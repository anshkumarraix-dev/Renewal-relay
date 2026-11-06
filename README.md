# Renewal Relay

> **An AI-powered PayPal subscription renewal recovery and merchant intelligence platform.**

Renewal Relay recovers failed subscription billing cycles, provides predictive renewal analytics, and orchestrates intelligent payment recovery workflows while adhering to strict fintech governance and PCI-DSS compliance standards.

---

## Architectural Principles & Security Rules

1. **PayPal Remains the Payment Authority:**  
   PayPal is the sole authority for billing agreement executions, payment captures, and tokenization. Renewal Relay does not simulate, fabricate, or act as an independent payment processor.
2. **Zero Raw Credential Storage:**  
   Primary Account Numbers (PANs), CVVs, CVCs, and bank account numbers are **never stored, logged, or processed** on Renewal Relay servers.
3. **Strict Credential & Secret Isolation:**  
   The `PAYPAL_CLIENT_SECRET` lives strictly in secure backend environment variables. It is never exposed, bundled, or transmitted to the frontend client.
4. **Deterministic Policy & Merchant Authorization Gate:**  
   AI models generate recovery diagnoses and predictive recommendations only. AI cannot autonomously trigger payment captures. All renewal retry executions require deterministic policy checks and merchant authorization.
5. **Mandatory External Verification:**  
   Every payment event must be verified directly via PayPal Sandbox/REST webhooks or API status queries.
6. **Isolated Sandbox Mode:**  
   Development and local testing are strictly bound to the PayPal Sandbox environment.

---

## Tech Stack

| Layer | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Backend Framework** | FastAPI | `^0.115.0` | High-performance asynchronous API layer |
| **Runtime** | Python | `3.14.7` | Backend application runtime |
| **ORM** | SQLAlchemy | `^2.0.0` | Database ORM, connection pooling, and lifecycle management |
| **Database** | SQLite | `3` | Local development database store |
| **Configuration** | Pydantic Settings | `^2.4.0` | Strongly-typed environment parsing and secret masking |
| **HTTP Client** | HTTPX | `^0.27.0` | Asynchronous external HTTP communications (PayPal REST API) |
| **Frontend Framework** | React | `^19.3.0` | Component-driven user interface |
| **Tooling** | Vite | `^8.3.0` | Fast frontend build tool and dev server |
| **Language** | TypeScript | `~6.0.0` | Type-safe development across the frontend |
| **Icons & UI** | Lucide React | `^1.70.0` | Telemetry, security, and status iconography |

---

## Project Structure

```text
Renewal-Relay/
├── .env.example                   # Master environment variables template
├── .gitignore                     # Comprehensive repository exclusion rules
├── README.md                      # Architecture guide and setup instructions
│
├── backend/
│   ├── .env.example               # Backend environment template
│   ├── requirements.txt           # Python dependency declarations
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI entry point, lifespan, CORS, route mounting
│   │   ├── core/
│   │   │   ├── config.py          # Pydantic Settings with safe defaults & secret redaction
│   │   │   ├── database.py        # SQLAlchemy engine, session factory, SQLite health probes
│   │   │   └── logging.py         # Structured logging with automatic token & PAN scrubbing
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── api.py         # Router composition for API v1
│   │   │   │   └── endpoints/
│   │   │   │       └── health.py  # Health check with separate app and DB status reports
│   │   └── schemas/
│   │       └── health.py          # Pydantic models for health telemetry
│   └── tests/
│       ├── __init__.py
│       └── test_foundation.py     # Unit tests: health, DB connection, 503 degraded, config
│
└── frontend/
    ├── .env.example               # Frontend environment template (VITE_ public variables only)
    ├── package.json               # Node dependencies and scripts
    ├── tsconfig.json              # TypeScript compilation configuration
    ├── vite.config.ts             # Vite build configuration
    └── src/
        ├── api/
        │   └── client.ts          # Axios client with robust error fallback handling
        ├── types/
        │   └── health.ts          # TypeScript interfaces for system health telemetry
        ├── components/
        │   ├── Header.tsx         # Platform header with environment badges
        │   ├── SystemStatusCard.tsx # Real-time component health monitor
        │   └── GovernanceBanner.tsx # Security boundaries and deterministic policy indicators
        ├── App.tsx                # Foundation dashboard assembly
        ├── App.css                # Polished theme and responsive layout
        └── main.tsx               # React application entry point
```

