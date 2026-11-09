#!/bin/sh
# Root-only deployment of explicitly staged files. No plaintext provider key.
set -eu
[ "$(id -u)" = 0 ]
[ -f gateway/app.py ] && [ -f deploy/day14-v2.service ] && [ -f client-verifiers.json ]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/var/backups/day14-v2-install-$stamp
release=/srv/day14-v2/releases/$stamp
mkdir -m 700 "$backup"
cp -a /etc/nginx/sites-available/default "$backup/nginx-default"
for item in /etc/nginx/snippets/day14-v2.conf /etc/nginx/conf.d/day14-v2-limits.conf /etc/systemd/system/day14-v2.service; do
    if [ -f "$item" ]; then cp -a "$item" "$backup/$(basename "$item")"; fi
done
if [ -L /srv/day14-v2/current ]; then readlink /srv/day14-v2/current > "$backup/previous-release"; fi
if [ -f /etc/day14-v2/tokens.json ]; then cp -a /etc/day14-v2/tokens.json "$backup/tokens.json"; fi
systemctl show day13 x-ui --property=Id,MainPID,ActiveEnterTimestamp > "$backup/protected-services"
sha256sum /etc/vps-firewall.nft /etc/systemd/system/day13.service > "$backup/protected-sha256"
rollback() {
    cp -a "$backup/nginx-default" /etc/nginx/sites-available/default
    for item in /etc/nginx/snippets/day14-v2.conf /etc/nginx/conf.d/day14-v2-limits.conf /etc/systemd/system/day14-v2.service; do
        if [ -f "$backup/$(basename "$item")" ]; then cp -a "$backup/$(basename "$item")" "$item"; else rm -f "$item"; fi
    done
    if [ -f "$backup/tokens.json" ]; then cp -a "$backup/tokens.json" /etc/day14-v2/tokens.json; fi
    if [ -f "$backup/previous-release" ]; then
        ln -sfn "$(cat "$backup/previous-release")" /srv/day14-v2/current
        systemctl daemon-reload
        systemctl restart day14-v2
    else
        systemctl disable --now day14-v2 2>/dev/null || true
        rm -f /srv/day14-v2/current
        systemctl daemon-reload
    fi
    nginx -t && systemctl reload nginx
    printf 'Deployment failed; previous configuration restored.\n' >&2
}
trap rollback EXIT
id day14v2 >/dev/null 2>&1 || useradd --system --home-dir /var/lib/day14-v2 --shell /usr/sbin/nologin day14v2
install -d -o root -g root -m 755 /srv/day14-v2 /srv/day14-v2/releases
install -d -o root -g root -m 700 /etc/day14-v2
install -d -o day14v2 -g day14v2 -m 700 /var/lib/day14-v2
mkdir -m 755 "$release"
python3 -m venv "$release/.venv"
"$release/.venv/bin/pip" install --disable-pip-version-check --only-binary=:all: -r requirements.txt > "$backup/dependencies.log" 2>&1
cp -R gateway tests tools "$release/"
cp requirements.txt openapi.json "$release/"
chown -R root:root "$release"
chmod -R a+rX "$release"
chmod -R go-w "$release"
(cd "$release" && runuser -u day14v2 -- "$release/.venv/bin/python" -m unittest discover -s tests -p 'test_*.py' -v) > "$backup/linux-tests.log" 2>&1
# Same encrypted credential name and machine; plaintext never leaves systemd.
if [ ! -f /etc/day14-v2/deepseek.cred ]; then install -o root -g root -m 600 /etc/day13/deepseek.cred /etc/day14-v2/deepseek.cred; fi
install -o root -g root -m 600 client-verifiers.json /etc/day14-v2/tokens.json
install -o root -g root -m 644 deploy/day14-v2.service /etc/systemd/system/day14-v2.service
install -o root -g root -m 644 deploy/nginx-location.conf /etc/nginx/snippets/day14-v2.conf
printf 'limit_req_zone $binary_remote_addr zone=day14v2_edge:1m rate=2r/s;\n' > /etc/nginx/conf.d/day14-v2-limits.conf
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/sites-available/default');s=p.read_text()
include='    include /etc/nginx/snippets/day14-v2.conf;'
if include not in s:
    needle='    listen 443 ssl http2 default_server;'
    if s.count(needle)!=1:raise SystemExit('Ambiguous TLS server; refusing mutation')
    p.write_text(s.replace(needle,needle+'\n'+include))
PY
ln -sfn "$release" /srv/day14-v2/current
systemd-analyze verify /etc/systemd/system/day14-v2.service
nginx -t
systemctl daemon-reload
systemctl enable --now day14-v2
systemctl restart day14-v2
ready=false
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    code=$(curl --silent --max-time 2 --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8141/v1/models || true)
    if [ "$code" = 401 ]; then ready=true; break; fi
    sleep 1
done
[ "$ready" = true ]
systemctl is-active --quiet day14-v2
systemctl reload nginx
sha256sum -c "$backup/protected-sha256" >/dev/null
trap - EXIT
printf 'Deployed release: %s\nRollback baseline: %s\n' "$release" "$backup"
