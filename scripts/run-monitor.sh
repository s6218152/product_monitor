#!/bin/sh
cd /home/s6218152/facebook-product-monitor || exit 1
start=$(date +%s)
status=0
for source in groups marketplace; do
    /usr/bin/timeout --kill-after=15s 420s .venv/bin/python main.py "$source" --live
    code=$?
    echo "source=$source exit=$code"
    [ "$code" -eq 0 ] || status=1
done
/usr/bin/timeout --kill-after=10s 90s .venv/bin/python main.py telegram --limit 30 --send
code=$?
[ "$code" -eq 0 ] || status=1
echo "run_completed elapsed=$(( $(date +%s) - start ))s status=$status"
exit "$status"
