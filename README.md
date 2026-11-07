# Open-Source Corpus Explorer

React + TypeScript + Vite frontend and Python FastAPI backend.

## Requirements

- Node.js 20.19+ or 22.12+
- Python 3.10+

## Backend

From the project root:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
cd backend
.venv/bin/python -m uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000/api/health

Interactive API docs: http://127.0.0.1:8000/docs

## Frontend

In a second terminal, from the project root:

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The starter page displays the backend connection status.
Vite proxies `/api` requests to `http://127.0.0.1:8000`, so no local CORS configuration is needed.

## Production build

```sh
cd frontend
npm run build
```

The frontend build is written to `frontend/dist`. For deployment, serve these static files
and route `/api` to the FastAPI service on the same origin. `npm run preview` previews
static assets only; its server does not provide the development API proxy.

See [PRD.md](PRD.md) for the product requirements.
