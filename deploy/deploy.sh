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
# BatchMode: never wait for a password prompt; a missing key fails at once with a clear message.
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o ServerAliveInterval=30)
command -v rsync >/dev/null || { echo "FAIL: rsync is not installed on this machine" >&2; exit 1; }
command -v ssh >/dev/null || { echo "FAIL: ssh is not installed on this machine" >&2; exit 1; }
SUDO=""; [ "$SSH_USER" = root ] || SUDO="sudo -E"
HOST="${DOMAIN:-${IP//./-}.sslip.io}"

echo "== ssh check ($SSH_USER@$IP)"
ssh "${SSH_OPTS[@]}" "$SSH_USER@$IP" true || {
  echo "FAIL: ssh to $SSH_USER@$IP. Check: (1) your public key was added to the server when it was created," >&2
  echo "      (2) the IP is right and port 22 is open, (3) 'REMOTE HOST IDENTIFICATION HAS CHANGED' above means the IP" >&2
  echo "      was used by an older server: run ssh-keygen -R $IP and retry. Other login user: SSH_USER=ubuntu $0 ..." >&2
  exit 1
}

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
  --exclude=.hn --exclude=.claude
)
du -sh --exclude=.git --exclude=.venv --exclude=.worktrees --exclude=data/raw --exclude=artifacts --exclude=docs/img . 2>/dev/null | sed 's/^/approx size to upload: /' || true
# Excluded paths (.venv, data/raw) are neither uploaded nor deleted on the server (no --delete-excluded).
# The exit status of rsync itself is checked: a failed upload must not end with "DEPLOY OK" on old code.
RSYNC_OUT=$(mktemp)
if ! rsync -az --delete --stats "${RSYNC_EXCL[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "deploy@$IP:/srv/bilans/app/" >"$RSYNC_OUT" 2>&1; then
  cat "$RSYNC_OUT" >&2; rm -f "$RSYNC_OUT" deploy/.REVISION
  echo "FAIL: rsync to deploy@$IP (the 'deploy' user needs your SSH key; bootstrap copies it from the login user)" >&2
  exit 1
fi
grep -E "Total transferred file size|Number of regular files transferred" "$RSYNC_OUT" || true
rm -f "$RSYNC_OUT" deploy/.REVISION

echo "== uv sync on server"
ssh "${SSH_OPTS[@]}" "deploy@$IP" 'cd /srv/bilans/app && UV_PYTHON_INSTALL_DIR=/opt/uv-python /usr/local/bin/uv sync --frozen --no-dev --python 3.12 -q'

echo "== live-only mode (HN_LIVE_ONLY=1: no copy from demo/data on the server)"
ssh "${SSH_OPTS[@]}" "deploy@$IP" "sudo grep -q '^HN_LIVE_ONLY=1' /etc/bilans.env || echo 'HN_LIVE_ONLY=1' | sudo tee -a /etc/bilans.env >/dev/null" \
  || echo "warn: could not set HN_LIVE_ONLY=1 in /etc/bilans.env; run deploy/bootstrap.sh again" >&2

echo "== restart"
# is-active is "active" as soon as the process exists, so wait until /health really answers (up to 60 s).
ssh "${SSH_OPTS[@]}" "deploy@$IP" 'sudo systemctl restart bilans && for i in $(seq 1 30); do
  curl -fsS -o /dev/null --max-time 3 http://127.0.0.1:8000/health && { echo "bilans: healthy"; exit 0; }; sleep 2; done
  echo "FAIL: bilans did not answer /health; see: journalctl -u bilans -n 50" >&2; sudo journalctl -u bilans -n 20 --no-pager >&2; exit 1'

if [ "$WARM" -eq 1 ]; then
  echo "== warm cache (server-side)"
  ssh "${SSH_OPTS[@]}" "deploy@$IP" 'bash /srv/bilans/app/deploy/warm.sh http://127.0.0.1:8000' || echo "warm: finished with errors"
fi
echo "DEPLOY OK: https://$HOST/   (check: ./deploy/smoke.sh https://$HOST)"
