# LXC 8 — Apollo (llama.cpp inference)

> **Codename:** Apollo  
> **IP:** 192.168.0.217  
> **Porta API:** 8080  
> **URL pública:** https://apollo.joaopaulo.me  

Nó de inferência local com GPU. Roda o `llama-server` (llama.cpp) com a RTX 3060 passada via LXC. Expõe uma API compatível com OpenAI consumida pelo LiteLLM (LXC 4).

---

## Hardware alocado

| Recurso | Valor |
|---------|-------|
| CPU | 8 cores visíveis no LXC (llama-server usa 6 threads) |
| RAM | 48 GB |
| Swap | 8 GB |
| Disco | 50 GB |
| GPU | RTX 3060 12 GB (passthrough) |
| Bind mount | `/mnt/models` → `/models` (modelos GGUF) |

---

## Pré-requisitos no host Proxmox

O driver NVIDIA já deve estar instalado no host (veja `drivers-nvidia.md` na raiz do repo).

### 1. Criar bind mount para modelos

```bash
# No host Proxmox
mkdir -p /mnt/models
```

### 2. Criar o container


```bash
pct create 110 local:vztmpl/debian-13-standard_13.0-1_amd64.tar.zst \
  --hostname apollo \
  --memory 49152 \
  --swap 8192 \
  --cores 8 \
  --rootfs local-lvm:50 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.0.217/24,gw=192.168.0.1 \
  --unprivileged 0 \
  --features nesting=1
```

### 3. Adicionar GPU passthrough ao config do LXC

Editar `/etc/pve/lxc/110.conf` (ou o ID que você usou) e adicionar ao final:

```ini
# GPU passthrough — RTX 3060
lxc.cgroup2.devices.allow: c 195:* rwm
lxc.cgroup2.devices.allow: c 509:* rwm
lxc.cgroup2.devices.allow: c 238:* rwm
lxc.mount.entry: /dev/nvidia0          dev/nvidia0          none bind,optional,create=file
lxc.mount.entry: /dev/nvidiactl        dev/nvidiactl        none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm       dev/nvidia-uvm       none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm-tools dev/nvidia-uvm-tools none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-caps      dev/nvidia-caps      none bind,optional,create=dir

# Bind mount para modelos
mp0: /mnt/models,mp=/models
```

> **Nota:** os device numbers são `195` (nvidia), `509` (nvidia-uvm), `238` (nvidia-caps). O major `238` é necessário para `cuInit()` no driver 470+. Confirme com `ls -la /dev/nvidia*` no host antes de editar.

### 4. Iniciar o container

```bash
pct start 110
pct enter 110
```

---

## Deploy

### 1. Copiar os arquivos do repo para o LXC

```bash
# No host, copiar este diretório para o LXC
pct push 110 /path/to/homelabzin/LXC_8_llama /opt/apollo --archive
```

Ou dentro do LXC via sparse-checkout (mesmo padrão dos outros LXCs):

```bash
# SSH access (run once from Proxmox host)
pct exec <VMID> -- mkdir -p /root/.ssh
cat ~/.ssh/id_ed25519.pub | pct exec <VMID> -- tee /root/.ssh/authorized_keys
pct exec <VMID> -- chmod 700 /root/.ssh
pct exec <VMID> -- chmod 600 /root/.ssh/authorized_keys

# Dentro do LXC
apt-get install -y git
mkdir /opt/apollo && cd /opt/apollo
# Clone only this folder (run on LXC 5)
git clone --no-checkout --filter=blob:none https://github.com/SchiavonJP/second-brain-automation.git
cd second-brain-automation
git sparse-checkout init --cone
git sparse-checkout set LXC_8_llama
git checkout main
cd LXC_8_llama
```

### 2. Configurar variáveis (opcional)

```bash
cp /opt/apollo/.env.example /opt/apollo/.env
# Editar se precisar alterar porta, ctx-size, ngl, etc.
nano /opt/apollo/.env
```

### 3. Rodar o setup

```bash
cd /opt/apollo
bash setup.sh
```

O script é **idempotente** — pode ser reexecutado sem problemas. Ele:
1. Instala o driver NVIDIA userspace (sem módulo de kernel)
2. Corrige o bug do `nvidia-smi` vazio
3. Instala o CUDA toolkit
4. Clona e compila o llama.cpp com CUDA (sm_86 = RTX 3060)
5. Baixa o modelo via `huggingface-cli`
6. Instala e inicia o serviço systemd

---

## Alternando modelos

