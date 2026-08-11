#!/usr/bin/env bash
# Adds /assets/ reverse-proxy locations to the existing finance nginx
# server block, proxying the Vite app to 127.0.0.1:5182 and the review API/
# asset routes to 127.0.0.1:8765.
#
# Run with sudo:
#   sudo bash deploy/install-nginx-assets-review.sh

set -euo pipefail

CONF="${FINANCE_NGINX_CONF:-/etc/nginx/sites-available/finance}"

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "$CONF" ]]; then
  echo "nginx config not found: $CONF" >&2
  echo "Set FINANCE_NGINX_CONF=/path/to/conf and re-run." >&2
  exit 1
fi

if grep -q "location /assets/" "$CONF"; then
  echo "/assets/ location already present in $CONF - nothing to do."
  exit 0
fi

BACKUP="${CONF}.bak.$(date +%Y%m%d-%H%M%S)"
cp -p "$CONF" "$BACKUP"
echo "Backed up $CONF -> $BACKUP"

read -r -d '' BLOCK <<'EOF' || true
    # --- Portrait Workbench (Vite on 127.0.0.1:5182, API on 127.0.0.1:8765) ---
    location = /assets {
        return 301 /assets/;
    }
    location /assets/api/ {
        rewrite ^/assets(/api/.*)$ $1 break;
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /assets/asset/ {
        rewrite ^/assets(/asset/.*)$ $1 break;
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /assets/ {
        proxy_pass http://127.0.0.1:5182;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

EOF

TMP="$(mktemp)"
awk -v block="$BLOCK" '
  !done && /^[[:space:]]*location \/ \{/ { print block; done=1 }
  { print }
' "$CONF" > "$TMP"

if ! grep -q "location /assets/" "$TMP"; then
  echo "Could not find a 'location / {' anchor in $CONF to insert before." >&2
  rm -f "$TMP"
  exit 1
fi

cp "$TMP" "$CONF"
rm -f "$TMP"
echo "Inserted /assets/ proxy block into $CONF"

if ! nginx -t; then
  echo "nginx -t FAILED - restoring backup." >&2
  cp -p "$BACKUP" "$CONF"
  exit 1
fi

systemctl reload nginx
echo
echo "Done. Portrait Workbench is now at:"
echo "  https://desktop-g62m1s8.taild55c40.ts.net/assets/"
