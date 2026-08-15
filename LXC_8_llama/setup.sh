#!/usr/bin/env bash
# Apollo — LXC 8 automated setup
# Run inside the LXC as root: bash setup.sh
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# Constants (override via .env in the same directory)
# ──────────────────────────────────────────────────────────────
DRIVER_VERSION="610.43.02"
# Auto-detected in step 4 — picks the latest cuda-toolkit-X-Y available in the repo
LLAMA_REPO="https://github.com/ggml-org/llama.cpp"
BGE_REPO="gpustack/bge-m3-GGUF"
BGE_FILE="bge-m3-Q4_K_M.gguf"
MODEL_DIR="/models"
LLAMA_DIR="/opt/llama.cpp"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"

# Load user overrides
[ -f "${SCRIPT_DIR}/.env" ] && source "${SCRIPT_DIR}/.env"

# ── Model preset ──────────────────────────────────────────────
# Select via MODEL_PRESET env var or .env file.
# .env values take precedence over preset defaults.
MODEL_PRESET="${MODEL_PRESET:-qwen3}"

case "$MODEL_PRESET" in
  qwen3)
    MODEL_REPO="${MODEL_REPO:-localweights/Qwen3.6-35B-A3B-MTP-Q4_K_M-GGUF}"
    MODEL_FILE="${MODEL_FILE:-Qwen3.6-35B-A3B-MTP-Q4_K_M.gguf}"
    LLAMA_NGL="${LLAMA_NGL:-22}"
    LLAMA_CTX_SIZE="${LLAMA_CTX_SIZE:-8192}"
    LLAMA_EXTRA_ARGS="${LLAMA_EXTRA_ARGS:---spec-type draft-mtp --spec-draft-n-max 3 --draft-p-min 0.40}"
    ;;
  gemma3-12b)
    MODEL_REPO="${MODEL_REPO:-bartowski/gemma-3-12b-it-GGUF}"
    MODEL_FILE="${MODEL_FILE:-gemma-3-12b-it-Q4_K_M.gguf}"
    LLAMA_NGL="${LLAMA_NGL:-99}"
    LLAMA_CTX_SIZE="${LLAMA_CTX_SIZE:-8192}"
    LLAMA_EXTRA_ARGS="${LLAMA_EXTRA_ARGS:-}"
    ;;
  *) echo -e "\033[1;31m  ✗\033[0m Unknown MODEL_PRESET: '$MODEL_PRESET'. Use: qwen3, gemma3-12b." >&2; exit 1 ;;
esac

LLAMA_PORT="${LLAMA_PORT:-8080}"
# Always derived from MODEL_FILE set by the preset; .env overrides of LLAMA_MODEL_PATH are ignored.
# To use a custom model path, set MODEL_FILE in .env instead.
LLAMA_MODEL_PATH="${MODEL_DIR}/${MODEL_FILE}"
BGE_PORT="${BGE_PORT:-8081}"
BGE_CTX_SIZE="${BGE_CTX_SIZE:-8192}"
BGE_NGL="${BGE_NGL:-99}"
BGE_MODEL_PATH="${BGE_MODEL_PATH:-${MODEL_DIR}/${BGE_FILE}}"

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
step() { echo -e "\n\033[1;34m==>\033[0m $*"; }
ok()   { echo -e "\033[1;32m  ✓\033[0m $*"; }
warn() { echo -e "\033[1;33m  !\033[0m $*"; }
die()  { echo -e "\033[1;31m  ✗\033[0m $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && die "Run as root: sudo bash setup.sh"

# ──────────────────────────────────────────────────────────────
# 0. GPU passthrough sanity check
# ──────────────────────────────────────────────────────────────
step "Checking GPU passthrough..."
if [ ! -c /dev/nvidia0 ]; then
  die "$(cat <<'EOF'
/dev/nvidia0 not found. Add GPU passthrough to the Proxmox LXC config first.

Add these lines to /etc/pve/lxc/NNN.conf (replace NNN with your CT ID):

  lxc.cgroup2.devices.allow: c 195:* rwm
  lxc.cgroup2.devices.allow: c 509:* rwm
  lxc.mount.entry: /dev/nvidia0         dev/nvidia0         none bind,optional,create=file
  lxc.mount.entry: /dev/nvidiactl       dev/nvidiactl       none bind,optional,create=file
  lxc.mount.entry: /dev/nvidia-uvm      dev/nvidia-uvm      none bind,optional,create=file
  lxc.mount.entry: /dev/nvidia-uvm-tools dev/nvidia-uvm-tools none bind,optional,create=file
  lxc.mount.entry: /dev/nvidia-modeset  dev/nvidia-modeset  none bind,optional,create=file

Then restart the container and re-run this script.
EOF
)"
fi
ok "GPU devices found"

# ──────────────────────────────────────────────────────────────
# 1. Base dependencies
# ──────────────────────────────────────────────────────────────
step "Installing base dependencies..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  wget curl git cmake build-essential pkg-config \
  python3-pip python3-venv tmux htop ccache
ok "Base dependencies installed"

