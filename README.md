Plataforma de Segurança Digital — MVP funcional (PT-BR)

Este repositório entrega um MVP executável da plataforma: API (FastAPI), pipeline de regras, agente local (Linux) + instalador systemd, gerador de relatórios (HTML) e painel web estático bonito e responsivo.

Stack (Track A): FastAPI + SQLAlchemy + SQLite (padrão) — configure PostgreSQL via `DATABASE_URL` quando desejar.

Componentes
- `api/`: FastAPI, modelos, rotas públicas (ingest/consulta) e admin, score, incidentes, ativos, relatórios, rate limiting por tenant.
- `reports/`: Gerador de relatórios HTML (salvos e servidos via `/static`), registra histórico em banco.
- `agent/`: Agente Linux em Python (coleta tail de auth.log/secure/syslog), batch gzip com retry + registro do agente/host.
- `installer/`: `install.sh` que cria usuário de serviço, instala em `/opt/digitalsec-agent`, grava `config.yaml`, ativa systemd service + timer.
- `web/`: Painel web (SPA estático) com abas Home/Incidentes/Ativos/Relatórios/Config, filtros e tema claro/escuro.

Como rodar (desenvolvimento)
1) Pré-requisitos: Python 3.10+, `pip` (ou Docker).
2) Dependências: `pip install -r requirements.txt`
3) (Opcional) `.env`: copie `.env.example` para `.env` e ajuste `DATABASE_URL`/`API_SECRET`. Para autenticação do painel, defina `ADMIN_EMAIL` e `ADMIN_PASSWORD` (cria usuário automaticamente no tenant demo).
4) API: `uvicorn api.main:app --reload --port 8000`
5) Painel: abra `web/index.html` (configure API `http://localhost:8000` e Token `demo-token`).

Docker
- Build: `docker build -t digitalsec-api .`
- Run: `docker run -p 8000:8000 -v $(pwd)/data:/app/data digitalsec-api`

Banco de dados
- Padrão: SQLite em `./data/app.db`. Para PostgreSQL: `export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db`.

Segurança (MVP)
- Ingest por Bearer token (por tenant). Idempotência via `batch_id` e limiter por minuto.
- Admin: cabeçalho `X-API-Secret` (defina `API_SECRET` em ambiente). Endpoints: criar tenant e girar token.
- Autenticação do painel (opcional): `POST /auth/login` com e‑mail/senha (criar via `ADMIN_EMAIL` e `ADMIN_PASSWORD`). O painel tem modal de login; se não usar login, você pode informar um token manualmente em Config.

Agente Linux
- Script: `sudo bash installer/install.sh --token <TOKEN> --tenant <TENANT_ID> --api https://api.seu-dominio --source-dir .`
- Serviço: `digitalsec-agent.service` + `digitalsec-agent.timer`. Logs: `journalctl -u digitalsec-agent -f`

Endpoints principais
- `POST /v1/agents/register` — registra/atualiza agente e ativo (host).
- `POST /v1/ingest` — recebe lote gzip (opcional), valida idempotência, processa regras em background.
- `GET /v1/incidents` — últimos 200; `GET /v1/incidents/search` — filtros (severity/host/intervalo).
- `POST /v1/incidents/{id}/ack` — reconhecer incidente.
- `GET /v1/score` — nota 0–100 (janela padrão 7d).
- `GET /v1/assets` — hosts/OS/heartbeat/agent.
- `GET /v1/reports/latest` — gera e retorna URL; `GET /v1/reports` — histórico.
- `GET /v1/config` — flags/config do agente.
- `GET /v1/checklist` e `POST /v1/checklist/{key}/done` — recomendações geradas e marcação de concluído.
- `POST /v1/actions/block_ip` — bloqueio de IP (provider: local|cloudflare|aws_waf; Cloudflare requer tokens via env ou integrações do tenant).

Admin
- `POST /admin/tenants` (X-API-Secret) — cria tenant e token.
- `POST /admin/tenants/{id}/rotate-token` — gira token.
- `GET /admin/tenants` — lista tenants.
- `POST /admin/tenants/{id}/alert-email` — define e-mail de alertas.
- Integrações (via JSON no tenant): `integrations_json` suporta `cloudflare_token`, `cloudflare_account`. (Endpoints dedicados podem ser adicionados conforme necessidade.)

Limites e próximos passos
- Integrações de Threat Intel (AbuseIPDB/Shodan/IPinfo) a plugar (stubs por enquanto).
- Alertas: e-mail implementado (SMTP); WhatsApp/webhook a conectar via provedores.
- PDF: gerar a partir do HTML (WeasyPrint) quando libs do sistema estiverem disponíveis.
- Autenticação de painel (usuários) — colocar por trás de SSO/Keycloak/Next.js + JWT.

Relatórios (HTML/PDF)
- HTML sempre é gerado.
- PDF: por padrão REPORT_PDF=true no `.env.example`. Em ambientes sem libs de sistema, defina `REPORT_PDF=false`.
- A imagem Docker já instala as libs necessárias (libcairo, pango, gdk-pixbuf, fontes).

Docker Compose (API + Postgres)
- `docker-compose up --build`
- API em `http://localhost:8000`, banco Postgres persistido em volume `dbdata`.

Agendamentos
- Job diário de geração de relatórios (APScheduler) embutido no processo da API. Em ambientes com múltiplas réplicas, adotar um scheduler único/externo.

Notificações
- E‑mail: configure SMTP_* no `.env`. Incidentes críticos/altos geram notificações.
- WhatsApp/Telegram/Webhooks: endpoints stubs em `api/notifications.py` podem ser estendidos (não ativados por padrão neste MVP).

CI
- GitHub Actions executa testes (pytest) a cada push/PR em `main`.
- Build Docker (sem push) para validar a imagem em cada push/PR.
