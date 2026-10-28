# EndeavourOS VM + Apollo migration

Status: tooling prepared; **no lab machines have been changed**. SSH from the
implementation session returned `No route to host`. Run the host steps from the
workstation terminal that can reach the lab. Do not run VM-only steps on the
physical notebook. Source notebook and original Apollo LXC remain rollback copies.

## Recorded inventory and decisions

| Item | Recorded value |
| --- | --- |
| Proxmox | `root@192.168.0.200`, Ryzen 5700G, MSI B550M Bazooka, RTX 3060 12 GB |
| Host memory | 58 GiB usable; 37 GiB available at inventory time |
| VM disk storage | `local-lvm`: about 588 GiB free |
| Host directory storage | `local`: about 5 GiB free; **not** an image/backup destination |
| Notebook | `schiva@192.168.0.58`, also Tailscale `100.80.3.58` |
| Source system disk | 119.2 GiB, formerly `sdb`: 2 GiB EFI + Btrfs; about 104 GiB used |
| Excluded disk | 931.5 GiB, formerly `sda`, mounted at `/mnt/dados` |
| Image repository | Mini PC `192.168.0.12:/storage`, about 880 GiB free |
| Original Apollo | LXC 110 per repo; **verify live**, IP `192.168.0.217` |
| Target VM | Independent clone, 160 GiB disk, 8 vCPUs, 32 GiB fixed RAM |
| Interaction | Direct monitor on RTX 3060; USB keyboard/mouse on Proxmox |
| Inference | Manual start; both services stopped for gaming |

Host maintenance reboot is accepted. Primary LiteLLM remote routes remain in
their existing container. There is no automatic synchronization of the two OS
installations. Never attach the original notebook disks directly to the VM.

## 1. Inventory, export Apollo, and prepare media

Copy this directory to each machine using your reachable terminal, or use an
existing repository checkout. Run the appropriate read-only inventory locally:

```bash
bash preflight.sh notebook
bash preflight.sh pve
bash preflight.sh minipc
```

Save the outputs on the workstation. On the notebook, also record the Btrfs
subvolumes (`sudo btrfs subvolume list /`), installed initramfs configuration,
bootloader configuration, enabled user services, and desktop autostarts. Record
game resolution, refresh rate, and frame-time/FPS baseline in representative games.

On Proxmox, verify the live Apollo ID with `pct list` and `pct config 110` before
using 110 below. Record `pct exec 110 -- systemctl cat llama-server bge-embedding`
and `pct exec 110 -- git -C /opt/llama.cpp rev-parse HEAD`. Capture the **full
40-character commit**, model paths, model hashes, current env files, wrapper,
service definitions, `nvidia-smi`, and `pct config 110`. Do not print secrets into
shared logs. Include any local llama.cpp changes (`git diff`) in the archive;
if present, preserve/review them before building rather than silently discarding.

Mount Mini PC NFS on Proxmox for export (do not put models under host `/root`):

```bash
mkdir -p /mnt/endeavour-migration
mount -t nfs 192.168.0.12:/storage /mnt/endeavour-migration
findmnt /mnt/endeavour-migration
df -h /mnt/endeavour-migration
mkdir -p /mnt/endeavour-migration/backups/endeavouros
chmod 700 /mnt/endeavour-migration/backups/endeavouros
```

Confirm that mount is NFS from the Mini PC and has sufficient capacity before
copying. Export the running service configuration and models while no model
downloads or configuration edits are in progress:

```bash
bash export-apollo.sh 110 /mnt/endeavour-migration
```

The exporter requires the exact Mini PC NFS source, checks capacity, saves live
configuration and commit/local-diff information, streams model copies with pipeline
error checking, and verifies SHA-256 hashes before creating `EXPORT-VERIFIED`.
If a live unit/wrapper uses paths beyond those recorded in the repo, archive those
additional paths too. Review the recorded untracked-file list for source patches
that must be carried over. Stop inference briefly if needed for a stable export.
The existing container can resume inference until the VFIO maintenance window.

Create `/storage/backups/endeavouros/images` on the Mini PC. Download the current
stable amd64 Clonezilla Live ISO from its official site and verify its checksum
against the release's published checksum. Use it to prepare a notebook USB stick
and upload the same ISO to Proxmox `local` ISO storage. Check ISO free space first.
Writing the USB erases that USB: verify its device identity before writing.

