#!/usr/bin/env bash
# Deploy from the laptop: ./deploy/deploy.sh <IP> [domain] [--warm] [--bootstrap]
# First run: bootstrap server + upload + start. Next runs: upload + restart only.
# SSH_USER (default root) is used for bootstrap; code is uploaded as user "deploy".
set -euo pipefail

cd "$(dirname "$0")/.."
WARM=0; FORCE_BOOT=0; ARGS=()
for a in "$@"; do
  case "$a" in
    --warm) WARM=1 ;;
    --bootstrap) FORCE_BOOT=1 ;;
    -h|--help) sed -n 2,5p "$0"; exit 0 ;;
    *) ARGS+=("$a") ;;
  esac
done
IP="${ARGS[0]:-}"; DOMAIN="${ARGS[1]:-${DOMAIN:-}}"
[ -n "$IP" ] || { echo "Usage: $0 <IP> [domain] [--warm] [--bootstrap]" >&2; exit 1; }
SSH_USER="${SSH_USER:-root}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o ServerAliveInterval=30)
SUDO=""; [ "$SSH_USER" = root ] || SUDO="sudo -E"
HOST="${DOMAIN:-${IP//./-}.sslip.io}"

echo "== ssh check ($SSH_USER@$IP)"
ssh "${SSH_OPTS[@]}" "$SSH_USER@$IP" true || { echo "FAIL: ssh to $SSH_USER@$IP" >&2; exit 1; }

NEED_BOOT=$FORCE_BOOT
if [ "$NEED_BOOT" -eq 0 ]; then
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$IP" 'test -f /var/lib/bilans/bootstrapped' 2>/dev/null || NEED_BOOT=1
fi
if [ "$NEED_BOOT" -eq 1 ]; then
  echo "== bootstrap on server (first run takes a few minutes)"
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$IP" "$SUDO env IP='$IP' DOMAIN='$DOMAIN' bash -s" <deploy/bootstrap.sh
fi

echo "== upload code"
git rev-parse --short HEAD >deploy/.REVISION 2>/dev/null || echo unknown >deploy/.REVISION
RSYNC_EXCL=(
  --exclude=.git --exclude=.venv --exclude=.worktrees --exclude=__pycache__ --exclude=.pytest_cache
  --exclude=.ruff_cache --exclude=node_modules --exclude=data/raw --exclude=artifacts
  --exclude=docs/img --exclude='*.webm' --exclude='*.mp4' --exclude='*.log' --exclude=.env
)
du -sh --exclude=.git --exclude=.venv --exclude=.worktrees --exclude=data/raw --exclude=artifacts --exclude=docs/img . 2>/dev/null | sed 's/^/approx size to upload: /' || true
rsync -az --delete --stats "${RSYNC_EXCL[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "deploy@$IP:/srv/bilans/app/" \
  | grep -E "Total transferred file size|Number of regular files transferred" || true
rm -f deploy/.REVISION

echo "== uv sync on server"
ssh "${SSH_OPTS[@]}" "deploy@$IP" 'cd /srv/bilans/app && UV_PYTHON_INSTALL_DIR=/opt/uv-python uv sync --frozen --no-dev --python 3.12 -q'

echo "== restart"
ssh "${SSH_OPTS[@]}" "deploy@$IP" 'sudo systemctl restart bilans && sleep 3 && systemctl is-active bilans'

if [ "$WARM" -eq 1 ]; then
  echo "== warm cache (server-side)"
  ssh "${SSH_OPTS[@]}" "deploy@$IP" 'bash /srv/bilans/app/deploy/warm.sh http://127.0.0.1:8000' || echo "warm: finished with errors"
fi
echo "DEPLOY OK: https://$HOST/   (check: ./deploy/smoke.sh https://$HOST)"
