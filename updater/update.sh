#!/usr/bin/env sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
run_updater() {
    if ! command -v git >/dev/null 2>&1; then
        printf 'Hinweis: Git nicht installiert; starte ohne git pull.\n'
    elif ! git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        printf 'Hinweis: Kein Git-Repository; starte ohne git pull.\n'
    else
        printf 'Aktualisiere Updater und Konfiguration ...\n'
        if ! git -C "$SCRIPT_DIR" pull --ff-only; then
            printf 'Fehler: git pull fehlgeschlagen. Updater wird nicht gestartet.\n' >&2
            return 1
        fi
    fi
    python3 "$SCRIPT_DIR/update.py" "$@"
}
run_updater "$@"
result=$?
printf '\nZum Schließen Enter drücken ... '
read -r ignored
exit "$result"