## 2. Capture and restore the system disk

1. Shut down the notebook cleanly. Boot Clonezilla Live from USB with wired LAN.
2. Choose `device-image`, `nfs_server`, server `192.168.0.12`, export `/storage`,
   repository subdirectory `/backups/endeavouros/images`. Verify the repository
   mount and available space before capture.
3. Choose `savedisk`; name the image `endeavour-system-YYYYMMDD`. Select the
   **119.2 GiB system disk by model/serial**, including EFI and Btrfs. Device
   letters can change. Exclude the 931.5 GiB data drive. Enable image verification.
4. After verified capture, the notebook can boot normally again. Subsequent
   notebook changes will not automatically appear in the VM.
5. On Proxmox, create the stopped VM using the actual ISO volume name:

   ```bash
   bash create-vm.sh local:iso/<verified-Clonezilla-ISO>.iso
   ```

   Record its printed VM ID as `VMID` in that terminal. Inspect `qm config "$VMID"`.
   The script allocates only new VM volumes and refuses insufficient storage;
   it does not restore, overwrite existing disks, start the VM, or attach a GPU.
   If creation fails partway, inspect the new VM/volumes before retrying; do not
   delete any volumes by guessing their IDs.
6. Temporarily connect its NIC for Clonezilla NFS access:

   ```bash
   qm set "$VMID" --net0 virtio,bridge=vmbr0,link_down=0
   qm start "$VMID"
   ```

   In the Proxmox console, boot Clonezilla. Mount the same image repository and
   use `restoredisk` into the **new 160 GiB VM disk only**. Restore the original
   partition sizes; grow Btrfs afterward, rather than proportionally enlarging EFI.
7. Power off after restore. Disconnect the VM NIC before booting restored Linux:

   ```bash
   qm set "$VMID" --net0 virtio,bridge=vmbr0,link_down=1
   ```

## 3. Offline clone repair and identity separation

Boot a verified Arch/EndeavourOS rescue ISO in the VM, keeping the NIC disconnected.
Use `lsblk -f` to identify the VM disk; mount the Btrfs `@` subvolume as the rescue
root and EFI at its recorded `/boot/efi`. Mount the other recorded subvolumes as
required. **All edits below target the mounted clone, never the notebook.**

- Back up the clone's `/etc/fstab`; remove/comment the missing `/mnt/dados` entry.
  Check for other missing disks and resume/hibernation device references.
- Set hostname `endeavour-vm`; update any hostname-specific `/etc/hosts` entry.
- Reset the clone's machine ID using systemd's image procedure: empty its
  `/etc/machine-id` and remove a separate copied `/var/lib/dbus/machine-id` file
  (preserve/recreate the normal symlink to `/etc/machine-id` as appropriate).
  Remove copied SSH host keys; regenerate inside the VM before enabling SSH.
- Disable Tailscale and remove **only the clone's** copied Tailscale state. Later
  enroll it as a new node. Do not log out/delete the original node from the tailnet.
- Disable copied Syncthing system/user units and Obsidian/other sync autostarts.
  Do not launch Obsidian until LiveSync is disabled or reviewed for this clone.
  Preserve the notebook as the existing Hermes vault source.
- In an `arch-chroot`, add `virtio_pci`, `virtio_scsi`, and `virtio_blk` using the
  **installed** initramfs generator. With mkinitcpio, preserve existing `MODULES`
  entries and regenerate with `mkinitcpio -P`; with dracut use a persistent
  `add_drivers` configuration and regenerate with `dracut --regenerate-all --force`.
- Repair the **existing** bootloader, preserving Btrfs `rootflags=subvol=@`.
  For GRUB, reinstall its EFI loader into the mounted EFI directory and regenerate
  its config. For systemd-boot, install to the recorded ESP and repair loader entries
  referencing the recorded kernel/initramfs paths. Source machine NVRAM entries
  are not copied into OVMF. Do not switch bootloaders during migration.
- Grow the final Btrfs partition to the end of the 160 GiB virtual disk using the
  rescue partition editor, preserving its start sector and filesystem UUID. Then
  run `btrfs filesystem resize max` against the mounted Btrfs filesystem.