# ──────────────────────────────────────────────────────────────
# 2. NVIDIA userspace driver (no kernel module — host owns that)
# ──────────────────────────────────────────────────────────────
step "Installing NVIDIA driver ${DRIVER_VERSION} (userspace only)..."

_driver_ok() {
  command -v nvidia-smi &>/dev/null \
    && nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null \
       | grep -q "^${DRIVER_VERSION}"
}

if _driver_ok; then
  ok "Driver ${DRIVER_VERSION} already installed"
else
  TMPDIR_DRV=$(mktemp -d)
  trap 'rm -rf "$TMPDIR_DRV"' EXIT

  wget -q --show-progress \
    "https://download.nvidia.com/XFree86/Linux-x86_64/${DRIVER_VERSION}/NVIDIA-Linux-x86_64-${DRIVER_VERSION}.run" \
    -O "${TMPDIR_DRV}/driver.run"
  chmod +x "${TMPDIR_DRV}/driver.run"

  "${TMPDIR_DRV}/driver.run" \
    --no-kernel-module \
    --no-kernel-module-source \
    --no-backup \
    --no-questions \
    --ui=none

  trap - EXIT
  rm -rf "$TMPDIR_DRV"
  ok "Driver installed"
fi

# ──────────────────────────────────────────────────────────────
# 3. Fix nvidia-smi binary (known empty-package bug)
# ──────────────────────────────────────────────────────────────
step "Checking nvidia-smi binary..."
if ! command -v nvidia-smi &>/dev/null; then
  warn "nvidia-smi missing (known CUDA repo bug) — extracting from .run..."
  TMPDIR_SMI=$(mktemp -d)
  trap 'rm -rf "$TMPDIR_SMI"' EXIT

  wget -q --show-progress \
    "https://download.nvidia.com/XFree86/Linux-x86_64/${DRIVER_VERSION}/NVIDIA-Linux-x86_64-${DRIVER_VERSION}.run" \
    -O "${TMPDIR_SMI}/driver.run"
  chmod +x "${TMPDIR_SMI}/driver.run"
  "${TMPDIR_SMI}/driver.run" --extract-only --target "${TMPDIR_SMI}/extracted"
  cp "${TMPDIR_SMI}/extracted/nvidia-smi" /usr/local/bin/nvidia-smi
  chmod +x /usr/local/bin/nvidia-smi

  trap - EXIT
  rm -rf "$TMPDIR_SMI"
fi

nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
ok "nvidia-smi OK"

# ──────────────────────────────────────────────────────────────
# 4. CUDA toolkit (nvcc + headers, required to build llama.cpp)
# ──────────────────────────────────────────────────────────────
step "Installing CUDA toolkit..."

export PATH="/usr/local/cuda/bin:${PATH}"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"

if command -v nvcc &>/dev/null; then
  ok "CUDA already installed: $(nvcc --version | grep 'release')"
else
  wget -q \
    https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/cuda-keyring_1.1-1_all.deb \
    -O /tmp/cuda-keyring.deb
  dpkg -i /tmp/cuda-keyring.deb
  rm /tmp/cuda-keyring.deb
  apt-get update -qq

  # Pick the latest versioned cuda-toolkit-X-Y available in the repo
  CUDA_PKG=$(apt-cache search 'cuda-toolkit-[0-9]' 2>/dev/null \
    | grep -oP 'cuda-toolkit-\d+-\d+' | sort -V | tail -1)
  CUDA_PKG="${CUDA_PKG:-cuda-toolkit}"
  echo "  Installing: ${CUDA_PKG}"
  apt-get install -y "${CUDA_PKG}"

  # Persist to /etc/environment for future shells
  grep -qxF 'PATH=/usr/local/cuda/bin:$PATH' /etc/environment 2>/dev/null \
    || echo 'PATH=/usr/local/cuda/bin:$PATH' >> /etc/environment
  grep -qxF 'LD_LIBRARY_PATH=/usr/local/cuda/lib64' /etc/environment 2>/dev/null \
    || echo 'LD_LIBRARY_PATH=/usr/local/cuda/lib64' >> /etc/environment

  ok "CUDA installed: $(nvcc --version | grep 'release')"
fi

# ──────────────────────────────────────────────────────────────
# 5. Build llama.cpp with CUDA (sm_86 = RTX 3060)
# ──────────────────────────────────────────────────────────────
step "Building llama.cpp with CUDA..."

if [ -f "${LLAMA_DIR}/build/bin/llama-server" ]; then
  ok "llama-server already built at ${LLAMA_DIR}/build/bin/llama-server"
else
  if [ -d "$LLAMA_DIR" ]; then
    warn "${LLAMA_DIR} exists but build is missing — rebuilding..."
    git -C "$LLAMA_DIR" pull --ff-only
  else
    git clone --depth 1 "$LLAMA_REPO" "$LLAMA_DIR"
  fi

  cmake -B "${LLAMA_DIR}/build" \
    -S "$LLAMA_DIR" \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES="86" \
    -DGGML_NATIVE=ON

  cmake --build "${LLAMA_DIR}/build" --config Release -j"$(nproc)"
  ok "llama-server built"
