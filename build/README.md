# Build

Run from the repo root:

```bash
sudo bash -x ./build/build-system.sh --mode iso
sudo bash -x ./build/build-system.sh --mode iso --clean   
sudo bash -x ./build/build-system.sh --mode docker
```

## File Function

### `build-system.sh`
The main entry point. It maps all the files from `build/` into a live-build workdir at `~/cis4900-lb-workdir` (Linux ext4, outside the repo, required because Windows NTFS doesn't support `mknod` which live-build needs for device files). Nothing generated ever lands back in `build/`.

### `live-build/`
Three scripts that live-build (`lb`) **requires** to exist at `auto/config`, `auto/build`, and `auto/clean` in its workdir. live-build calls them automatically, in order, when you run `lb build`, they're never called directly

- **`config`** - tells live-build what to build: Debian Bookworm amd64, hybrid ISO (boots from USB or DVD), apt sources include non-free firmware for AMD/WiFi drivers. Boot parameters default to `ychitsa.gpu_tier=0` (full acceleration attempted first). See `ychitsa-gpu-tier` below for how it falls back automatically instead of a permanent amdgpu blacklist.
- **`build`** - runs `lb build noauto`. `noauto` prevents an infinite loop (lb would otherwise call this script recursively).
- **`clean`** - runs `lb clean --purge`. NOTE: this only wipes the chroot/build stages, NOT `config/includes.chroot` — `build-system.sh` sweeps the stale-able paths in there itself (`lib/live/config`, `etc/systemd/system`) at the start of every run, so files deleted from `build/inject/` actually disappear from the next ISO.

### `archives/`
Extra apt sources added to the chroot beyond the main Bookworm mirror.
- `backports.list.chroot` - enables `bookworm-backports`, used to pull a newer kernel and `firmware-amd-graphics` build than Bookworm main ships. See "GPU acceleration" below for why.

### `packages/`
APT package lists installed into the OS.
- `base.list` - live-boot/live-config system packages
- `apps.list` - everything else: i3, pipewire, GTK, Waterfox deps, the kernel and firmware (see `99-bookworm-backports.pref` in `inject/` for how these resolve to backports), etc.

### `inject/`
Files dropped directly into the built OS filesystem, or used to override live-build's own default templates, before packages run.
- `lightdm.conf` -> `/etc/lightdm/lightdm.conf` (autologin config)
- `gpu.conf` -> `/etc/X11/xorg.conf.d/20-fbdev.conf` (fbdev fallback driver, only takes effect at GPU tier 3)
- `99-bookworm-backports.pref` -> `/etc/apt/preferences.d/99-bookworm-backports.pref`, pins the kernel/firmware package family to `bookworm-backports` so the whole dependency chain (including packages live-build's own `chroot_firmware` stage adds automatically, like `firmware-linux-nonfree`) resolves consistently from one suite instead of mixing main and backports
- `grub-live-menu.cfg` -> overlays live-build's default `config/bootloaders/grub-pc/grub.cfg`, adding the "Install Ychitsa OS" boot menu entry
- `ychitsa-install` -> `/usr/local/sbin/ychitsa-install`, the installer script (partition, clone the live filesystem to disk, install the bootloader)
- `ychitsa-installer.service` -> `/etc/systemd/system/ychitsa-installer.service`, runs the installer on tty1. Inert on every boot except the "Install Ychitsa OS" GRUB entry (`ConditionKernelCommandLine=ychitsa.installer=1`); that entry also boots `multi-user.target` so no desktop, display manager, or GPU tier units ever start during an install
- `gpu/` - the GPU fallback tier system, kept in its own subfolder since it's five files:
  - `ychitsa-gpu-tier` -> `/usr/local/sbin/ychitsa-gpu-tier`, the fallback tier system itself
  - `ychitsa-gpu-recover` -> `/usr/local/sbin/ychitsa-gpu-recover`, opportunistic online GPU repair for hardware not yet diagnosed
  - `ychitsa-gpu-stage.service` / `ychitsa-gpu-confirm.service` / `ychitsa-gpu-recover.service` -> `/etc/systemd/system/`, enabled by `hooks/05-services.sh`

### `hooks/`
Scripts run **inside the chroot** by live-build after packages are installed, in numeric order.
- `01-waterfox.sh` - downloads and installs Waterfox and uBlock Origin
- `02-build-i3.sh` - clones i3 from source, applies 3 patches (invisible tabs, no drag resize, normal cursor), compiles and installs. Skips automatically if a cached binary was injected.
- `03-copy-assets.sh` - copies everything from `src/debian-base1` into the OS (`/etc/skel`, `/usr/local/bin`, `/opt/makecode`, etc.)
- `04-user-setup.sh` - creates users/groups, runs all config scripts (i3, vifm, GTK, launcher)
- `05-services.sh` - enables systemd services (student-state-agent, teacher-state-publisher, the GPU fallback tier system)

## Full build flow

```
build-system.sh
  |
  |- copy live-build/  -> ~/cis4900-lb-workdir/auto/
  |- copy packages/    -> workdir/config/package-lists/
  |- copy archives/    -> workdir/config/archives/
  |- copy bootloaders  -> workdir/config/bootloaders/ (default templates + grub-live-menu.cfg overlay)
  |- copy inject/      -> workdir/config/includes.chroot/...
  |- copy hooks/       -> workdir/config/hooks/live/ (renamed to 0XXX-*.hook.chroot)
  |- rsync src/debian-base1 -> workdir (hash-checked, skipped if unchanged)
  |- inject cached i3 binary if available (saves like 3-8 mins)
  |
  |- lb build
        |- auto/config -> lb config (initialises workdir, creates generated dirs)
        |- auto/build  -> lb build
              |- bootstrap (download base Debian system)
              |- chroot    (install packages from packages/)
              |     |- 01-waterfox.sh
              |     |- 02-build-i3.sh
              |     |- 03-copy-assets.sh
              |     |- 04-user-setup.sh
              |     |- 05-services.sh
              |- binary
                    |- dist/cis4900-live.iso
```

## Incremental builds

On the second run (without `--clean`):
- If `src/debian-base1` hasn't changed, then it skips the rsync entirely
- If a cached i3 binary exists in `~/cis4900-lb-workdir/cache/i3/`, then it injects it and hook `02` exits immediately

Use `--clean` when you change the i3 patches in `hooks/02-build-i3.sh` or need a guaranteed clean slate.

## GPU acceleration on AMD Stoney Ridge

Some AMD Stoney Ridge iGPUs fail to fully initialize `amdgpu` (the last line you see is often a `kfd ... STONEY` message, but the real failure is deeper in `amdgpu`'s powerplay/Display Core code, not that line). The old approach was a permanent `nomodeset modprobe.blacklist=amdgpu`, which meant no GPU acceleration at all, forever, on every machine.

Instead, `linux-image-amd64` and `firmware-amd-graphics` in `apps.list` now resolve to their `bookworm-backports` builds (the two best-evidenced candidate fixes for this chip generation), pinned there by `99-bookworm-backports.pref`, and `ychitsa-gpu-tier` (see `inject/` above) tries full acceleration first on every boot, automatically stepping down through safer kernel parameter tiers only if a boot doesn't actually come up, and remembering whichever tier last worked. See the GPU section of the project plan for the full design and the research behind it.
