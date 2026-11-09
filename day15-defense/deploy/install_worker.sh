#!/bin/sh
set -eu
[ "$(id -u)" = 0 ]
[ -f server/worker.py ] && [ -f sandbox/check.py ]
stamp=$(date -u +%Y%m%dT%H%M%SZ)
release=/srv/day15-defense/releases/$stamp
backup=/var/backups/day15-defense-install-$stamp
mkdir -m 700 "$backup"
systemctl show day13 day14-v2 x-ui nginx -p Id -p MainPID -p ActiveEnterTimestamp > "$backup/protected-services"
sha256sum /etc/vps-firewall.nft /etc/systemd/system/day13.service /etc/systemd/system/day14-v2.service > "$backup/protected-sha256"
if [ -L /srv/day15-defense/current ]; then readlink /srv/day15-defense/current > "$backup/previous-release"; fi
install -d -m 755 /srv/day15-defense /srv/day15-defense/releases "$release"
install -d -m 700 /var/lib/day15-defense
cp -R runner server sandbox tools tests integration redteam api "$release/"
cp requirements-api.txt requirements-worker.txt "$release/"
python3 -m venv "$release/runtime"
"$release/runtime/bin/pip" install --only-binary=:all: --disable-pip-version-check -r requirements-worker.txt -r requirements-api.txt > "$backup/dependencies.log" 2>&1
chown -R root:root "$release"
chmod -R a+rX "$release"
chmod -R go-w "$release"
(cd "$release" && python3 -m unittest tests.test_snapshots tests.test_sandbox tests.test_gate tests.test_store tests.test_accept tests.test_loop tests.test_action_policy tests.test_gateway_client tests.test_hardening -v) > "$backup/tests.log" 2>&1
sha256sum -c "$backup/protected-sha256"
ln -s "$release" /srv/day15-defense/current.next
mv -Tf /srv/day15-defense/current.next /srv/day15-defense/current
printf 'Worker release: %s\nBackup: %s\n' "$release" "$backup"
