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

# Clean first. NOTE: lb clean --purge only wipes the chroot/build stages,
# NOT config/includes.chroot — stale files there survive every clean.
if [[ "${CLEAN}" == "1" ]]; then
  lb clean noauto --purge || true
fi

# includes.chroot accumulates stale files across builds (files deleted from the
# repo are never deleted here by the copy steps below, and lb clean doesn't touch
# this dir). Sweep every path that is fully re-created below so the repo is the
# single source of truth. (usr/local/share/cis4900-src is hash-managed separately.)
rm -rf "${LB_WORKDIR}/config/includes.chroot/lib/live/config"
rm -rf "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system"

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

# extra apt sources for the chroot (bookworm-backports kernel/firmware)
mkdir -p "${LB_WORKDIR}/config/archives"
cp "${BUILD_DIR}/archives/backports.list.chroot" \
   "${LB_WORKDIR}/config/archives/backports.list.chroot"

# pin the kernel/firmware family to bookworm-backports, see build/inject/99-bookworm-backports.pref
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/apt/preferences.d"
cp "${BUILD_DIR}/inject/99-bookworm-backports.pref" \
   "${LB_WORKDIR}/config/includes.chroot/etc/apt/preferences.d/99-bookworm-backports.pref"

# custom GRUB live boot menu entry, overlaid on live-build's default bootloader templates
rm -rf "${LB_WORKDIR}/config/bootloaders"
cp -r /usr/share/live/build/bootloaders "${LB_WORKDIR}/config/bootloaders"
cp "${BUILD_DIR}/inject/grub-live-menu.cfg" \
   "${LB_WORKDIR}/config/bootloaders/grub-pc/grub.cfg"

# the installer script itself
mkdir -p "${LB_WORKDIR}/config/includes.chroot/usr/local/sbin"
cp "${BUILD_DIR}/inject/ychitsa-install" \
   "${LB_WORKDIR}/config/includes.chroot/usr/local/sbin/ychitsa-install"
chmod +x "${LB_WORKDIR}/config/includes.chroot/usr/local/sbin/ychitsa-install"

# systemd unit that runs the installer on tty1 when the Install GRUB entry is selected
# (ConditionKernelCommandLine=ychitsa.installer=1 keeps it inert on all other boots)
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system"
cp "${BUILD_DIR}/inject/ychitsa-installer.service" \
   "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system/ychitsa-installer.service"

# cap live-config's start time so a wedged component can never hang boot forever
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system/live-config.service.d"
cp "${BUILD_DIR}/inject/live-config-timeout.conf" \
   "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system/live-config.service.d/timeout.conf"

# GPU fallback tier scripts and the systemd units that run them, see build/inject/gpu/
cp "${BUILD_DIR}/inject/gpu/ychitsa-gpu-tier" \
   "${LB_WORKDIR}/config/includes.chroot/usr/local/sbin/ychitsa-gpu-tier"
cp "${BUILD_DIR}/inject/gpu/ychitsa-gpu-recover" \
   "${LB_WORKDIR}/config/includes.chroot/usr/local/sbin/ychitsa-gpu-recover"
chmod +x "${LB_WORKDIR}/config/includes.chroot/usr/local/sbin/ychitsa-gpu-tier" \
         "${LB_WORKDIR}/config/includes.chroot/usr/local/sbin/ychitsa-gpu-recover"

mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system"
cp "${BUILD_DIR}/inject/gpu/ychitsa-gpu-stage.service" \
   "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system/ychitsa-gpu-stage.service"
cp "${BUILD_DIR}/inject/gpu/ychitsa-gpu-confirm.service" \
   "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system/ychitsa-gpu-confirm.service"
cp "${BUILD_DIR}/inject/gpu/ychitsa-gpu-recover.service" \
   "${LB_WORKDIR}/config/includes.chroot/etc/systemd/system/ychitsa-gpu-recover.service"

# inject files into their /etc/ destination paths inside the chroot
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/lightdm"
cp "${BUILD_DIR}/inject/lightdm.conf" \
   "${LB_WORKDIR}/config/includes.chroot/etc/lightdm/lightdm.conf"
# Do not install an always-on Xorg fbdev Device section. That forced software
# rendering (llvmpipe) even when amdgpu worked. See build/HARDWARE.md.
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/X11/xorg.conf.d"
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/NetworkManager/conf.d"
cp "${BUILD_DIR}/inject/nm-managed.conf" \
   "${LB_WORKDIR}/config/includes.chroot/etc/NetworkManager/conf.d/10-managed.conf"
mkdir -p "${LB_WORKDIR}/config/includes.chroot/etc/polkit-1/rules.d"
cp "${BUILD_DIR}/inject/10-network-manager.rules" \
   "${LB_WORKDIR}/config/includes.chroot/etc/polkit-1/rules.d/10-network-manager.rules"

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

# grub-efi-amd64-signed became essential in bookworm so we patch live-build so binary_grub-efi can remove it
sed -i 's/apt-get remove --auto-remove --purge/apt-get remove --allow-remove-essential --auto-remove --purge/' \
    /usr/share/live/build/functions/packages.sh

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
