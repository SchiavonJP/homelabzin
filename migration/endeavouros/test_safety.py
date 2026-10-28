"""Exercise migration guards with temporary sysfs/configs and fake host commands.

No root access, lab connection, or system configuration writes required.
Run: python3 -m unittest discover -s migration/endeavouros -p 'test_*.py' -v
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parent


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "commands"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", LOG=str(self.log))

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(0o755)
        return path

    def run_script(self, name, *args, replacements=()):
        content = (SCRIPTS / name).read_text()
        for old, new in replacements:
            content = content.replace(old, new)
        script = self.root / name
        script.write_text(content)
        return subprocess.run(["bash", str(script), *args], env=self.env,
                              capture_output=True, text=True)

    def test_vm_has_disconnected_network_and_no_gpu(self):
        iso = self.root / "clonezilla.iso"
        iso.touch()
        self.command("pvesm", f'if [[ $1 == path ]]; then echo "{iso}"; else '
                     "printf 'Name Type Status Total Used Available %%\\nlocal-lvm lvmthin active 999999999 0 999999999 0\\n'; fi")
        self.command("pvesh", "echo 222")
        self.command("qm", 'printf "%s\\n" "$@" >> "$LOG"')
        result = self.run_script("create-vm.sh", "local:iso/clonezilla.iso",
                                 replacements=[('[[ $EUID == 0 && -d /etc/pve ]]', 'true')])
        self.assertEqual(result.returncode, 0, result.stderr)
        args = self.log.read_text().splitlines()
        self.assertIn("virtio,bridge=vmbr0,link_down=1", args)
        self.assertIn("4096", args)
        self.assertIn("local-lvm:160,discard=on,ssd=1", args)
        self.assertNotIn("start", args)
        self.assertFalse(any("hostpci" in arg for arg in args))

    def test_low_storage_refuses_vm_creation(self):
        iso = self.root / "clonezilla.iso"
        iso.touch()
        self.command("pvesm", f'if [[ $1 == path ]]; then echo "{iso}"; else '
                     "printf 'Name Type Status Total Used Available %%\\nlocal-lvm lvmthin active 1000 900 100 90\\n'; fi")
        self.command("qm", 'touch "$LOG"')
        result = self.run_script("create-vm.sh", "local:iso/clonezilla.iso",
                                 replacements=[('[[ $EUID == 0 && -d /etc/pve ]]', 'true')])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def vfio_fixture(self, extra=False):
        devices = self.root / "devices"
        devices.mkdir()
        group = self.root / "group" / "devices"
        group.mkdir(parents=True)
        definitions = [("0000:10:00.0", "0x030000", "0x2504"),
                       ("0000:10:00.1", "0x040300", "0x228e")]
        if extra:
            definitions.append(("0000:11:00.0", "0x020000", "0x9999"))
        for bdf, cls, device_id in definitions:
            path = devices / bdf
            path.mkdir()
            (path / "vendor").write_text("0x10de\n")
            (path / "device").write_text(device_id + "\n")
            (path / "class").write_text(cls + "\n")
            (path / "iommu_group").symlink_to(group.parent)
            (group / bdf).symlink_to(path)
        modules = self.root / "modules"
        modules.write_text("# existing\ni915\n")
        modprobe = self.root / "modprobe"
        modprobe.mkdir()
        self.command("update-initramfs", 'echo update >> "$LOG"')
        return [('[[ $EUID == 0 && -d /etc/pve ]]', 'true'),
                ('/sys/bus/pci/devices', str(devices)),
                ('/etc/initramfs-tools/modules', str(modules)),
                ('/etc/modprobe.d', str(modprobe)),
                ('/root/endeavour-vfio-backup-', str(self.root / 'backup-'))]

    def test_vfio_refuses_unrelated_group_member_before_writing(self):
        replacements = self.vfio_fixture(extra=True)
        result = self.run_script("configure-vfio.sh", "0000:10:00.0", "0000:10:00.1",
                                 replacements=replacements)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsafe group", result.stderr)
        self.assertEqual((self.root / "modules").read_text(), "# existing\ni915\n")
        self.assertFalse(self.log.exists())
        self.assertFalse(list((self.root / "modprobe").iterdir()))

    def test_vfio_stages_and_backs_up_without_reboot(self):
        replacements = self.vfio_fixture()
        result = self.run_script("configure-vfio.sh", "0000:10:00.0", "0000:10:00.1",
                                 replacements=replacements)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = (self.root / "modprobe" / "endeavour-vfio.conf").read_text()
        self.assertIn("ids=10de:2504,10de:228e", config)
        backup = next(self.root.glob("backup-*/modules"))
        self.assertEqual(backup.read_text(), "# existing\ni915\n")
        self.assertEqual(self.log.read_text(), "update\n")

    def test_gaming_mode_rejects_lingering_process(self):
        self.command("systemctl", 'if [[ $1 == show ]]; then '
                     'case "$3" in --property=MainPID) echo 123;; *) echo inactive;; esac; fi')
        result = self.run_script("apollo-mode", "gaming",
                                 replacements=[('if [[ $EUID != 0 ]]; then', 'if false; then')])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not fully stopped", result.stderr)

    def test_gaming_mode_confirms_both_services_stop(self):
        self.command("systemctl", 'printf "%s\\n" "$*" >> "$LOG"; '
                     'if [[ $1 == show ]]; then case "$3" in '
                     '--property=MainPID) echo 0;; *) echo inactive;; esac; fi')
        result = self.run_script("apollo-mode", "gaming",
                                 replacements=[('if [[ $EUID != 0 ]]; then', 'if false; then')])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stop apollo-inference.service apollo-embedding.service", self.log.read_text())

    def test_runner_passes_literal_arguments_without_shell_evaluation(self):
        config = self.root / "config"
        config.mkdir()
        payload = f"$(touch {self.root / 'should-not-exist'})"
        (config / "inference.args").write_text(f"--model\n/models/model with spaces.gguf\n{payload}\n")
        binary = self.command("server", 'printf "%s\\n" "$@"')
        result = self.run_script("apollo-run", "inference", replacements=[
            ('/etc/apollo', str(config)), ('/opt/apollo-llama/build/bin/llama-server', str(binary))])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["--model", "/models/model with spaces.gguf", payload])
        self.assertFalse((self.root / "should-not-exist").exists())

    def test_export_refuses_host_local_storage(self):
        self.command("realpath", 'printf "%s\\n" "$2"')
        self.command("findmnt", 'if [[ $* == *FSTYPE* ]]; then echo ext4; else echo /dev/sda; fi')
        self.command("pct", 'touch "$LOG"')
        result = self.run_script("export-apollo.sh", "110", str(self.root),
                                 replacements=[('[[ $EUID == 0 && -d /etc/pve ]]', 'true')])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-NFS", result.stderr)
        self.assertFalse(self.log.exists())

    def test_installer_refuses_physical_notebook(self):
        self.command("systemd-detect-virt", "echo none")
        result = self.run_script("install-apollo.sh", replacements=[
            ('[[ $EUID == 0 ]]', 'true'), ('[[ -f /etc/arch-release ]]', 'true')])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing physical notebook", result.stderr)


if __name__ == "__main__":
    unittest.main()
