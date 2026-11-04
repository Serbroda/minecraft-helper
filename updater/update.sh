#!/usr/bin/env sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
python3 "$SCRIPT_DIR/update.py" "$@"
result=$?
printf '\nZum Schließen Enter drücken ... '
read -r ignored
exit "$result"
