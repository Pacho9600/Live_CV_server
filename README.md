# Server (FastAPI)

Run:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On startup (dev/local), the server auto-creates the DB tables and seeds the example user if missing.
Disable or override via env vars in `.env` (see `.env.example`).

Relevant routes:
- Browser login:
  - GET  `/desktop/login?...` (HTML)
  - POST `/desktop/login`       (form submit)
- Browser registration (multi-step):
  - GET  `/desktop/register` (Step 1: Data)
  - Steps: `/desktop/register/email`, `/desktop/register/2fa`, `/desktop/register/payment`, `/desktop/register/review`
- Desktop exchange:
  - POST `/api/auth/desktop/exchange` (PKCE verify + returns JWT)
- API:
  - GET `/api/auth/me`
  - GET `/health`

DB:
- SQLite file `app.db` in the repo root by default (`Live_CV_server/app.db`).
- Stripe payment step requires `STRIPE_SECRET_KEY` (see `.env.example`).
