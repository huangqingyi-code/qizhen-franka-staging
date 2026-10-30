#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: install.sh WHEEL SHA256" >&2
  exit 2
fi

wheel=$1
expected=${2#sha256:}
case "$expected" in
  *[!0-9a-f]*|'') echo "SHA256 must be 64 lowercase hexadecimal characters" >&2; exit 2 ;;
esac
[ "${#expected}" -eq 64 ] || { echo "SHA256 must have 64 characters" >&2; exit 2; }
[ -f "$wheel" ] || { echo "wheel not found: $wheel" >&2; exit 2; }

installer_bin="$HOME/.local/lib/qizhen-edge-installer/bin"
if [ -x "$installer_bin/python3" ]; then
  export PATH="$installer_bin:$PATH"
  python_cmd="$installer_bin/python3"
elif command -v python3.12 >/dev/null 2>&1; then
  python_cmd=$(command -v python3.12)
else
  python_cmd=python3
fi

if ! "$python_cmd" -c 'import sys; assert sys.version_info[:2] == (3, 12)' >/dev/null 2>&1; then
  echo "Python 3.12 is required; first run: sh install-python312.sh" >&2
  exit 1
fi

actual=$("$python_cmd" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$wheel")
[ "$actual" = "$expected" ] || { echo "wheel SHA-256 mismatch" >&2; exit 1; }

if ! "$python_cmd" -c 'import ensurepip, venv' >/dev/null 2>&1; then
  echo "python venv support is required (Ubuntu: sudo apt install python3-venv)" >&2
  exit 1
fi

root=${QIZHEN_EDGE_INSTALL_ROOT:-"$HOME/.local/lib/qizhen-edge"}
bin_dir=${QIZHEN_EDGE_BIN_DIR:-"$HOME/.local/bin"}
release="$root/releases/$expected"
created=0
if [ ! -d "$release" ]; then
  created=1
  mkdir -p "$root/releases"
  trap 'if [ "$created" = 1 ]; then rm -rf "$release"; fi' EXIT INT TERM
  "$python_cmd" -m venv "$release"
  "$release/bin/python" -m pip install --no-cache-dir "$wheel"
fi
"$release/bin/qizhen-linux-edge" --version >/dev/null

previous=$(readlink "$root/current" 2>/dev/null || true)
if [ -n "$previous" ]; then ln -sfn "$previous" "$root/previous"; fi
ln -sfn "$release" "$root/current"
mkdir -p "$bin_dir"
ln -sfn "$root/current/bin/qizhen-linux-edge" "$bin_dir/qizhen-linux-edge"
created=0
trap - EXIT INT TERM
echo "installed qizhen-linux-edge at $bin_dir/qizhen-linux-edge"
export PATH="$bin_dir:$PATH"
qizhen-linux-edge doctor
echo "To use the command name in your terminal, run:"
printf 'export PATH="%s:$PATH"\n' "$bin_dir"
echo "Alternatively, use: $bin_dir/qizhen-linux-edge"
