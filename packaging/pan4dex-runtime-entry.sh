#!/bin/bash
# Start ibus + pinyin inside the container, then exec the Pan4dex app.
export DISPLAY="${DISPLAY:-:0}"
if ! pgrep -x ibus-daemon >/dev/null 2>&1; then
    dbus-launch --exit-with-session ibus-daemon -drx --panel=disable >/dev/null 2>&1
    sleep 1
fi
ibus engine libpinyin >/dev/null 2>&1 || true
exec "$@"
