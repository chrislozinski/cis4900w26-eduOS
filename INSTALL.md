# Installing Ychitsa OS to Disk

## What You Need
- Flashed USB with the built ISO
- Laptop with internal drive to install to

---

## Step 1 — Boot from USB

Enter BIOS. Set USB as first boot priority. Save and reboot with USB plugged in.

---

## Step 2 — Installer

At the GRUB menu select **Install Ychitsa OS**.

Pick the target disk from the list. Confirm the warning. The installer partitions the disk, clones the live filesystem onto it, and installs the bootloader with no further prompts.

When it says the install is complete, remove the USB and reboot.

---

## What changed from the old installer

The Debian Installer is gone. `ychitsa-install` (`build/inject/ychitsa-install`) does the same job the old GRUB "Start installer" entry used to, but as a script instead of a multi-screen wizard: partition the disk, unsquash the live filesystem straight onto it, install the bootloader, done. The "Install Ychitsa OS" GRUB entry boots straight to text mode (`systemd.unit=multi-user.target`, so no desktop or display manager ever starts) and a systemd unit (`build/inject/ychitsa-installer.service`, gated on the `ychitsa.installer=1` boot parameter) runs the installer directly on tty1. If an install boot ever hangs, `Ctrl+Alt+F9` opens a root debug shell (`systemd.debug-shell=1` is set on that entry) — run `systemctl list-jobs` there to see what is stuck.

Both GRUB failures the old installer used to hit (the `grub-efi-amd64-signed` essential-package bug and the missing `grub-efi-amd64` package at install time) are structurally gone: there's no more Debian Installer running its own separate bootloader-install step, and `grub-efi-amd64`, `grub-common`, and `dosfstools` are all baked into `apps.list` so the installer's own `grub-install`/`grub-mkconfig` calls never depend on a network fetch.

First-boot GPU black screens should also no longer need a manual fix. See `build/README.md`, `build/HARDWARE.md`, and the GPU fallback tier system (`build/inject/gpu/ychitsa-gpu-tier`) for how the OS now tests for working acceleration itself and falls back automatically instead of requiring a manual `nomodeset` edit.

---

## After install: updates

The updater binary is on PATH as `ychitsa-update` (`/usr/local/bin`), not in your home folder.

```bash
sudo ychitsa-update
```

It needs a git checkout at `/opt/cis4900-repo`. Fresh installs try to clone that when network is available. If install was offline, seed it once from the public GitHub repo (not the school GitLab URL):

```bash
sudo git clone https://github.com/chrislozinski/cis4900w26-eduOS.git /opt/cis4900-repo
sudo ychitsa-update
```

More hardware, GPU, hostname, and quiet-boot notes: `build/HARDWARE.md`.
