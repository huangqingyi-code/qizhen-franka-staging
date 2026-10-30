#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
source "$root/scripts/release_common.sh"
release_select_python
"$python" - <<'CHECK'
import sys
import tarfile
if sys.version_info < (3, 11):
    raise SystemExit("Connector Python must be >=3.11; upgrade or repair the Connector environment.")
if not hasattr(tarfile, "data_filter"):
    raise SystemExit("Connector Python needs tarfile data filters; upgrade or repair the Connector environment.")
try:
    from jsonschema import Draft202012Validator
except ImportError:
    raise SystemExit("Connector Python needs jsonschema with Draft202012Validator support.") from None
print("Test Python: " + sys.executable + " (" + sys.version.split()[0] + ")", flush=True)
CHECK
exec "$python" -m unittest discover -s "$root/tests" -p 'test_*.py' "$@"
