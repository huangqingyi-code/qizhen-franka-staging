#!/usr/bin/env bash
systemctl --user stop qizhen-linux-edge.service
"$HOME/.local/lib/qizhen-edge/current/bin/python" "$(dirname -- "$0")/broker_control.py" --force-stop
systemctl --user start qizhen-linux-edge.service