| Preset | Modelo | VRAM | Tokens/s esperado |
|--------|--------|------|------------------|
| `qwen3` (default) | Qwen3.6-35B-A3B-MTP Q4_K_M | ~11.4 GiB (NGL=22) | ~25–35 t/s |
| `gemma3-12b` | Gemma 3 12B IT Q4_K_M | ~9 GiB (NGL=99) | ~60–100 t/s |

```bash
# Trocar para Gemma 3 12B (baixa modelo se necessário, não recompila llama.cpp)
MODEL_PRESET=gemma3-12b bash setup.sh
systemctl restart llama-server

# Voltar para Qwen3.6
MODEL_PRESET=qwen3 bash setup.sh
systemctl restart llama-server
```

Setup.sh é idempotente — ao trocar preset, apenas atualiza o env file, regenera o wrapper script e reinicia o serviço. O download só acontece se o GGUF ainda não existe em `/models`.

---

## Gerenciar os serviços

```bash
# Inference (Qwen3.6 — porta 8080)
systemctl status llama-server
systemctl restart llama-server
journalctl -u llama-server -f

# Embeddings (bge-m3 — porta 8081)
systemctl status bge-embedding
systemctl restart bge-embedding
journalctl -u bge-embedding -f
```

Para trocar parâmetros, edite `/etc/llama-server.env` ou `/etc/bge-embedding.env` e reinicie o serviço correspondente.

---

## Verificação

```bash
# GPU visível
nvidia-smi

# API respondendo
curl http://localhost:8080/health

# Teste de inferência
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.6-35b-mtp",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 64
  }'

# Via LiteLLM (do host ou qualquer máquina na rede)
curl http://192.168.0.211:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local-coder","messages":[{"role":"user","content":"Hello"}],"max_tokens":32}'

# Embedding direto (bge-m3 — porta 8081)
curl http://localhost:8081/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-m3","input":"Apollo homelab embedding test"}'
```

---

## Performance esperada

**llama-server — Qwen3.6 (porta 8080)**

| Métrica | Valor estimado |
|---------|---------------|
| VRAM usada | ~10–11 GB (Q4_K_M, NGL=45) |
| RAM usada | ~13–15 GB (camadas offloaded + KV cache) |
| Tokens/s geração | 50–80 tok/s com MTP |
| Contexto | 32K tokens |
| TTFT | ~1–3 segundos |

**bge-embedding — bge-m3 (porta 8081)**

| Métrica | Valor estimado |
|---------|---------------|
| VRAM usada | ~570 MB (Q4_K_M, NGL=99) |
| Throughput | ~500–1000 embeddings/s |
| Dimensão do vetor | 1024 |
| Contexto máx | 8192 tokens |

---

## Troubleshooting

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| `/dev/nvidia0 not found` | GPU passthrough não configurado | Adicionar linhas ao `/etc/pve/lxc/NNN.conf` (ver acima) |
| `nvidia-smi: not found` | Bug do pacote vazio | O setup.sh extrai do `.run` automaticamente |
| `CUDA not found` no build | PATH incorreto | `export PATH=/usr/local/cuda/bin:$PATH` e rerodar cmake |
| `spec-type mtp` ignorado | GGUF sem cabeças MTP | Usar especificamente o GGUF com sufixo `-MTP` |
| Tok/s baixo apesar do MTP | `draft-p-min` rejeitando tudo | Preset qwen3 usa 0.40 por default; conferir `/etc/llama-server.env` |
| OOM ao carregar modelo (`CUDA0 buffer`) | NGL muito alto — MoE tem ~28 blocos; NGL > 28 = modelo inteiro (~20GB) na GPU | Reduzir `LLAMA_NGL` para ≤22 (bge-m3 na CPU) |
| Gemma 3 falha ao iniciar com `spec-type mtp` | Preset antigo ainda no env | `MODEL_PRESET=gemma3-12b bash setup.sh` regenera o wrapper sem MTP flags |
| Contexto 32K causa OOM mesmo com NGL baixo | KV cache pre-alocado é proporcional ao ctx | Usar `LLAMA_CTX_SIZE=8192`; aumentar ctx só após confirmar NGL estável |
| bge-embedding OOM ao iniciar | VRAM apertada com Qwen3.6 | Reduzir `LLAMA_NGL` para 38–40 para liberar ~1GB |
| `/v1/embeddings` retorna 404 | Serviço não iniciado ou sem flag `--embedding` | `systemctl start bge-embedding` e verificar logs |
