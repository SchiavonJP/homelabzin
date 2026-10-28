#!/usr/bin/env bash
# Run ONLY in the restored EndeavourOS VM, after NVIDIA/CUDA validation.
# Requires verified model copies and the full commit hash captured from Apollo.
set -euo pipefail
die() { echo "$*" >&2; exit 1; }
[[ $EUID == 0 ]] || die 'Run as root inside EndeavourOS VM.'
[[ -f /etc/arch-release ]] || die 'This installer requires Arch/EndeavourOS.'
[[ $(systemd-detect-virt) == kvm ]] || die 'Expected a KVM guest; refusing physical notebook.'
[[ $# == 3 ]] || die 'Usage: sudo bash install-apollo.sh <40-char-llama-commit> <inference.gguf> <embedding.gguf>'
commit=$1
[[ $commit =~ ^[a-fA-F0-9]{40}$ ]] || die 'Pass the full captured llama.cpp commit hash.'
inference=$(realpath -e "$2")
embedding=$(realpath -e "$3")
[[ -f $inference && -f $embedding ]] || die 'Both model files must exist.'
for model in "$inference" "$embedding"; do
  [[ $model != *$'\n'* && $model != *$'\r'* ]] || die 'Model paths cannot contain line breaks.'
done
for command in git cmake ninja nvcc nvidia-smi runuser useradd systemctl; do
  command -v "$command" >/dev/null || die "Missing $command; install the matching Arch packages first."
done
nvidia-smi >/dev/null || die 'Guest NVIDIA driver is not working.'
[[ ! -e /opt/apollo-llama ]] || die '/opt/apollo-llama exists; inspect it before reinstalling.'
[[ ! -e /etc/apollo ]] || die '/etc/apollo exists; refusing to overwrite configuration.'
for unit in apollo-inference apollo-embedding; do
  [[ $(systemctl show "$unit.service" -p LoadState --value) == not-found ]] || die "Existing $unit service."
done
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
id apollo >/dev/null 2>&1 || useradd --system --user-group --home-dir /var/lib/apollo --create-home apollo
getent group video >/dev/null && usermod -aG video apollo
getent group render >/dev/null && usermod -aG render apollo
runuser -u apollo -- test -r "$inference" || die 'apollo cannot read inference model or traverse its directories.'
runuser -u apollo -- test -r "$embedding" || die 'apollo cannot read embedding model or traverse its directories.'
install -d -o apollo -g apollo /opt/apollo-llama
runuser -u apollo -- git clone --no-checkout https://github.com/ggml-org/llama.cpp.git /opt/apollo-llama
runuser -u apollo -- git -C /opt/apollo-llama checkout --detach "$commit"
[[ $(git -c safe.directory=/opt/apollo-llama -C /opt/apollo-llama rev-parse HEAD) == "${commit,,}" ]] || die 'Commit mismatch.'
cuda_root=$(dirname "$(dirname "$(readlink -f "$(command -v nvcc)")")")
runuser -u apollo -- cmake -S /opt/apollo-llama -B /opt/apollo-llama/build -G Ninja \
  -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_COMPILER="$(command -v nvcc)" -DCUDAToolkit_ROOT="$cuda_root"
runuser -u apollo -- cmake --build /opt/apollo-llama/build --parallel 4
runuser -u apollo -- /opt/apollo-llama/build/bin/llama-server --list-devices
install -d -m 0755 /etc/apollo
printf '%s\n' --model "$inference" --alias apollo-local --host 0.0.0.0 --port 8080 \
  --n-gpu-layers 99 --n-cpu-moe 28 --no-mmproj --ctx-size 8192 \
  --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --threads 6 \
  --parallel 1 --cont-batching > /etc/apollo/inference.args
printf '%s\n' --model "$embedding" --alias bge-m3 --host 0.0.0.0 --port 8081 \
  --n-gpu-layers 99 --embedding --pooling mean --ctx-size 8192 \
  --batch-size 2048 --threads 4 > /etc/apollo/embedding.args
install -m 0755 "$script_dir/apollo-run" /usr/local/bin/apollo-run
install -m 0755 "$script_dir/apollo-mode" /usr/local/bin/apollo-mode
for mode in inference embedding; do
  cat > "/etc/systemd/system/apollo-${mode}.service" <<EOF
[Unit]
Description=Apollo ${mode} inside EndeavourOS
After=network.target

[Service]
Type=simple
User=apollo
Group=apollo
ExecStart=/usr/local/bin/apollo-run ${mode}
Restart=on-failure
RestartSec=10
TimeoutStopSec=60
KillMode=control-group
NoNewPrivileges=true
ProtectHome=true
Environment=CUDA_VISIBLE_DEVICES=0

[Install]
WantedBy=multi-user.target
EOF
done
install -d /usr/local/share/applications
for mode in start gaming; do
  cat > "/usr/local/share/applications/apollo-${mode}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Apollo: ${mode}
Exec=/usr/local/bin/apollo-mode ${mode}
Terminal=true
Categories=Development;
EOF
done
systemctl daemon-reload
systemctl disable apollo-inference.service apollo-embedding.service
echo 'Installed; services remain stopped and disabled at boot.'
echo 'Review /etc/apollo/*.args against captured live settings BEFORE starting.'
echo 'Defaults target the documented Qwen MoE + bge-m3; adjust for other models.'
echo 'Use apollo-mode start, then check both health endpoints; apollo-mode gaming stops both.'
