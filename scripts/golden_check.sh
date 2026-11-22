#!/usr/bin/env bash
# Golden locations against a running application: ./scripts/golden_check.sh https://ADDRESS [--only ID]
# Without an address the checks run offline on the frozen data. Exit code 1 on any FAIL.
set -uo pipefail
cd "$(dirname "$0")/.."
URL="${1:-}"; [ $# -gt 0 ] && shift
if [ -n "$URL" ]; then
  # the application must answer before the long run
  code=$(curl -s -o /dev/null --max-time 20 -w '%{http_code}' "${URL%/}/health" || true)
  [ "$code" = 200 ] || { echo "Aplikacja pod ${URL} nie odpowiada na /health (HTTP ${code})"; exit 2; }
  exec uv run python scripts/golden_check.py "$URL" "$@"
fi
exec uv run python scripts/golden_check.py "$@"
