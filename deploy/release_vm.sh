#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-/home/ubuntu/seacommons}"
RELEASE_ROOT="${SEACOMMONS_RELEASE_ROOT:-/opt/seacommons}"
KEEP_RELEASES="${SEACOMMONS_KEEP_RELEASES:-5}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0 [repo]" >&2
  exit 2
fi

git -C "${REPO}" fetch origin main --quiet
SHA="$(git -C "${REPO}" rev-parse origin/main)"
RELEASE="${RELEASE_ROOT}/releases/${SHA}"

install -d -o root -g root "${RELEASE_ROOT}/releases"
if [[ ! -d "${RELEASE}" ]]; then
  install -d -o root -g root "${RELEASE}"
  git -C "${REPO}" archive "${SHA}" | tar -x -C "${RELEASE}"
  chmod -R a-w "${RELEASE}"
fi

ln -sfn "${RELEASE}" "${RELEASE_ROOT}/current"

for unit in seacommons-api.service seacommons-worker.service seacommons-live-edge-publisher.service; do
  dropin="/etc/systemd/system/${unit}.d"
  install -d "${dropin}"
  cat >"${dropin}/10-immutable-release.conf" <<EOF
[Service]
WorkingDirectory=${RELEASE_ROOT}/current/apps/api
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
