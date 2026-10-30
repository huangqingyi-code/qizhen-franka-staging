"Set Linux parent-death signal without unsafe Popen preexec_fn in broker threads."

import ctypes
import os
import signal
import sys

if sys.platform == "linux":
    if ctypes.CDLL(None).prctl(1, signal.SIGINT) != 0:
        raise SystemExit("could not set parent-death signal")
    if os.getppid() != int(sys.argv[1]):
        raise SystemExit("broker already exited")
os.execv(sys.argv[2], sys.argv[2:])
