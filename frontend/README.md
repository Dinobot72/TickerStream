# TickerStream AI — Frontend

Angular 21 single-page dashboard for TickerStream AI: login/registration, portfolio overview, positions, watchlist, manual trading, AI bot management, and account settings.

## Stack

- Angular 21 with **zoneless change detection** and **server-side rendering** (`@angular/ssr`)
- Angular Material (cards, buttons, form fields) + hand-rolled SCSS design system (see `styles.scss` CSS variables)
- Chart.js for the live portfolio chart
- RxJS for all HTTP/data flows; component state is otherwise signal-based
- Karma + Jasmine + Puppeteer-driven headless Chrome for unit tests

## Getting started

```bash
yarn install
yarn start          # ng serve --proxy-config proxy.conf.json, http://localhost:4200
```

`proxy.conf.json` forwards `/api/*` to `http://127.0.0.1:8000`, so run the [backend](../backend/README.md) alongside this for a working app.

```bash
yarn build                # production build → dist/stockBot
yarn test                 # Karma unit tests (headless Chrome via Puppeteer)
yarn serve:ssr:stockBot   # run the built SSR server directly
```

## Routing

```
/login                          → LoginComponent (also handles registration)
/dashboard            (guarded) → DashboardComponent (sidebar + router-outlet)
  ├── /                         → HomepageComponent (overview, chart, activity)
  ├── /positions                → PositionsComponent
  ├── /watchlist                → WatchlistComponent
  ├── /trading                  → TradingComponent
  ├── /ai-management            → AiManagementComponent
  └── /settings                 → SettingsComponent
```

`auth-guard.ts` protects everything under `/dashboard`, redirecting to `/login` if `AuthService.isAuthenticated()` resolves false.

## Auth flow

`AuthService` (signal-based: `isLoggedIn`, `currentUserId`, `currentUsername`) calls `/api/auth/status` on construction (browser only — guarded with `PLATFORM_ID`/`isPlatformBrowser` so it's skipped during SSR). `auth-interceptor.ts` adds `withCredentials: true` to every request under `/api/`, since the backend uses an `httponly` session cookie rather than a bearer token in local storage.

## Key components & services

- **`HomepageComponent`** — fetches balance/holdings/metrics/activity/trending stocks in parallel and renders a Chart.js line chart of portfolio value per holding, with selectable time spans (1D/1W/1M/1Y/5Y).
- **`PositionsComponent`** / **`WatchlistComponent`** — fetch holdings/watchlist then fan out per-ticker requests (price, metrics, change) via `forkJoin`, and auto-refresh on a `timer()` (30s / 60s respectively).
- **`TradingComponent`** — manual market/limit buy & sell form; reads a `ticker` query param so "Trade" links from Positions/Watchlist pre-fill the form.
- **`AiManagementComponent`** — bot start/stop toggle, and a client-side FIFO P/L + win-rate calculation over the bot's own trade history (`is_bot_trade` filtered).
- **`SettingsComponent`** — profile (first/last name) and password-change forms.
- **`AuthService`** / **`BotStatusService`** — shared signal/Observable state for auth and bot status, both SSR-safe.

## Testing

Run `yarn test` for the full Karma/Jasmine suite. Most components are tested across both `server` and `browser` `PLATFORM_ID` configurations to verify SSR-safe guards around `HttpClient` calls. Coverage reports are written to `coverage/frontend` (and uploaded as a CI artifact — see `.github/workflows/testing.yml`).

## Known issues / cleanup candidates

- `HomepageComponent` still has hardcoded placeholder data for `marketIndices` and the initial `portfolioHoldings`/`currentPrices` signals — these are overwritten once `fetchPortfolio()` etc. resolve, but are misleading defaults and could be replaced with proper empty-state UI.
- There are two parallel "portfolio value" computations in `HomepageComponent` (the `portfolioValue` signal set imperatively in `fetchPortfolio()`, and the `portfolioValueLive` computed signal) — worth consolidating into one source of truth.
- `frontend/Dockerfile` builds and runs the Angular **SSR Node server**, while `frontend/nginx.conf` configures an **nginx** static-file + reverse-proxy setup that doesn't appear to be referenced by that Dockerfile — likely a leftover from an earlier deployment approach; reconcile with the root-level `nginx.conf` used by `docker-compose.yml`.
- Double-check that `/login` prerendering in `app.routes.server.ts` doesn't go stale if backend URLs or auth requirements change, since `/dashboard/**` is intentionally client-rendered only.