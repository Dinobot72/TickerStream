# TickerStream AI

TickerStream AI is a full-stack stock trading platform that pairs a live Angular dashboard with a FastAPI backend and a custom-trained reinforcement learning trading bot. Users can track a portfolio, watch a personalized watchlist, place manual trades, and toggle on an autonomous bot that trades on their behalf using a `RecurrentPPO` model trained with `stable-baselines3` / `sb3-contrib`.

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌────────────────────┐
│   Angular   │ HTTP │     FastAPI       │      │   RecurrentPPO      │
│  Frontend   │◄────►│     Backend       │◄────►│   Trading Model     │
│ (SSR, :4200)│      │ (uvicorn, :8000)  │      │ (sb3-contrib/torch) │
└─────────────┘      └────────┬─────────┘      └────────────────────┘
                               │
                         ┌─────▼─────┐
                         │  SQLite   │
                         │  Database │
                         └───────────┘
```

In production, an `nginx` gateway container proxies `/api/*` to the backend and serves the built frontend, with a Cloudflare tunnel exposing the stack publicly (see `docker-compose.yml`).

## Repository layout

| Path | Description |
| --- | --- |
| `backend/` | FastAPI service: auth, portfolio, trading endpoints, risk management, and the live trading bot scheduler. See [backend/README.md](backend/README.md). |
| `frontend/` | Angular 21 SSR dashboard (login, positions, watchlist, trading, AI management, settings). See [frontend/README.md](frontend/README.md). |
| `model/` | Gymnasium training environment, RecurrentPPO training/evaluation scripts, and a live training monitor. See [model/README.md](model/README.md). |
| `docker-compose.yml`, `nginx.conf` | Container orchestration for backend + frontend + nginx gateway + Cloudflare tunnel. |
| `.github/workflows/` | CI: Angular unit tests on every branch push, and an AI-generated summary comment on new GitHub issues. |

## Tech stack

- **Frontend:** Angular 21 (zoneless change detection, SSR), Angular Material, Chart.js, Tailwind (CDN), Karma/Jasmine.
- **Backend:** FastAPI, Pydantic, PyJWT + cookie-based auth, SQLite, `yfinance` for market data.
- **Machine learning:** Gymnasium custom environment, `stable-baselines3`/`sb3-contrib` `RecurrentPPO`, PyTorch.
- **Infra:** Docker Compose, nginx reverse proxy, Cloudflare Tunnel, GitHub Actions.

## Getting started

### Option A — Docker Compose

```bash
docker compose up --build
```

This builds the backend and frontend images and starts them behind the `gateway` (nginx) and `tunnel` (Cloudflare) services defined in `docker-compose.yml`.

### Option B — Run services manually

```bash
# Backend
cd backend
pip install -r requirements.txt
pip install -r ../model/requirements.txt
uvicorn app.main:app --reload          # http://localhost:8000

# Frontend (separate terminal)
cd frontend
yarn install
yarn start                              # http://localhost:4200, proxies /api to :8000
```

See each subdirectory's README for environment variables, database schema, and model training instructions.

## Notes on current state

This is an actively evolving project. A few things worth knowing before deploying anywhere public:

- `docker-compose.yml` currently has a real Cloudflare tunnel token and a placeholder `SECRET_KEY` committed in plaintext — both must be rotated and moved to a real secrets store before any public deployment.
- The `ai_bridge` integration in `backend/app/routers/trading.py` is commented out, and the AI scorer/portfolio manager have some signature mismatches between the live-inference code path and the legacy code path — see `backend/README.md` for details.
- `backend/app/services/services.py` duplicates `market_data.py` and appears unused; it's a candidate for removal.

## License

No license file is currently included — add one before distributing this project publicly.