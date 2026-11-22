#!/usr/bin/env bash
# Server bootstrap for "Bilans dzialki" (Ubuntu 24.04). Run ON THE SERVER as root; idempotent.
# Usage (normally called by deploy.sh): IP=1.2.3.4 [DOMAIN=example.com] bash bootstrap.sh
set -euo pipefail

UV_VERSION="${UV_VERSION:-0.11.32}"
APP_USER=deploy
APP_ROOT=/srv/bilans
APP_DIR=$APP_ROOT/app
CACHE_DIR=/var/lib/bilans/geodata_cache
ENV_FILE=/etc/bilans.env
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a   # no interactive "restart services?" dialog after the upgrade
# A fresh VPS often still runs cloud-init / unattended-upgrades and holds the dpkg lock: wait instead of failing.
APT=(apt-get -y -qq -o DPkg::Lock::Timeout=600 -o Dpkg::Options::=--force-confold)

[ "$(id -u)" -eq 0 ] || { echo "Run as root" >&2; exit 1; }

if [ -n "${DOMAIN:-}" ]; then
  HOST="$DOMAIN"
elif [ -n "${IP:-}" ]; then
  HOST="${IP//./-}.sslip.io"
else
  echo "Set IP (or DOMAIN)" >&2; exit 1
fi
echo "== host: $HOST"

echo "== apt update/upgrade"
"${APT[@]}" update
"${APT[@]}" upgrade
# libgomp1: shared library required by the lightgbm wheel (all other native libraries are bundled in the wheels).
# No build-essential: every dependency in uv.lock comes as a prebuilt manylinux x86_64 wheel.
"${APT[@]}" install git curl rsync ca-certificates ufw unattended-upgrades libgomp1 \
  debian-keyring debian-archive-keyring apt-transport-https gnupg
# periodic security upgrades
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF

echo "== swap (safety net for 4 GB RAM)"
if ! swapon --show | grep -q .; then
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile.tmp && chmod 600 /swapfile.tmp && mkswap /swapfile.tmp >/dev/null
    mv /swapfile.tmp /swapfile   # appears under its final name only when complete
  fi
  swapon /swapfile || true
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

echo "== firewall"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null   # SSH first, so that enabling the firewall cannot cut the session
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo "== user $APP_USER"
if ! id "$APP_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$APP_USER" >/dev/null
fi
echo "$APP_USER ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/90-$APP_USER.tmp
chmod 440 /etc/sudoers.d/90-$APP_USER.tmp
visudo -cf /etc/sudoers.d/90-$APP_USER.tmp >/dev/null   # a broken sudoers file would lock sudo out
mv /etc/sudoers.d/90-$APP_USER.tmp /etc/sudoers.d/90-$APP_USER
install -d -m 700 -o "$APP_USER" -g "$APP_USER" /home/$APP_USER/.ssh
# keep existing deploy keys, add the keys of root and of the account that ran sudo (SSH_USER, e.g. ubuntu)
KEYSRC=(/root/.ssh/authorized_keys)
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
  KEYSRC+=("$(getent passwd "$SUDO_USER" | cut -d: -f6)/.ssh/authorized_keys")
fi
touch /home/$APP_USER/.ssh/authorized_keys
AK=$(mktemp)
for f in "${KEYSRC[@]}" /home/$APP_USER/.ssh/authorized_keys; do [ -s "$f" ] && cat "$f"; done | sort -u >"$AK" || true
if [ -s "$AK" ]; then
  install -m 600 -o "$APP_USER" -g "$APP_USER" "$AK" /home/$APP_USER/.ssh/authorized_keys
else
  echo "WARNING: no SSH public key found for user $APP_USER; deploy.sh will not be able to upload code" >&2
fi
rm -f "$AK"

echo "== uv $UV_VERSION"
if ! command -v uv >/dev/null || ! uv --version | grep -q " $UV_VERSION"; then
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" \
    | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
install -d -o "$APP_USER" -g "$APP_USER" /opt/uv-python
sudo -u "$APP_USER" env UV_PYTHON_INSTALL_DIR=/opt/uv-python uv python install 3.12

echo "== Caddy"
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    >/etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  "${APT[@]}" update
  "${APT[@]}" install caddy
fi

echo "== directories and environment file"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_ROOT" "$APP_DIR"
install -d -o "$APP_USER" -g "$APP_USER" /var/lib/bilans "$CACHE_DIR"
# the app also keeps the SMSR page cache in <app>/data/raw (not uploaded or deleted by rsync, see deploy.sh)
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR/data" "$APP_DIR/data/raw"
if [ ! -f "$ENV_FILE" ]; then
  cat >"$ENV_FILE" <<CONF
# Environment of bilans.service. No secrets here unless you add them yourself.
GEODATA_CACHE_DIR=$CACHE_DIR
UV_PYTHON_INSTALL_DIR=/opt/uv-python
CONF
  chmod 644 "$ENV_FILE"
fi

echo "== systemd unit"
cat >/etc/systemd/system/bilans.service <<UNIT
[Unit]
Description=Bilans dzialki (uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3
LimitNOFILE=65536
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
ReadWritePaths=/var/lib/bilans $APP_DIR/data/raw

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable bilans >/dev/null 2>&1

echo "== Caddyfile"
cat >/etc/caddy/Caddyfile <<CADDY
$HOST {
	encode zstd gzip
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		X-Frame-Options "SAMEORIGIN"
		-Server
	}
	@static path /static/*
	header @static Cache-Control "public, max-age=300"
	reverse_proxy 127.0.0.1:8000 {
		transport http {
			response_header_timeout 120s
		}
	}
}
CADDY
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable caddy >/dev/null 2>&1
systemctl reload caddy 2>/dev/null || systemctl restart caddy

mkdir -p /var/lib/bilans && date -u +%FT%TZ >/var/lib/bilans/bootstrapped
echo "BOOTSTRAP OK: https://$HOST/"
