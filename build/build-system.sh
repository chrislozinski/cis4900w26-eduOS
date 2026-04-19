#!/usr/bin/env bash
set -euo pipefail

MODE=""
CLEAN=0
DEBUG=0
FIRMWARE="on"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --clean)
      CLEAN=1
      shift
      ;;
    --debug)
      DEBUG=1
      shift
      ;;
    --firmware)
      FIRMWARE="${2:-on}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${MODE}" ]]; then
  echo "Usage: $0 --mode docker|iso [--clean] [--debug] [--firmware on|off]" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/build"

if [[ "${DEBUG}" == "1" ]]; then
  set -x
fi

if [[ "${MODE}" == "docker" ]]; then
  exec "${BUILD_DIR}/build-docker.sh"
fi

if [[ "${MODE}" != "iso" ]]; then
  echo "Invalid --mode: ${MODE}" >&2
  exit 1
fi

# live-build must run on a native Linux ext4 filesystem
# /mnt/c/... is Windows NTFS and does not support mknod (device files)
# LB_WORKDIR is on ext4; everything is mapped from the repo each build.
LB_WORKDIR="${HOME}/cis4900-lb-workdir"
DIST_DIR="${ROOT_DIR}/dist"
mkdir -p "${LB_WORKDIR}" "${DIST_DIR}"

cd "${LB_WORKDIR}"

# Clean first: lb clean --purge wipes config/ and auto/ entirely,
# so all mapping must happen AFTER the clean.
if [[ "${CLEAN}" == "1" ]]; then
  lb clean noauto --purge || true
fi

# live-build lifecycle scripts
mkdir -p "${LB_WORKDIR}/auto"
cp "${BUILD_DIR}/live-build/config" "${LB_WORKDIR}/auto/config"
cp "${BUILD_DIR}/live-build/build"  "${LB_WORKDIR}/auto/build"
cp "${BUILD_DIR}/live-build/clean"  "${LB_WORKDIR}/auto/clean"
chmod +x "${LB_WORKDIR}/auto/config" "${LB_WORKDIR}/auto/build" "${LB_WORKDIR}/auto/clean"

# package lists
mkdir -p "${LB_WORKDIR}/config/package-lists"
cp "${BUILD_DIR}/packages/base.list" "${LB_WORKDIR}/config/package-lists/live.list.chroot"
cp "${BUILD_DIR}/packages/apps.list" "${LB_WORKDIR}/config/package-lists/cis4900.list.chroot"

# debian-installer files (udeb_exclude must exist or older live-build versions error)
mkdir -p "${LB_WORKDIR}/config/debian-installer"
touch    "${LB_WORKDIR}/config/debian-installer/exclude"
cp "${BUILD_DIR}/inject/udeb_exclude" "${LB_WORKDIR}/config/debian-installer/udeb_exclude"

# inject files into their /etc/ destination paths inside the chroot
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/lightdm"
cp "${BUILD_DIR}/inject/lightdm.conf" \
   "${LB_WORKDIR}/config/includes.chroot/etc/lightdm/lightdm.conf"
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/X11/xorg.conf.d"
cp "${BUILD_DIR}/inject/gpu.conf" \
   "${LB_WORKDIR}/config/includes.chroot/etc/X11/xorg.conf.d/20-fbdev.conf"
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/NetworkManager/conf.d"
cp "${BUILD_DIR}/inject/nm-managed.conf" \
   "${LB_WORKDIR}/config/includes.chroot/etc/NetworkManager/conf.d/10-managed.conf"

# hooks: live-build requires 0XXX-*.hook.chroot convention
HOOKS_DEST="${LB_WORKDIR}/config/hooks/live"
mkdir -p "${HOOKS_DEST}"
cp "${BUILD_DIR}/hooks/01-waterfox.sh"    "${HOOKS_DEST}/0050-install-waterfox.hook.chroot"
cp "${BUILD_DIR}/hooks/02-build-i3.sh"    "${HOOKS_DEST}/0060-build-patched-i3.hook.chroot"
cp "${BUILD_DIR}/hooks/03-copy-assets.sh" "${HOOKS_DEST}/0100-copy-project-assets.hook.chroot"
cp "${BUILD_DIR}/hooks/04-user-setup.sh"  "${HOOKS_DEST}/0200-run-user-and-ui-setup.hook.chroot"
cp "${BUILD_DIR}/hooks/05-services.sh"    "${HOOKS_DEST}/0300-enable-services.hook.chroot"
chmod +x "${HOOKS_DEST}/"*

# project sources — hash-checked so we only rsync when src/debian-base1 actually changed.
# makecode-static has paths >260 chars which cause I/O errors on NTFS, so
# this always runs from the Linux side directly into the ext4 workdir.
INCLUDES_DIR="${LB_WORKDIR}/config/includes.chroot/usr/local/share/cis4900-src"
NEW_HASH=$(find "${ROOT_DIR}/src/debian-base1" -type f -print0 \
    | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')
HASH_FILE="${LB_WORKDIR}/.src-hash"
if [[ ! -f "${HASH_FILE}" ]] || [[ "$(cat "${HASH_FILE}")" != "${NEW_HASH}" ]]; then
    echo "Source changed — syncing debian-base1..."
    mkdir -p "${INCLUDES_DIR}/src"
    rsync -a --delete "${ROOT_DIR}/src/debian-base1/" "${INCLUDES_DIR}/src/debian-base1/"
    echo "${NEW_HASH}" > "${HASH_FILE}"
else
    echo "Source unchanged — skipping copy."
fi

if [[ "${FIRMWARE}" == "off" ]]; then
  sed -i 's/non-free non-free-firmware/non-free/' "${LB_WORKDIR}/auto/config"
fi

# i3 binary cache, inject pre-built binary to skip 3-8 min compilation.
# Cache persists in LB_WORKDIR across builds. Use --clean to force a rebuild
# when the patches in hooks/02-build-i3.sh change.
I3_CACHE="${LB_WORKDIR}/cache/i3/i3"
I3_INJECT="${LB_WORKDIR}/config/includes.chroot/usr/local/bin/i3"
if [[ -f "${I3_CACHE}" ]]; then
    echo "Injecting cached i3 binary — skipping compilation."
    mkdir -p "$(dirname "${I3_INJECT}")"
    cp "${I3_CACHE}" "${I3_INJECT}" && chmod +x "${I3_INJECT}"
fi

# lb build calls auto/config and auto/build automatically.
lb build

# save i3 binary to cache for future builds
if [[ -f "${LB_WORKDIR}/chroot/usr/local/bin/i3" ]]; then
    mkdir -p "${LB_WORKDIR}/cache/i3"
    cp "${LB_WORKDIR}/chroot/usr/local/bin/i3" "${I3_CACHE}"
fi

if ls ./*.iso >/dev/null 2>&1; then
  cp -f ./*.iso "${DIST_DIR}/cis4900-live.iso"
  echo "ISO written to ${DIST_DIR}/cis4900-live.iso"
fi
