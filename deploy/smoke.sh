#!/usr/bin/env bash
# Post-deploy smoke test: ./deploy/smoke.sh <URL>   (e.g. https://1-2-3-4.sslip.io or http://127.0.0.1:8785)
set -uo pipefail
URL="${1:?Usage: $0 <URL>}"; URL="${URL%/}"
FAILS=0
report() { # name, path, extra curl args...
  local name="$1" path="$2" out code t body; shift 2
  out=$(curl -sG --max-time 180 -L -w '\n%{http_code} %{time_total}' "$URL$path" "$@") || true
  code=$(tail -n1 <<<"$out" | cut -d' ' -f1); t=$(tail -n1 <<<"$out" | cut -d' ' -f2)
  body=$(sed '$d' <<<"$out")
  if [ "$code" = 200 ] && grep -qi "werdykt" <<<"$body"; then echo "PASS $name (${t}s)"
  else echo "FAIL $name (HTTP $code, ${t}s, no verdict)"; FAILS=$((FAILS+1)); fi
}
check() { # name, ok(0/1), detail
  if [ "$2" = 0 ]; then echo "PASS $1 ($3)"; else echo "FAIL $1 ($3)"; FAILS=$((FAILS+1)); fi
}

out=$(curl -s --max-time 20 -w '\n%{http_code} %{time_total}' "$URL/health" || true)
c=$(tail -n1 <<<"$out" | cut -d' ' -f1); check "health" "$([ "$c" = 200 ]; echo $?)" "HTTP $c, $(tail -n1 <<<"$out" | cut -d' ' -f2)s"
out=$(curl -s --max-time 30 -o /dev/null -w '%{http_code} %{time_total}' "$URL/" || true)
check "start screen" "$([ "${out%% *}" = 200 ]; echo $?)" "HTTP ${out%% *}, ${out##* }s"

report "report 189/13 (demo)" /raport --data-urlencode "dzialka=040303_2.0002.189/13" --data-urlencode "data=2023-07-20" --data-urlencode "uprawa=zboza_jare"
report "report 144 (demo 2)" /raport --data-urlencode "dzialka=100403_2.0011.144" --data-urlencode "data=2026-11-21" --data-urlencode "uprawa=rosliny_straczkowe"
report "report cold 160204_5.0001.101" /raport --data-urlencode "dzialka=160204_5.0001.101" --data-urlencode "data=2023-07-20" --data-urlencode "uprawa=zboza_jare"

# ULDK reachable from this machine and not the decoy: expect a real polygon.
# (when URL is the server, run this script on the server too, or accept that it tests the caller's network)
t0=$(date +%s.%N)
u=$(curl -s --max-time 30 -G "https://uldk.gugik.gov.pl/" --data-urlencode "request=GetParcelById" \
  --data-urlencode "id=040303_2.0002.189/13" --data-urlencode "result=geom_wkt" --data-urlencode "srid=2180" || true)
dt=$(awk -v a="$t0" -v b="$(date +%s.%N)" 'BEGIN{printf "%.2f", b-a}')
check "ULDK polygon (this host)" "$(grep -q 'POLYGON' <<<"$u"; echo $?)" "${dt}s"

if [ "$FAILS" -eq 0 ]; then echo "SMOKE PASS"; else echo "SMOKE FAIL ($FAILS)"; exit 1; fi
