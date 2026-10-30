"""Durable device events and local wait behavior; vendor and robot access are forbidden."""
import threading
import time
import unittest
from unittest.mock import patch

import rfc8785
from jsonschema import Draft202012Validator, ValidationError
import test_adapter as original
from broker import Broker
from core import MANIFEST, OPERATIONS


class SessionEventTests(unittest.TestCase):
    def setUp(self):
        self.fixture = original.AdapterTests()
        self.fixture.setUp()
        self.b = self.fixture.b
        self.s = self.fixture.failed_session()
        self.s.update(state='running', control_lock_pending=False, operation_id='franka.task.validate')
        self.b.save()

    def tearDown(self):
        self.fixture.tearDown()

    def read(self, after=0, seconds=0):
        return self.b.session_events({'session_id': self.s['session_id'], 'after':after,
                                     'max_wait_seconds':seconds})['events']

    def test_manifest_and_session_outputs_are_jcs_hashable(self):
        self.assertTrue(rfc8785.dumps(MANIFEST))
        for event in self.read():
            self.assertTrue(rfc8785.dumps(event))

    def test_revision_schema_and_event_cursor_share_safe_integer_boundary(self):
        schema = OPERATIONS['franka.session.status']['output_schema']['properties']['data']['properties']['session_revision']
        validator = Draft202012Validator(schema)
        maximum = 2**53 - 1
        self.assertEqual(schema['maximum'], maximum)
        validator.validate(maximum)
        self.assertEqual(self.read(maximum), [])
        for invalid in (-1, maximum + 1, 2**63 - 1, True, '1'):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    validator.validate(invalid)
                with self.assertRaisesRegex(ValueError, 'INVALID_SESSION_EVENTS_CURSOR'):
                    self.read(invalid)

    def test_events_are_immutable_and_log_updates_do_not_create_state_events(self):
        before = self.read()
        self.s['log_tail'] = 'new log text'
        self.b.save()
        self.assertEqual(self.read(), before)
        with self.b.lock:
            self.b.prompt(self.s, ['MOVE'], 'Current prompt')
        prompt = self.read()[-1]
        self.s['confirmation']['prompt'] = 'different prompt'
        self.b.save()
        self.assertEqual(prompt['output']['data']['confirmation']['prompt'], 'Current prompt')
        self.assertGreater(self.read()[-1]['revision'], prompt['revision'])

    def test_long_wait_is_not_a_tool_or_hardware_call(self):
        after = self.read()[-1]['revision']
        observed = []
        def wait():
            with patch.object(self.b, 'invoke', side_effect=AssertionError('tool called')):
                observed.extend(self.read(after, 2))
        thread = threading.Thread(target=wait)
        thread.start()
        time.sleep(0.05)
        with self.b.lock:
            self.s['state'] = 'succeeded'
            self.b.save()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(observed[-1]['output']['data']['state'], 'succeeded')

    def test_restart_replays_persisted_terminal_events_without_new_execution(self):
        self.s.update(state='succeeded', operation_id='franka.task.validate')
        self.b.save()
        before = self.read()
        with patch('broker.subprocess.Popen', side_effect=AssertionError('execution replayed')):
            restored = Broker(self.fixture.c)
        self.assertEqual(restored.session_events({'session_id': self.s['session_id'],
                         'after':0,'max_wait_seconds':0})['events'], before)

    def test_unknown_stop_verification_runs_without_status_query(self):
        self.s.update(state='unknown', operation_id='franka.delta.move', control_lock_pending=True)
        stop = threading.Event()
        with patch.object(self.b, 'refresh_failed_lock') as verify:
            thread = threading.Thread(target=self.b.verify_unresolved, args=(stop,))
            # Exercise the loop using a deterministic event instead of a five-second delay.
            with patch.object(stop, 'wait', side_effect=[False, True]):
                thread.start()
                thread.join(timeout=1)
            verify.assert_called_once_with(self.s)

    def test_background_unavailable_release_is_durable_without_status_or_replay(self):
        self.s.update(state='unknown', operation_id='franka.delta.move', control_lock_pending=True)
        self.b.save()
        after = self.read()[-1]['revision']
        stop = threading.Event()
        with patch.object(stop, 'wait', side_effect=[False, True]), \
             patch('stop_guard.read_snapshot', side_effect=OSError('fixture offline')), \
             patch.object(self.b, 'invoke', side_effect=AssertionError('status tool invoked')), \
             patch('broker.command', side_effect=AssertionError('motion replayed')):
            self.b.verify_unresolved(stop)
        event = self.read(after)[-1]
        data = event['output']['data']
        self.assertEqual(data['state'], 'failed')
        self.assertFalse(data['control_lock_pending'])
        self.assertFalse(data['physical_stop_verified'])
        self.assertTrue(data['stop_verification']['state_unavailable'])
        self.assertFalse(data['stop_verification']['verified'])
        self.assertEqual(data['error'], 'PROCESS_EXIT_1')
        Draft202012Validator(OPERATIONS['franka.session.status']['output_schema']).validate(event['output'])
        with patch('stop_guard.read_snapshot', side_effect=AssertionError('resolved session reread')), \
             patch('broker.command', side_effect=AssertionError('motion replayed')):
            restored = Broker(self.fixture.c)
            self.assertEqual(restored.session_events({'session_id': self.s['session_id'],
                'after': after, 'max_wait_seconds': 0})['events'], self.read(after))
        self.assertFalse(restored.store.data['sessions'][self.s['session_id']]['control_lock_pending'])

    def test_confirmation_response_cursor_skips_the_old_prompt(self):
        from types import SimpleNamespace
        with self.b.lock:
            self.b.prompt(self.s, ['MOVE'], 'Current MOVE prompt')
        confirmation_id = self.s['confirmation']['confirmation_id']
        old_revision = self.read()[-1]['revision']
        self.b.live[self.s['session_id']] = (0, SimpleNamespace(poll=lambda: None))
        with patch('broker.os.write', return_value=5):
            response = self.b.invoke('franka.session.respond', {
                'request_id':'respond_fixture', 'session_id':self.s['session_id'],
                'confirmation_id':confirmation_id, 'action':'MOVE'})
        self.assertGreater(response['session_revision'], old_revision)
        self.assertEqual(self.read(response['session_revision']), [])
        with self.b.lock:
            self.s['state'] = 'succeeded'
            self.b.save()
        events = self.read(response['session_revision'])
        self.assertEqual([e['output']['data']['state'] for e in events], ['succeeded'])
