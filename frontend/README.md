# DealMind AI — Basket Intelligence Frontend

Vue 3 + Vite dashboard for historical e-commerce funnel analytics (Oct 2019 – Feb 2020), zero-leakage February 2020 cart session replay, and purchase intent model benchmarks.

## Local Setup

```bash
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite (default `http://localhost:5173`).

## Production Build

```bash
cd frontend
npm run build
npm run preview
```

## Connecting to the FastAPI Backend

1. Copy `.env.example` to `.env.local` (optional — defaults work out of the box):
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   VITE_USE_MOCK=auto
   ```
2. Start the FastAPI backend on `http://localhost:8000`.
3. The navbar status indicator checks `GET /api/health` automatically:
   - **API Connected | FastAPI Local** (green) when the backend responds.
   - **Mock Mode | Local Preview** (amber) when running offline against the bundled SQLite snapshot (`src/services/mock/`).
4. Use the **Settings (`⚙`)** button in the top-right navbar to switch between **Auto**, **Live API Only**, and **Mock Data Mode**, or to override the API Base URL at runtime.

## Routes

- `/` — **Analytics**: Period filter (`ALL`, `Oct`–`Feb`), 5 funnel KPIs, interactive 3-zone wireframe basket funnel, monthly trend Chart.js chart, and model comparison.
- `/replay` & `/replay/:id` — **Session Replay**: Paginated 100 curated Feb 2020 cart sessions, interactive 3-zone path visualization, zero-leakage timeline with `PREDICTION CUTOFF`, `/api/predict` card, and explicit `Reveal outcome` workflow.
- `/models` — **Models**: Role 5 Logistic Regression baseline metrics & drivers, Role 6 Random Forest slot, temporal split integrity, Role 4 cart behavior & catalog intelligence, and Role 3 funnel summary slot.