fi

# Verify CUDA was linked
"${LLAMA_DIR}/build/bin/llama-server" --list-devices 2>&1 | grep -i cuda \
  || warn "CUDA devices not found — check that driver and CUDA toolkit versions match"

# ──────────────────────────────────────────────────────────────
# 6. Download model
# ──────────────────────────────────────────────────────────────
step "Downloading model (${MODEL_FILE})..."
mkdir -p "$MODEL_DIR"

if [ -f "${LLAMA_MODEL_PATH}" ]; then
  ok "Model already present at ${LLAMA_MODEL_PATH}"
else
  pip3 install -q --break-system-packages huggingface-hub
  hf download "$MODEL_REPO" \
    --local-dir "$MODEL_DIR" \
    --include "*.gguf"
  ok "Model downloaded to ${LLAMA_MODEL_PATH}"
fi

# ──────────────────────────────────────────────────────────────
# 6b. Download bge-m3 embedding model
# ──────────────────────────────────────────────────────────────
step "Downloading bge-m3 embedding model (${BGE_FILE})..."

if [ -f "${BGE_MODEL_PATH}" ]; then
  ok "bge-m3 already present at ${BGE_MODEL_PATH}"
else
  pip3 install -q --break-system-packages huggingface-hub
  hf download "$BGE_REPO" \
    --local-dir "$MODEL_DIR" \
    --include "${BGE_FILE}"
  ok "bge-m3 downloaded to ${BGE_MODEL_PATH}"
fi

# ──────────────────────────────────────────────────────────────
# 7. Install systemd services
# ──────────────────────────────────────────────────────────────
step "Installing systemd services..."

# Env files (always regenerated so overrides take effect)
cat > /etc/llama-server.env << EOF
LLAMA_PORT=${LLAMA_PORT}
LLAMA_MODEL_PATH=${LLAMA_MODEL_PATH}
LLAMA_CTX_SIZE=${LLAMA_CTX_SIZE}
LLAMA_NGL=${LLAMA_NGL}
LLAMA_THREADS=6
LLAMA_EXTRA_ARGS=${LLAMA_EXTRA_ARGS}
EOF

# Wrapper script — handles word-splitting of LLAMA_EXTRA_ARGS
# (systemd does not word-split env var references in ExecStart)
cat > "${LLAMA_DIR}/run-llama-server.sh" << 'WRAPPER'
#!/usr/bin/env bash
set -a; source /etc/llama-server.env; set +a
exec /opt/llama.cpp/build/bin/llama-server \
  --model        "$LLAMA_MODEL_PATH" \
  --host         0.0.0.0 \
  --port         "$LLAMA_PORT" \
  --n-gpu-layers "$LLAMA_NGL" \
  --flash-attn   on \
  --ctx-size     "$LLAMA_CTX_SIZE" \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --threads      "${LLAMA_THREADS:-6}" \
  --parallel     1 \
  --cont-batching \
  $LLAMA_EXTRA_ARGS
WRAPPER
chmod +x "${LLAMA_DIR}/run-llama-server.sh"
ok "Wrapper script written to ${LLAMA_DIR}/run-llama-server.sh"

cat > /etc/bge-embedding.env << EOF
BGE_PORT=${BGE_PORT}
BGE_MODEL_PATH=${BGE_MODEL_PATH}
BGE_CTX_SIZE=${BGE_CTX_SIZE}
BGE_NGL=${BGE_NGL}
EOF

cp "${SCRIPT_DIR}/llama-server.service" /etc/systemd/system/llama-server.service
cp "${SCRIPT_DIR}/bge-embedding.service" /etc/systemd/system/bge-embedding.service
systemctl daemon-reload
systemctl enable --now llama-server
systemctl enable --now bge-embedding
ok "Services installed and started"

# ──────────────────────────────────────────────────────────────
# 8. Verification
# ──────────────────────────────────────────────────────────────
step "Verification (waiting 8s for server to load model)..."
sleep 8

echo ""
nvidia-smi
echo ""
systemctl status llama-server --no-pager -l | head -25
echo ""

HEALTH=$(curl -sf "http://localhost:${LLAMA_PORT}/health" 2>/dev/null || echo '{"status":"not ready yet"}')
echo "Health (llama-server):   ${HEALTH}"

BGE_HEALTH=$(curl -sf "http://localhost:${BGE_PORT}/health" 2>/dev/null || echo '{"status":"not ready yet"}')
echo "Health (bge-embedding):  ${BGE_HEALTH}"

echo ""
echo "════════════════════════════════════════════════"
echo "  Apollo setup complete!"
echo "  Inference:  http://$(hostname -I | awk '{print $1}'):${LLAMA_PORT}/v1"
echo "  Embeddings: http://$(hostname -I | awk '{print $1}'):${BGE_PORT}/v1/embeddings"
echo "  Public URL: https://apollo.joaopaulo.me"
echo ""
echo "  Manage services:"
echo "    systemctl status llama-server bge-embedding"
echo "    journalctl -u llama-server -f"
echo "    journalctl -u bge-embedding -f"
echo "════════════════════════════════════════════════"
