# Hardware notes (real laptop testing)

Plain notes from installs on the test Lenovo laptop so we do not re-guess later.

## Machine

- Class: Lenovo IdeaPad style laptop
- CPU / GPU: AMD A9 class, Stoney Ridge, Radeon R5 graphics
- Firmware: UEFI
- Secure Boot was off during the successful install and boot tests
- Early boots were confusing when PXE/network boot was first in the BIOS order

## Install

- Use the custom installer (`ychitsa-install`), not the Debian Installer
- GRUB entry: Install Ychitsa OS
- Success looks like: disk picker, partition, clone, then reboot off the internal drive to LightDM

## GPU (important)

### What we proved

- At `ychitsa.gpu_tier=0`, the `amdgpu` kernel module loads
- With the old always-on Xorg fbdev config, OpenGL was `llvmpipe` (CPU software). Desktop felt very slow
- After removing `/etc/X11/xorg.conf.d/20-fbdev.conf`, `glxinfo` showed:

```
direct rendering: Yes
OpenGL renderer string: AMD Radeon R5 Graphics (stoney, ...)
```

So this chip can do real hardware acceleration. Do not ship that always-on fbdev Xorg file again.

### Why `gpu.conf` existed

Added April 2026 when the live ISO first worked. Early Stoney boots sometimes black-screened, so X was forced to the `fbdev` driver for a guaranteed picture. That was before the GPU tier system. It was left in place by mistake and blocked acceleration even when amdgpu worked.

### Tier list (kernel cmdline only)

0. Full acceleration (empty extra params)
1. `amdgpu.dc=0`
2. `amdgpu.dc=0 iommu=soft`
3. `nomodeset modprobe.blacklist=amdgpu` (last resort)

Tier 3 is the safety net if a future machine cannot run amdgpu. That is separate from the old Xorg fbdev file.

### How to check on a machine

```bash
cat /proc/cmdline
lsmod | grep amdgpu
glxinfo | grep -iE 'direct rendering|OpenGL renderer'
grep -E 'Driver|fbdev|AMD|modeset' /var/log/Xorg.0.log | head -40
cat /var/log/ychitsa-gpu-boot.log 2>/dev/null
ls /etc/ychitsa/
```

Wanted on a healthy Stoney box: amdgpu loaded, glxinfo shows AMD Radeon R5 / stoney, not llvmpipe.

### Boot time note

`ychitsa-gpu-stage` and `ychitsa-gpu-confirm` used to call `update-grub` every boot (tens of seconds). After a good tier 0 confirm, the system pins with `/etc/ychitsa/gpu-tier-pinned` so those units stop. If you need the tier system again: `sudo rm /etc/ychitsa/gpu-tier-pinned` and reboot.

## Hostname

Hostname is `ychitsa`. `/etc/hosts` must include `127.0.1.1 ychitsa` or sudo prints `unable to resolve host ychitsa`.

## Updater

Command (on PATH, not in your home folder):

```bash
sudo ychitsa-update
```

Needs a git checkout at `/opt/cis4900-repo` from:

```bash
sudo git clone https://github.com/chrislozinski/cis4900w26-eduOS.git /opt/cis4900-repo
```

Fresh installs try to seed that clone when network is up. If install was offline, run the clone by hand once.

## Quiet boot

Installed systems should hide the blue GRUB menu (`GRUB_TIMEOUT=0`, `GRUB_TIMEOUT_STYLE=hidden`) and use `quiet` on the kernel cmdline. Hold Shift (BIOS) or Esc (UEFI) at power-on if you need the GRUB menu for recovery.

## Quick fixes on an already-installed box (before the next ISO)

```bash
# GPU (if still on fbdev)
sudo mv /etc/X11/xorg.conf.d/20-fbdev.conf /root/20-fbdev.conf.bak 2>/dev/null || true
sudo systemctl restart lightdm

# Hostname warning
echo '127.0.1.1 ychitsa' | sudo tee -a /etc/hosts

# Silent GRUB + quiet cmdline (until next ISO bake)
sudo sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=0/' /etc/default/grub
grep -q '^GRUB_TIMEOUT_STYLE=' /etc/default/grub \
  && sudo sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=hidden/' /etc/default/grub \
  || echo 'GRUB_TIMEOUT_STYLE=hidden' | sudo tee -a /etc/default/grub
sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet loglevel=3 ychitsa.gpu_tier=0"/' /etc/default/grub
sudo update-grub

# Updater
sudo git clone https://github.com/chrislozinski/cis4900w26-eduOS.git /opt/cis4900-repo
sudo ychitsa-update

# Pin GPU tier after a good boot (skips stage/confirm update-grub cost)
sudo mkdir -p /etc/ychitsa
sudo touch /etc/ychitsa/gpu-tier-pinned
```