---

## Getting Started

### 1. Prerequisites
- **Python:** 3.14+ (or 3.11+)
- **Node.js:** 20+ with `npm` 10+
- **Git**

### 2. Environment Configuration
Copy `.env.example` templates to `.env`:

```bash
# Backend configuration
copy backend\.env.example backend\.env

# Frontend configuration
copy frontend\.env.example frontend\.env
```

Review `backend/.env` to confirm the settings:
- `ENVIRONMENT=development`
- `DATABASE_URL=sqlite:///./renewal_relay.db`
- `PAYPAL_MODE=sandbox`
- `CORS_ORIGINS=["http://localhost:5173", "http://127.0.0.1:5173"]`

### 3. Backend Setup & Run

Activate the existing virtual environment or create one:
```powershell
# Activate virtual environment (Windows)
.\backend\.venv\Scripts\Activate.ps1

# Run the FastAPI development server
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

The interactive documentation will be available at:
- Swagger UI: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/api/v1/health`
- Liveness Probe: `http://localhost:8000/api/v1/health/live`

### 4. Frontend Setup & Run

In a separate terminal:
```powershell
cd frontend

# Start the Vite development server
npm run dev
```

Open your browser at `http://localhost:5173` to view the Renewal Relay foundation telemetry dashboard.

---

## Development Commands Reference

| Task | Command | Directory |
| :--- | :--- | :--- |
| **Run Backend Server** | `python -m uvicorn app.main:app --app-dir backend --reload --port 8000` | Root |
| **Run Backend Tests** | `python -m unittest discover -s backend/tests -p "test_*.py" -v` | Root |
| **Run Frontend Dev Server** | `npm run dev` | `frontend/` |
| **Build Frontend** | `npm run build` | `frontend/` |
| **Lint Frontend** | `npm run lint` | `frontend/` |

---

## Verification & Testing

### Running Backend Unit Tests
Execute the comprehensive foundation test suite:
```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_*.py" -v
```

The test suite validates:
1. **Application Health (`/api/v1/health`):** Verifies 200 OK with separate `app` and `database` statuses.
2. **Database Connectivity:** Executes a live `SELECT 1` query via SQLAlchemy on SQLite and records latency.
3. **Database Failure Handling:** Simulates an `OperationalError` on the database session and verifies that the endpoint gracefully reports `degraded` status with HTTP `503 Service Unavailable`.
4. **Configuration Safety:** Validates default settings, rejects unsafe `*` CORS wildcards, and ensures sensitive credentials are redacted in logs and outputs.

### Building Frontend
Verify TypeScript types and Vite production bundling:
```powershell
cd frontend
npm run build
npm run lint
```

---

## Security & Governance Implementation

- **Sanitized Logging:** All log messages pass through `SensitiveDataFilter`, automatically masking access tokens (`Bearer ...`), client secrets, and potential 13-19 digit card PAN patterns.
- **CORS Protection:** Whitelists only local development origins (`http://localhost:5173` and `http://127.0.0.1:5173`). Wildcard `*` origins are rejected by Pydantic configuration validators.
- **Git Exclusions:** SQLite database files (`*.db`), virtual environments (`.venv`), `.env` secrets, and build outputs (`dist/`, `node_modules/`) are strictly excluded in `.gitignore`.

---

## Roadmap

- [x] **Milestone 1: Development Foundation** (Current)
  - FastAPI health check with SQLAlchemy SQLite connectivity
  - React + TypeScript dashboard with live telemetry
  - Structured logging with credential redaction
  - Test suite with 100% pass rate
- [ ] **Milestone 2: PayPal Sandbox Integration**
  - OAuth 2.0 client credential token exchange via HTTPX
  - Subscription details lookup and billing cycle parsing
  - PayPal Webhook signature verification
- [ ] **Milestone 3: Deterministic Policy Engine**
  - Dunning schedule rules and retry limits
  - Merchant recovery thresholds and pause conditions
- [ ] **Milestone 4: AI Failure Diagnosis & Recovery Intelligence**
  - Structured error classification (soft decline vs. hard decline)
  - Predictive renewal churn modeling
