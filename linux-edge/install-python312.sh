#!/bin/sh
# Install/reuse Python 3.12 for Qizhen without changing the system Python.
set -eu

version=3.12.15
expected=de1a241a519e0a3374fea98988d0b52c886743f9d953f23be8269cc7b59c5fab
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
archive="$script_dir/Python-$version.tgz"
prefix="$HOME/.local/opt/python-$version"
installer_env="$HOME/.local/lib/qizhen-edge-installer"
jobs=2
install_deps=0

usage() {
  cat <<'USAGE'
Usage: sh install-python312.sh [--install-deps] [--jobs N]

Run as the target Linux user, not with sudo.
Reuses an existing Python 3.12 with the required modules.
If absent or incomplete, builds Python-3.12.15.tgz from this directory.
Source archive and build tools are only needed for the compilation path.
Installs to ~/.local/opt/python-3.12.15 without changing system Python.
Creates ~/.local/lib/qizhen-edge-installer for the Qizhen wheel installer.

--install-deps  Install build dependencies using sudo apt-get (Debian/Ubuntu).
--jobs N        Number of compilation jobs (default: 2).
USAGE
}

fail() { printf '%s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-deps) install_deps=1; shift ;;
    --jobs)
      [ "$#" -ge 2 ] || fail '--jobs requires a positive integer'
      jobs=$2
      case "$jobs" in ''|*[!0-9]*) fail '--jobs requires a positive integer' ;; esac
      [ "$jobs" -gt 0 ] || fail '--jobs requires a positive integer'
      shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; fail "Unknown argument: $1" ;;
  esac
done

[ "$(uname -s)" = Linux ] || fail 'This installer must run on the target Linux host.'
case "$(uname -m)" in
  x86_64|aarch64|arm64) ;;
  *) fail 'Only Linux AMD64 and ARM64 are supported.' ;;
esac
[ "$(id -u)" -ne 0 ] || fail 'Run as the target user without sudo; use --install-deps if needed.'

is_python312() {
  "$1" -c 'import sys; assert sys.version_info[:2] == (3, 12)' >/dev/null 2>&1
}

check_python() {
  "$1" -c 'import sys; assert sys.version_info[:2] == (3, 12); import ssl, sqlite3, bz2, lzma, ctypes, venv, ensurepip' >/dev/null 2>&1
}

python_bin=
for candidate in python3.12 python3; do
  candidate_path=$(command -v "$candidate" 2>/dev/null || true)
  if [ -n "$candidate_path" ] && check_python "$candidate_path"; then
    python_bin=$candidate_path
    break
  elif [ -n "$candidate_path" ] && is_python312 "$candidate_path"; then
    printf 'Python 3.12 at %s lacks required modules; checking other installations.\n' "$candidate_path"
  fi
done
# Also reuse the private interpreter from an earlier source installation.
if [ -z "$python_bin" ] && [ -x "$prefix/bin/python3.12" ] && check_python "$prefix/bin/python3.12"; then
  python_bin="$prefix/bin/python3.12"
fi
# A previous rebuild may use a different private directory; the installer
# environment retains the interpreter path and can be reused on later runs.
if [ -z "$python_bin" ] && [ -x "$installer_env/bin/python3" ] && check_python "$installer_env/bin/python3"; then
  python_bin="$installer_env/bin/python3"
fi

if [ -z "$python_bin" ]; then
  printf 'No complete Python 3.12 found; building the bundled source.\n'
  [ -f "$archive" ] || fail "Missing source archive: $archive"
  command -v sha256sum >/dev/null 2>&1 || fail 'sha256sum is required.'
  actual=$(sha256sum "$archive")
  actual=${actual%% *}
  [ "$actual" = "$expected" ] || fail 'Python source SHA-256 does not match the official checksum.'
  if [ -e "$prefix" ]; then
    # Preserve an incomplete prior installation instead of overwriting it.
    prefix="$HOME/.local/opt/python-$version-rebuild-$(date +%Y%m%d%H%M%S)-$$"
    printf 'Preserving the existing installation; new Python directory: %s\n' "$prefix"
  fi
  if [ "$install_deps" -eq 1 ]; then
    command -v apt-get >/dev/null 2>&1 || fail '--install-deps requires Debian/Ubuntu apt-get.'
    command -v sudo >/dev/null 2>&1 || fail 'sudo is required for --install-deps.'
    sudo apt-get update
    sudo apt-get install -y build-essential ca-certificates \
      libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
      libsqlite3-dev libffi-dev liblzma-dev libncurses-dev \
      libgdbm-dev uuid-dev
  fi
  for tool in cc make tar; do
    command -v "$tool" >/dev/null 2>&1 || fail "Missing $tool; on Debian/Ubuntu retry with --install-deps."
  done
  build_dir=$(mktemp -d "${TMPDIR:-/tmp}/qizhen-python312.XXXXXX")
  trap 'rm -rf "$build_dir"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  tar -xzf "$archive" -C "$build_dir"
  (
    cd "$build_dir/Python-$version"
    ./configure --prefix="$prefix" --with-ensurepip=install
    make -j"$jobs"
    # Verify essential modules before installing a potentially incomplete build.
    check_python ./python || fail 'Built Python lacks essential modules; install the build dependencies and retry.'
    make altinstall
  )
  python_bin="$prefix/bin/python3.12"
else
  printf 'Reusing Python: %s\n' "$python_bin"
fi

check_python "$python_bin" || fail 'Python 3.12 validation failed.'
"$python_bin" -m venv "$installer_env"
check_python "$installer_env/bin/python" || fail 'Installer virtual environment validation failed.'
printf '\nPython ready: '
"$installer_env/bin/python" --version
printf 'Installer environment: %s\n' "$installer_env"
printf 'System Python and its dependencies were not replaced.\n'
printf '\nNext, from the artifact directory run:\n'
printf 'sh install.sh qizhen_linux_edge-0.1.0-py3-none-any.whl sha256:<wheel-digest>\n'
