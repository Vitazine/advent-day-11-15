#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
[ -f api/app.py ] && [ -f api-tokens.json ] && [ -f gateway-token ]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/var/backups/day15-api-install-$stamp
mkdir -m 700 "$backup"
cp -a /etc/nginx/sites-available/default "$backup/nginx-default"
readlink /srv/day15-defense/current > "$backup/previous-release"
systemctl show day13 day14-v2 x-ui nginx -p Id -p MainPID -p ActiveEnterTimestamp > "$backup/protected-services"
sha256sum /etc/vps-firewall.nft /etc/systemd/system/day13.service /etc/systemd/system/day14-v2.service > "$backup/protected-sha256"
for file in /etc/systemd/system/day15-api.service /etc/systemd/system/day15-executor.service /etc/nginx/snippets/day15-api.conf /etc/nginx/conf.d/day15-limits.conf; do
 if [ -f "$file" ]; then cp -a "$file" "$backup/$(basename "$file")"; fi
done
if [ -d /etc/day15-api ]; then cp -a /etc/day15-api "$backup/credentials"; fi
rollback() {
 systemctl stop day15-api day15-executor 2>/dev/null || true
 cp -a "$backup/nginx-default" /etc/nginx/sites-available/default
 for file in /etc/systemd/system/day15-api.service /etc/systemd/system/day15-executor.service /etc/nginx/snippets/day15-api.conf /etc/nginx/conf.d/day15-limits.conf; do
  if [ -f "$backup/$(basename "$file")" ]; then cp -a "$backup/$(basename "$file")" "$file"; else rm -f "$file"; fi
 done
 ln -sfn "$(cat "$backup/previous-release")" /srv/day15-defense/current
 if [ -d "$backup/credentials" ]; then cp -a "$backup/credentials/." /etc/day15-api/; else rm -f /etc/day15-api/tokens.json /etc/day15-api/gateway-token; fi
 if [ ! -f "$backup/day15-api.service" ]; then systemctl disable day15-api day15-executor 2>/dev/null || true; fi
 systemctl daemon-reload
 if [ -f "$backup/day15-api.service" ]; then systemctl start day15-executor day15-api; fi
 nginx -t && systemctl reload nginx
}
trap rollback EXIT
id day15api >/dev/null 2>&1 || useradd --system --home-dir /var/lib/day15-api --shell /usr/sbin/nologin day15api
systemctl stop day15-api day15-executor 2>/dev/null || true
sh deploy/install_worker.sh
release=$(readlink /srv/day15-defense/current)
(cd "$release" && "$release/runtime/bin/python" -m unittest tests.test_partner_api tests.test_native_generator -v) > "$backup/api-tests.log" 2>&1
install -d -o root -g day15api -m 750 /etc/day15-api
install -o root -g day15api -m 640 api-tokens.json /etc/day15-api/tokens.json
install -o root -g day15api -m 640 gateway-token /etc/day15-api/gateway-token
install -o root -g root -m 644 deploy/day15-api.service /etc/systemd/system/day15-api.service
install -o root -g root -m 644 deploy/day15-executor.service /etc/systemd/system/day15-executor.service
install -o root -g root -m 644 deploy/nginx-api.conf /etc/nginx/snippets/day15-api.conf
printf 'limit_req_zone $binary_remote_addr zone=day15_edge:1m rate=2r/s;\n' > /etc/nginx/conf.d/day15-limits.conf
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/sites-available/default');text=p.read_text();include='    include /etc/nginx/snippets/day15-api.conf;'
if include not in text:
 needle='    listen 443 ssl http2 default_server;'
 if text.count(needle)!=1:raise SystemExit('Ambiguous server')
 p.write_text(text.replace(needle,needle+'\n'+include))
PY
systemd-analyze verify /etc/systemd/system/day15-api.service /etc/systemd/system/day15-executor.service
nginx -t
systemctl daemon-reload
systemctl enable --now day15-executor day15-api
sleep 2
python3 - <<'PY'
import urllib.request,urllib.error
try:urllib.request.urlopen('http://127.0.0.1:8151/v1/limits',timeout=10)
except urllib.error.HTTPError as e:assert e.code==401
else:raise SystemExit('Missing auth gate')
PY
systemctl reload nginx
sha256sum -c "$backup/protected-sha256"
trap - EXIT
printf 'API deployment backup: %s\n' "$backup"
