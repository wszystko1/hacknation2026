#!/usr/bin/env bash
# Warm the server cache (the two demo parcels first, live when the server runs with HN_LIVE_ONLY=1): ./deploy/warm.sh [URL] [MAX_PARCELS]  (default http://127.0.0.1:8000, 12)
# Sequential, 120 s per request, 20 min total.
set -uo pipefail
URL="${1:-http://127.0.0.1:8000}"; URL="${URL%/}"; MAX="${2:-12}"
CSV="$(dirname "$0")/../demo/data/eval/parcels50.csv"
DEADLINE=$(( $(date +%s) + 1200 )); n=0; ok=0
hit() { # parcel date crop
  [ "$(date +%s)" -lt "$DEADLINE" ] || { echo "time limit reached"; return 1; }
  local r; r=$(curl -sG -L --max-time 120 -o /dev/null -w '%{http_code} %{time_total}' "$URL/raport" \
    --data-urlencode "dzialka=$1" --data-urlencode "data=$2" --data-urlencode "uprawa=$3" || true)
  echo "$1 $2 $3 -> $r"; n=$((n+1)); [ "${r%% *}" = 200 ] && ok=$((ok+1)); return 0
}
hit 040303_2.0002.189/13 2023-07-20 zboza_jare
hit 100403_2.0011.144 2026-11-21 rosliny_straczkowe
# parcels50.csv holds points (lon, lat), most rows without a parcel id: resolve the id with ULDK GetParcelByXY.
resolve() { # lon lat -> parcel id or empty
  curl -s --max-time 20 -G "https://uldk.gugik.gov.pl/" --data-urlencode "request=GetParcelByXY" \
    --data-urlencode "xy=$1,$2,4326" --data-urlencode "result=teryt" | tr -d '\r' | sed -n 2p | cut -d'|' -f1
}
if [ -f "$CSV" ]; then
  seen=""
  while IFS=, read -r dz _ lon lat dt cr; do
    [ "$dz" != dzialka ] && [ -n "$cr" ] || continue
    [ "$dt" = dzis ] && dt=$(date +%F)
    [[ "$dt" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || continue
    [ -n "$dz" ] || dz=$(resolve "$lon" "$lat")
    [ -n "$dz" ] || continue
    key="$dz|$dt|$cr"; case "$seen" in *"$key"*) continue ;; esac; seen="$seen $key"
    [ "$n" -lt "$MAX" ] || break
    hit "$dz" "$dt" "$cr" || break
  done <"$CSV"
fi
echo "warm: $ok/$n ok"