Boot the cloned installation from disk with the NIC still disconnected. Verify
login and identities first. Then reconnect the NIC, use DHCP, regenerate SSH host
keys with `sudo ssh-keygen -A`, and enroll Tailscale only as a distinct node.
Install the QEMU guest agent and enable it inside the VM. Verify desktop and coding
tools before proceeding. Remove rescue media from normal boot order:

```bash
qm set "$VMID" --boot order=scsi0
```

## 4. Permanent RTX 3060 passthrough

Read the inventory's IOMMU groups. Identify full-domain BDFs for RTX 3060 VGA and
its audio function. Require separation from unrelated devices. Do not use an ACS
override or unsafe interrupts to bypass this check. Enable SVM/IOMMU in firmware
if absent, and re-inventory after reboot before continuing.

In firmware, enable integrated graphics and select the 5700G iGPU as the host's
primary display. Confirm independent SSH/Proxmox management still works. Preserve
the existing NVIDIA driver packages for rollback.

```bash
pct shutdown 110
pct set 110 --onboot 0
qm shutdown "$VMID"
```

Confirm both are stopped. Check actual free memory and other active workloads
before assigning 32 GiB; do not allow swap to substitute for adequate headroom.
Set `GPU_BDF` and `AUDIO_BDF` to the **verified** full BDFs from inventory, then:

```bash
bash configure-vfio.sh "$GPU_BDF" "$AUDIO_BDF"
```

Record the printed rollback directory. The script verifies NVIDIA functions,
same-card membership, isolated groups, and unique IDs before staging initramfs
changes. It neither unbinds devices live nor reboots. If initramfs generation
fails, restore its backup before rebooting. Check `proxmox-boot-tool status`;
refresh configured boot-tool ESPs if that boot method is in use. Reboot Proxmox
during the maintenance window. Verify **both** functions show `vfio-pci` in
`lspci -nnk` before attaching them. If binding failed, stop here and diagnose.

```bash
qm set "$VMID" --memory 32768 --balloon 0
qm set "$VMID" --hostpci0 "${GPU_BDF},pcie=1,x-vga=1"
qm set "$VMID" --hostpci1 "${AUDIO_BDF},pcie=1"
```

Attach individual keyboard/mouse/controller devices through Proxmox's USB
hardware UI; do not pass an entire host USB controller by default. Connect the
monitor to the RTX 3060. The passed GPU's display is not available through noVNC.
Start the VM; verify/install the guest NVIDIA driver matching its installed kernel
through EndeavourOS/Arch packages. Do not run the host Debian NVIDIA installer.

Test GPU acceleration (`nvidia-smi`), monitor refresh rate, audio, peripherals,
representative games, multiplayer compatibility, and frame pacing versus baseline.
Require three successful VM shutdown/start cycles without a host reboot. Leave
autostart disabled and do not configure host suspend.

## 5. Install Apollo inside the VM

Mount the export read-only or copy over SSH, then copy the selected inference and
bge-m3 GGUF files to `/models` on VM-local storage. Verify exported SHA-256 hashes.
Check free space first; the installer does not download models. Leave the export
and original container intact. Install the kernel-matching NVIDIA driver, CUDA,
`base-devel`, `cmake`, `ninja`, `git`, and a desktop polkit authentication agent
using the normal Arch full-upgrade procedure, rebooting the VM if required.
Ensure CUDA's compiler is on root's PATH (typically `/opt/cuda/bin/nvcc`).

```bash
sudo bash install-apollo.sh <captured-40-character-commit> \
  /models/<captured-inference-file>.gguf /models/bge-m3-Q4_K_M.gguf
```

This installer refuses the physical notebook, existing Apollo install paths, and
existing service names. It builds the captured commit, installs a dedicated
`apollo` account, and leaves services stopped and disabled at boot. Review
`/etc/apollo/inference.args` against the captured env/wrapper: defaults target the
documented Qwen MoE (`--n-cpu-moe 28`, no speculative decoding) at 8,192 context.
For another model, remove unsupported MoE flags and use its captured offload
settings. Arguments are **one literal argument per line**, including values;
they are not shell expressions. Model files and all parent directories must be
readable/traversable by `apollo`; use `/models`, not a private home directory.

The new services are `apollo-inference` and `apollo-embedding`. Set the guest
firewall to allow the LiteLLM container `192.168.0.211` to ports 8080/8081; do not
create new router port forwards or public ingress. Endpoints listen on guest
interfaces, matching existing service usage.

