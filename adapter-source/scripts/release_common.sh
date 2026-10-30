# Shared by test.sh, install.sh and update.sh; sourced, not executed directly.
release_select_python() {
  python="$HOME/.local/lib/qizhen-edge/current/bin/python"
  if [[ ! -x "$python" ]]; then
    echo "Connector Python is unavailable: $python; install or repair the Connector environment first." >&2
    return 1
  fi
}
release_build() {
  local result
  bash "$root/scripts/test.sh"
  result=$("$python" "$root/scripts/build_adapter.py" --architecture amd64 --output "$root/packages" "$@")
  package=$("$python" -c 'import json,sys; print(json.loads(sys.argv[1])["package"])' "$result")
  digest=$("$python" -c 'import json,sys; print(json.loads(sys.argv[1])["sha256"])' "$result")
  echo "Selected release package: $package"
}
release_verify() {
  local actual
  [[ -f "$package" ]] || { echo 'Package file not found.' >&2; return 1; }
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo 'Expected sha256:DIGEST.' >&2; return 1; }
  actual="sha256:$(sha256sum -- "$package" | cut -d ' ' -f 1)"
  [[ "$actual" == "$digest" ]] || { echo 'Package checksum mismatch; release refused.' >&2; return 1; }
}
