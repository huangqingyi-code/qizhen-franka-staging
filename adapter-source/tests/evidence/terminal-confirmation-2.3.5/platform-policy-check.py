"""Offline consumer test: actual Connector export + API invocation policy, no device calls."""
import asyncio
import json
from pathlib import Path
from qizhen_linux_edge.adapters import AdapterManager
from qizhen_platform_api.capability_invocations import CapabilityInvocationService
from qizhen_platform_api.errors import ApiProblem
from qizhen_platform_api.models import CapabilityInvocationRequest

manifest=json.loads(Path('/adapter/adapter.json').read_text())
exported=AdapterManager._capability_adapter({'manifest':manifest,'artifact_hash':'sha256:'+'1'*64,'size_bytes':1000,'installed_at':'2026-10-21T00:00:00Z'})
ops={op['operation_id']:op for op in exported['operations']}
assert [op for op,v in ops.items() if v['side_effect']=='high_impact']==['franka.session.respond']
class Authorizer:
    def __init__(self,op): self.op=op
    async def authorize(self,credential,body):
        op=ops[self.op]
        return ({'task_id':'task_fixture','agent_run_id':'run_fixture','trace_id':'trace_fixture'},
          {'capability_type':'tool','input_schema':op['input_schema'],'output_schema':op['output_schema'],
           'type_spec':{'kind':'tool','side_effect':op['side_effect'],'invocation':{
            'protocol':'resource_federation','endpoint_ref':'endpoint_fixture','endpoint_config_version':'1.0.0',
            'endpoint_config_hash':'sha256:'+'7'*64,'supports_stream':False,'operation':self.op}}})
class Invoker:
    def __init__(self): self.calls=[]
    async def invoke(self,**values):
        self.calls.append(values)
        return {'schema_version':'1.0','backend':'mock','simulated':True,'ok':True,
                'sampled_at':'2026-10-21T00:00:00Z','data':{},'error':None}
class Confirmations:
    def __init__(self): self.allowed=False;self.calls=0
    async def claim_issued(self,*args):
        self.calls+=1
        return ('confirmation_fixture','invocation_confirmed') if self.allowed else None

def request(op,args):
    return CapabilityInvocationRequest(capability_id='tool_fixture',version=manifest['version'],
        content_hash='sha256:'+'5'*64,input=args)
async def main():
    cases={
      'franka.ribbon.run':{},'franka.home':{},'franka.delta.move':{'translation_m':[0,0,0]},
      'franka.pipeline.start':{'task_id':'task_fixture','mode':'prepare','skip_leveling':True},
      'franka.offline.execute':{'trajectory_artifact_id':'artifact_fixture'},
      'franka.session.cancel':{'session_id':'session_fixture'},
      'franka.session.reconcile':{'session_id':'session_fixture','operator_verified_stopped':True}}
    for op,args in cases.items():
        invoker=Invoker();service=CapabilityInvocationService(Authorizer(op),{},resource_invoker=invoker)
        body=request(op,{'request_id':'request_fixture',**args})
        first=await service.invoke('grant_fixture','key_fixture',body)
        replay=await service.invoke('grant_fixture','key_fixture',body)
        assert first==replay and len(invoker.calls)==1,op
    op='franka.session.respond';invoker=Invoker();confirmations=Confirmations()
    service=CapabilityInvocationService(Authorizer(op),{},resource_invoker=invoker,confirmations=confirmations)
    body=request(op,{'request_id':'response_fixture','session_id':'session_fixture','confirmation_id':'confirm_current','action':'MOVE'})
    try:
        await service.invoke('grant_fixture','key_response',body)
    except ApiProblem as error: assert error.code=='capability_confirmation_required'
    else: raise AssertionError('Native terminal response bypassed user confirmation')
    assert not invoker.calls
    confirmations.allowed=True
    first=await service.invoke('grant_fixture','key_response',body)
    replay=await service.invoke('grant_fixture','key_response',body)
    assert first==replay and len(invoker.calls)==1 and confirmations.calls==2
    print(json.dumps({'ok':True,'connector_export_preserves_policy':True,
       'seven_start_cancel_reconcile_tools_without_extra_card':True,
       'terminal_response_requires_confirmation':True,'retries_do_not_replay':True,
       'platform_service':'real_code','transport':'fixture_only','hardware_tested':False}))
asyncio.run(main())
