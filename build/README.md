# Build

Run from the repo root:

```bash
sudo bash -x ./build/build-system.sh --mode iso
sudo bash -x ./build/build-system.sh --mode iso --clean   
sudo bash -x ./build/build-system.sh --mode docker
```

## File Function

### `build-system.sh`
The main entry point. It maps all the files from `build/` into a live-build workdir at `~/cis4900-lb-workdir` (Linux ext4, outside the repo — required because Windows NTFS doesn't support `mknod` which live-build needs for device files). Nothing generated ever lands back in `build/`.

### `live-build/`
Three scripts that live-build (`lb`) **requires** to exist at `auto/config`, `auto/build`, and `auto/clean` in its workdir. live-build calls them automatically, in order, when you run `lb build`, they're never called directly

- **`config`** — tells live-build what to build: Debian Bookworm amd64, hybrid ISO (boots from USB or DVD), includes the Debian installer so you can install to disk from GRUB, apt sources include non-free firmware for AMD/WiFi drivers, boot parameters blacklist amdgpu and set nomodeset (as there is an issue with the amd gpu, so this is a known Stoney Ridge workaround)
- **`build`** — runs `lb build noauto`. `noauto` prevents an infinite loop (lb would otherwise call this script recursively).
- **`clean`** — runs `lb clean --purge` which wipes the workdir to a blank slate. Used when you pass `--clean` to `build-system.sh`.

### `packages/`
APT package lists installed into the OS.
- `base.list` — live-boot/live-config system packages
- `apps.list` — everything else: i3, pipewire, GTK, Waterfox deps, etc.

### `inject/`
Files dropped directly into the built OS filesystem before packages run.
- `lightdm.conf` → `/etc/lightdm/lightdm.conf` (autologin config)
- `gpu.conf` → `/etc/X11/xorg.conf.d/20-fbdev.conf` (fbdev driver, required because amdgpu is blacklisted)
- `udeb_exclude` → `config/debian-installer/udeb_exclude` (must exist or older live-build versions error on install)

### `hooks/`
Scripts run **inside the chroot** by live-build after packages are installed, in numeric order.
- `01-waterfox.sh` — downloads and installs Waterfox and uBlock Origin
- `02-build-i3.sh` — clones i3 from source, applies 3 patches (invisible tabs, no drag resize, normal cursor), compiles and installs. Skips automatically if a cached binary was injected.
- `03-copy-assets.sh` — copies everything from `src/debian-base1` into the OS (`/etc/skel`, `/usr/local/bin`, `/opt/makecode`, etc.)
- `04-user-setup.sh` — creates users/groups, runs all config scripts (i3, vifm, GTK, launcher)
- `05-services.sh` — enables systemd services (student-state-agent, teacher-state-publisher)

## Full build flow

```
build-system.sh
  │
  ├── copy live-build/ -> ~/cis4900-lb-workdir/auto/
  ├── copy packages/   -> workdir/config/package-lists/
  ├── copy inject/     -> workdir/config/includes.chroot/etc/ + workdir/config/debian-installer/
  ├── copy hooks/      -> workdir/config/hooks/live/  (renamed to 0XXX-*.hook.chroot)
  ├── rsync src/debian-base1 -> workdir (hash-checked, skipped if unchanged)
  ├── inject cached i3 binary if available (saves like 3-8 mins)
  │
  └── lb build
        ├── auto/config  -> lb config  (initialises workdir, creates generated dirs)
        └── auto/build   -> lb build
              ├── bootstrap  (download base Debian system)
              ├── chroot     (install packages from packages/)
              │     ├── 01-waterfox.sh
              │     ├── 02-build-i3.sh
              │     ├── 03-copy-assets.sh
              │     ├── 04-user-setup.sh
              │     └── 05-services.sh
              └── binary     
                    └──dist/cis4900-live.iso
```

## Incremental builds

On the second run (without `--clean`):
- If `src/debian-base1` hasn't changed, then it skips the rsync entirely
- If a cached i3 binary exists in `~/cis4900-lb-workdir/cache/i3/`, then it injects it and hook `02` exits immediately

Use `--clean` when you change the i3 patches in `hooks/02-build-i3.sh` or need a guaranteed clean slate.

## AMD Stoney Ridge, Black screen error at `kfd … STONEY`

On some AMD Stoney Ridge iGPUs the last line you see is the KFD message, but the real failure is usually amdgpu GPU init / SMU firmware. The ISO defaults to `nomodeset` and `modprobe.blacklist=amdgpu` so the machine can boot. After install you may need similar kernel options in GRUB until you verify a kernel/firmware combo that works without them.