```bash
sudo apollo-mode start
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8081/health
curl --fail http://127.0.0.1:8080/v1/models
curl --fail http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"apollo-local","messages":[{"role":"user","content":"Reply with OK"}],"max_tokens":16}'
curl --fail http://127.0.0.1:8081/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"bge-m3","input":"migration test"}'
sudo apollo-mode gaming
```

Health can report loading until initialization completes. Read
`journalctl -u apollo-inference -u apollo-embedding` for startup failures and verify
GPU activity during requests. Confirm embedding dimension 1024 and all values
finite. Increase context only after measuring memory/VRAM headroom with the desktop
active. The `.desktop` entries provide start/gaming shortcuts with normal polkit
authentication. Gaming mode stops both service cgroups and verifies stopped state;
it does not terminate unrelated GPU processes or promise zero desktop VRAM use.

## 6. Cutover, acceptance, and rollback

Ensure LXC 110 remains stopped with autostart off. Assign `192.168.0.217/24`,
gateway `192.168.0.1`, to the guest's **actual** VirtIO interface in NetworkManager;
remove its temporary DHCP profile/address. Never have both machines claim this IP.
The physical notebook retains its own IP and identity. Confirm LAN/DNS access.

At cutover, change only `local-coder` and `local-fast` model identifiers in the
LiteLLM configuration to `openai/apollo-local` (matching `--alias apollo-local`).
Keep their existing `http://192.168.0.217:8080/v1` base and public alias names.
Keep `embed`, `openai/bge-m3`, and port 8081 unchanged. Back up the deployed
configuration before applying/reloading it. Do not overwrite unrelated current
LiteLLM changes. Verify requests through LiteLLM for local chat and embeddings,
then stop Apollo and verify primary remote models continue working. An unavailable
local alias is expected when Apollo is off; no embedding-provider fallback is added.

Acceptance checklist:

- Original notebook still boots and retains its vault/Tailscale identity.
- Clone boots independently without the absent HDD and has expanded disk space.
- Three VM stop/start cycles retain GPU, audio, monitor, and USB functionality.
- User's coding workflows and representative games work acceptably.
- Both inference endpoints work directly and through LiteLLM with GPU use.
- Start/gaming shortcuts release inference processes and memory without rebinding
  the GPU or rebooting. Services remain off after a VM reboot.
- Primary remote LiteLLM routes and other lab services survive the cutover.

Create a stopped VM backup to Mini PC NFS after acceptance; include the VM's EFI
disk and model files, and verify backup logs. Keep it separate from the original
Clonezilla image. Use a dedicated Proxmox NFS backup storage or a verified mounted
backup directory; never the nearly full host `local` storage. Record the actual
VM ID, BDFs, USB mappings, commit, models, measurements, and backup paths in
`HOMELAB.md` and Apollo documentation **after** successful cutover, not as a claim
that this runbook has already been executed.

Rollback: stop the VM, remove its claim to `.217`, restore LiteLLM model identifiers
from the deployment backup, remove `/etc/modprobe.d/endeavour-vfio.conf`, and restore
`/etc/initramfs-tools/modules` from the printed VFIO backup. Regenerate initramfs,
refresh configured boot-tool ESPs, and reboot the host. Confirm the NVIDIA driver
and `nvidia-smi` work before starting LXC 110. Check its NVIDIA UVM major device
number against its cgroup rules (documented existing issue). Restore its original
autostart preference only after recovery. No original disks/images are deleted.

References: [Clonezilla NFS imaging](https://clonezilla.org/clonezilla-usage/general-live-use.php),
[Proxmox PCI passthrough](https://github.com/proxmox/pve-docs/blob/master/qm-pci-passthrough.adoc).

## Local tooling checks

```bash
python3 -m unittest discover -s migration/endeavouros -p 'test_*.py' -v
bash -n migration/endeavouros/*.sh migration/endeavouros/apollo-run migration/endeavouros/apollo-mode
```

The tests use temporary fixtures and fake host commands. They verify disconnected
VM creation, storage refusal, isolated GPU staging/backup, rejection of unrelated
IOMMU group members, literal argument handling, workload-stop verification, export
destination checks, and refusal to install on the physical notebook. They do not
substitute for the live hardware and game acceptance checks above.
