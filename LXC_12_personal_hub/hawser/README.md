# Hawser — LXC 12 (Personal Hub)

> **Hostname LXC:** personal-hub
> **IP:** 192.168.0.221
> **Porta:** 2376

Agente do Dockhand (LXC 7) — expõe o Docker deste host pro pool de checagem
de atualização de imagem. Este LXC não tem um `docker-compose.yml` único no
topo (AFFiNE e Ryot têm cada um o seu, em `../affine/` e `../ryot/`), então
o Hawser ganhou sua própria pasta, seguindo o mesmo padrão.

Só precisa de **uma** instância de Hawser por host — mesmo com múltiplos
compose projects rodando no mesmo LXC (AFFiNE, Ryot), o socket do Docker é
o mesmo, então esse container enxerga todos eles.

---

## Deploy

```bash
cd /root/second-brain-automation/LXC_12_personal_hub/hawser

cp .env.example .env
nano .env   # preencher HAWSER_TOKEN (gerado no Dockhand)

docker compose -f compose.yml up -d
```

## Registrar no Dockhand

1. `dockhand.joaopaulo.me` → **Settings → Environments → Add new environment**
2. Tipo de conexão: **Standard**
3. Host: `192.168.0.221:2376`
4. Copiar o token gerado (só aparece uma vez) pro `.env` antes de fechar a tela
5. Aba **Updates** → habilitar checagem agendada, **deixar
   "Automatically update containers" desligado** (modo notificação — os
   containers deste repo já seguem versão pinada, nunca `:latest`)

## Verificação

```bash
docker compose ps
curl http://192.168.0.221:2376
```

No Dockhand, o ambiente deve aparecer "Connected" e listar `affine_server`,
`affine_postgres`, `affine_redis`, `ryot_app`, `ryot_postgres`.
