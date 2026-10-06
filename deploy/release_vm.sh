#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-/home/ubuntu/seacommons}"
RELEASE_ROOT="${SEACOMMONS_RELEASE_ROOT:-/opt/seacommons}"
STATE_ROOT="${SEACOMMONS_STATE_ROOT:-/var/lib/seacommons}"
KEEP_RELEASES="${SEACOMMONS_KEEP_RELEASES:-5}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0 [repo]" >&2
  exit 2
fi

git -C "${REPO}" fetch origin main --quiet
SHA="$(git -C "${REPO}" rev-parse origin/main)"
RELEASE="${RELEASE_ROOT}/releases/${SHA}"

install -d -o root -g root "${RELEASE_ROOT}/releases"
install -d -o ubuntu -g ubuntu "${STATE_ROOT}" "${STATE_ROOT}/reference" "${STATE_ROOT}/reference/refreshed"

# Migrate mutable runtime state out of the checkout exactly once. Immutable
# releases must never boot with a fresh vessel registry or discard downloaded
# reference layers just because the code SHA changed.
if [[ ! -f "${STATE_ROOT}/vessels.db" && -f "${REPO}/apps/api/core/data/vessels.db" ]]; then
  install -o ubuntu -g ubuntu -m 0644 "${REPO}/apps/api/core/data/vessels.db" "${STATE_ROOT}/vessels.db"
fi
if [[ -d "${REPO}/apps/api/core/data/reference/refreshed" ]] && [[ -z "$(find "${STATE_ROOT}/reference/refreshed" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  cp -a "${REPO}/apps/api/core/data/reference/refreshed/." "${STATE_ROOT}/reference/refreshed/"
  chown -R ubuntu:ubuntu "${STATE_ROOT}/reference/refreshed"
fi
if [[ ! -f "${STATE_ROOT}/reference/navwarn_zones.json" && -f "${REPO}/apps/api/core/data/reference/navwarn_zones.json" ]]; then
  install -o ubuntu -g ubuntu -m 0644 "${REPO}/apps/api/core/data/reference/navwarn_zones.json" "${STATE_ROOT}/reference/navwarn_zones.json"
fi
touch "${STATE_ROOT}/reference/navwarn_zones.json"
chown ubuntu:ubuntu "${STATE_ROOT}/reference/navwarn_zones.json"

if [[ ! -d "${RELEASE}" ]]; then
  install -d -o root -g root "${RELEASE}"
  git -C "${REPO}" archive "${SHA}" | tar -x -C "${RELEASE}"
  rm -rf "${RELEASE}/apps/api/core/data/reference/refreshed"
  ln -s "${STATE_ROOT}/reference/refreshed" "${RELEASE}/apps/api/core/data/reference/refreshed"
  rm -f "${RELEASE}/apps/api/core/data/reference/navwarn_zones.json"
  ln -s "${STATE_ROOT}/reference/navwarn_zones.json" "${RELEASE}/apps/api/core/data/reference/navwarn_zones.json"
  chmod -R a-w "${RELEASE}"
fi

ln -sfn "${RELEASE}" "${RELEASE_ROOT}/current"

for unit in seacommons-api.service seacommons-worker.service seacommons-live-edge-publisher.service; do
  dropin="/etc/systemd/system/${unit}.d"
  install -d "${dropin}"
  cat >"${dropin}/10-immutable-release.conf" <<EOF
[Service]
WorkingDirectory=${RELEASE_ROOT}/current/apps/api
Environment=VESSEL_REGISTRY_DB_PATH=${STATE_ROOT}/vessels.db
EOF
done

systemctl daemon-reload
systemctl restart seacommons-api.service seacommons-worker.service seacommons-live-edge-publisher.service

# Keep current plus a small bounded rollback history.
mapfile -t releases < <(find "${RELEASE_ROOT}/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | awk '{print $2}')
if (( ${#releases[@]} > KEEP_RELEASES )); then
  for old in "${releases[@]:KEEP_RELEASES}"; do
    [[ "${old}" == "${RELEASE}" ]] || rm -rf -- "${old}"
  done
fi

echo "SeaCommons release active: ${SHA}"
systemctl --no-pager --full status seacommons-api.service | head -20
