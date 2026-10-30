#!/usr/bin/env bash
set -euo pipefail
# Native Connector must already be installed and paired.
root=$(cd "$(dirname "$0")/.." && pwd)
source "$root/scripts/release_common.sh"
connector=${QIZHEN_EDGE_BIN:-"$HOME/.local/bin/qizhen-linux-edge"}
release_select_python
build=false
case $# in
  0) build=true; config="$HOME/.config/qizhen-franka/config.json" ;;
  1) build=true; config=$1 ;;
  3) package=$1; digest=$2; config=$3 ;;
  *) echo 'usage: install.sh [LOCAL_CONFIG.json] | PACKAGE.tar.gz sha256:DIGEST LOCAL_CONFIG.json' >&2; exit 2 ;;
esac
[[ -f "$config" ]] || {
  echo 'Local config required: pass its path to install.sh for first installation.' >&2; exit 1;
}
if [[ -e "$HOME/.config/qizhen-franka/config.json" ]]; then
  cmp -s "$config" "$HOME/.config/qizhen-franka/config.json" || {
    echo 'Existing config differs; finish/cancel and reconcile active sessions, stop broker, then explicitly update config.' >&2; exit 1;
  }
fi
if "$build"; then release_build; fi
release_verify
# Finish validation before pausing the Connector; restore its previous state on failure.
systemctl=${QIZHEN_SYSTEMCTL_BIN:-systemctl}
service=qizhen-linux-edge.service
restore_service=false
if "$systemctl" --user is-active --quiet "$service"; then
  restore_service=true
fi
restore_on_exit() {
  local result=$?
  trap - EXIT
  if (( result != 0 )) && "$restore_service"; then
    echo 'Installation failed; restoring the previously running Connector service (no adapter rollback).' >&2
    if ! "$systemctl" --user start "$service" || ! "$systemctl" --user is-active --quiet "$service"; then
      echo "Connector recovery failed; run: systemctl --user start $service" >&2
    fi
  fi
  exit "$result"
}
trap restore_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$systemctl" --user stop "$service"
mkdir -p "$HOME/.config/qizhen-franka"
if [[ ! -e "$HOME/.config/qizhen-franka/config.json" ]]; then
  install -m 600 "$config" "$HOME/.config/qizhen-franka/config.json"
fi
"$connector" adapter install "$package" --sha256 "$digest"
"$connector" adapter start adapter_franka_ribbon
"$connector" adapter health adapter_franka_ribbon
"$connector" capabilities sync
# Start the Connector only after installation, health checks and synchronization succeed.
"$systemctl" --user start "$service"
"$systemctl" --user is-active --quiet "$service"
