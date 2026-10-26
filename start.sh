#!/bin/sh
cd "$(dirname "$0")"
for nf_sdk in ../renpy-*-sdk ./renpy-*-sdk; do
    if [ -f "$nf_sdk/lib/py3-linux-x86_64/python" ]; then
        chmod +x "$nf_sdk/lib/py3-linux-x86_64/python"
        exec "$nf_sdk/lib/py3-linux-x86_64/python" app.py --sdk "$nf_sdk" "$@"
    fi
done
exec python3 app.py "$@"
