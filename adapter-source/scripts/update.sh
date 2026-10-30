#!/usr/bin/env bash
set -euo pipefail
# Existing adapter only. Force-stop and archive old blocking sessions before updating.
root=$(cd "$(dirname "$0")/.." && pwd)
source "$root/scripts/release_common.sh"
connector=${QIZHEN_EDGE_BIN:-"$HOME/.local/bin/qizhen-linux-edge"}
release_select_python
build=false
case $# in
  0) build=true ;;
  2) package=$1; digest=$2 ;;
  *) echo 'usage: update.sh [PACKAGE.tar.gz sha256:DIGEST]' >&2; exit 2 ;;
esac
[[ -f "$HOME/.config/qizhen-franka/config.json" ]] || {
  echo 'Existing local config required; use install.sh for first installation.' >&2; exit 1;
}
if "$build"; then release_build --reuse-existing; fi
release_verify
# Package checks complete before pausing the Connector or touching live sessions.
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
    echo 'Update failed; restoring the previously running Connector service (no adapter rollback).' >&2
    if ! "$systemctl" --user start "$service" || ! "$systemctl" --user is-active --quiet "$service"; then
      echo "Connector recovery failed; run: systemctl --user start $service" >&2
    fi
  fi
  exit "$result"
}
trap restore_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Stop command processing first, so no new call can relaunch the old broker.
"$systemctl" --user stop "$service"
# Stop the old broker and archive blockers; never restart the old version before updating.
"$python" "$root/scripts/broker_control.py" --force-stop
"$connector" adapter update "$package" --sha256 "$digest"
"$connector" adapter start adapter_franka_ribbon
"$connector" adapter health adapter_franka_ribbon
"$connector" capabilities sync
# Synchronization is a standalone CLI operation; resume the service afterwards.
"$systemctl" --user start "$service"
"$systemctl" --user is-active --quiet "$service"
