# Finz pipeline frontend

Minimal React + Vite single-page app implementing the required workflow (PDF
section 5): upload & map, review & classify, monthly/consolidated P&L, sync to
QuickBooks, and reconciliation.

```bash
npm install
cp .env.example .env   # points at the backend, defaults to localhost:8000
npm run dev
```

Talks to the FastAPI backend in `../backend` over plain `fetch` - no state
library, no router (five tabs, one screen each, so `useState` is enough). See
the root `README.md` for the full architecture writeup.
