#!/bin/sh
# Run as root, from an explicitly staged Day 13 directory. No credentials in bundle.
set -eu
[ "$(id -u)" = 0 ]
[ -f day13/app.py ]
[ -f day13/deploy/day13.service ]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/var/backups/day13-install-$stamp
mkdir -m 700 "$backup"
cp -a /etc/nginx/sites-available/default "$backup/nginx-default"
if [ -e /etc/nginx/snippets/day13.conf ]; then cp -a /etc/nginx/snippets/day13.conf "$backup/nginx-snippet"; fi
if [ -e /etc/nginx/conf.d/day13-limits.conf ]; then cp -a /etc/nginx/conf.d/day13-limits.conf "$backup/nginx-limits"; fi
if [ -e /etc/systemd/system/day13.service ]; then cp -a /etc/systemd/system/day13.service "$backup/day13.service"; fi
if [ -L /srv/day13/current ]; then readlink /srv/day13/current > "$backup/previous-release"; fi
rollback() {
    cp -a "$backup/nginx-default" /etc/nginx/sites-available/default
    if [ -f "$backup/nginx-snippet" ]; then
        cp -a "$backup/nginx-snippet" /etc/nginx/snippets/day13.conf
    else rm -f /etc/nginx/snippets/day13.conf; fi
    if [ -f "$backup/nginx-limits" ]; then
        cp -a "$backup/nginx-limits" /etc/nginx/conf.d/day13-limits.conf
    else rm -f /etc/nginx/conf.d/day13-limits.conf; fi
    if [ -f "$backup/previous-release" ]; then
        ln -sfn "$(cat "$backup/previous-release")" /srv/day13/current
    else rm -f /srv/day13/current; fi
    if [ -f "$backup/day13.service" ]; then
        cp -a "$backup/day13.service" /etc/systemd/system/day13.service
        systemctl daemon-reload
        systemctl restart day13
    else
        systemctl disable --now day13 2>/dev/null || true
        rm -f /etc/systemd/system/day13.service
        systemctl daemon-reload
    fi
    nginx -t && systemctl reload nginx
    echo 'Installation failed; previous application and nginx restored.' >&2
}
trap rollback EXIT
export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends python3-venv apache2-utils > "$backup/packages.log" 2>&1
id day13 >/dev/null 2>&1 || useradd --system --home-dir /var/lib/day13 --shell /usr/sbin/nologin day13
install -d -o root -g root -m 755 /srv/day13 /srv/day13/releases
install -d -o day13 -g day13 -m 700 /var/lib/day13
install -d -o root -g www-data -m 750 /etc/day13
release=/srv/day13/releases/$stamp
mkdir -m 755 "$release"
python3 -m venv "$release/.venv"
"$release/.venv/bin/pip" install --only-binary=:all: -r day13/requirements.txt > "$backup/dependencies.log" 2>&1
cp -R day13 "$release/day13"
chown -R root:root "$release"
chmod -R go-w "$release"
if [ ! -f /etc/day13/deepseek.cred ]; then
    printf UNCONFIGURED | systemd-creds encrypt --name=deepseek - /etc/day13/deepseek.cred >/dev/null 2>&1
fi
if [ ! -f /etc/day13/ip-hmac.cred ]; then
    python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_hex(32))' | systemd-creds encrypt --name=ip-hmac - /etc/day13/ip-hmac.cred >/dev/null 2>&1
fi
chmod 600 /etc/day13/*.cred
if [ ! -f /etc/day13/access.htpasswd ]; then
    # Empty file denies every login until interactive provisioning.
    install -o root -g www-data -m 640 /dev/null /etc/day13/access.htpasswd
fi
install -o root -g root -m 700 day13/deploy/set_credentials.py /usr/local/sbin/day13-set-credentials
install -o root -g root -m 644 day13/deploy/day13.service /etc/systemd/system/day13.service
install -o root -g root -m 644 day13/deploy/nginx-location.conf /etc/nginx/snippets/day13.conf
printf 'limit_req_zone $binary_remote_addr zone=day13_edge:1m rate=2r/s;\n' > /etc/nginx/conf.d/day13-limits.conf
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/sites-available/default'); s=p.read_text()
include='    include /etc/nginx/snippets/day13.conf;'
if include not in s:
    needle='    listen 443 ssl http2 default_server;'
    if s.count(needle)!=1: raise SystemExit('Ambiguous TLS server, refusing edit')
    s=s.replace(needle,needle+'\n'+include)
    p.write_text(s)
PY
ln -sfn "$release" /srv/day13/current
systemd-analyze verify /etc/systemd/system/day13.service
nginx -t
systemctl daemon-reload
systemctl enable --now day13
systemctl restart day13
sleep 2
systemctl is-active --quiet day13
curl --fail --silent -H 'X-Day13-IP: 127.0.0.1' http://127.0.0.1:8130/day13/api/limits >/dev/null
systemctl reload nginx
trap - EXIT
printf 'Day13 installed. Credential provisioning pending if not configured.\n'
