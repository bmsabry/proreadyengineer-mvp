# ProReadyEngineer — Complete Handoff Document

> **⚠️ This handoff doc is partly historical.** For the *current* architecture,
> money model, RFQ/dispatch/NDA/payment flows, statuses, and known constraints,
> read **`ARCHITECTURE.md`** (kept up to date) and **`CODE_AUDIT_2026-05-28.md`**.
> Sections below marked as 'open issues' from April 2026 have largely been
> resolved in the May 2026 cleanup — see ARCHITECTURE.md §11 for the live backlog.


> **For the receiving agent:** Read this first, then `DEVELOPMENT_HISTORY.md`, then load `secrets.env`.

---

## 1. Project Overview

**Product:** ProReadyEngineer (also referred to internally as ProMechDirectory)  
**Purpose:** B2B marketplace that matches engineering service-provider firms with customers who have complex engineering projects. Customers submit RFQs (Requests for Quote), providers receive teaser emails and pay to unlock full RFQ details, then submit rough quotes. The platform also supports advertising slots for software vendors and featured firms.  
**Target Users:** Engineering firms (providers), companies needing engineering services (customers), software tool vendors (advertisers)  
**Status:** MVP — built, deployed on Render, partially functional. Core auth, search, provider profiles, RFQ flow, payment stubs, admin backoffice, and customer/provider dashboards are implemented. Several advanced flows (NDA signing, full Stripe/PayPal webhook fulfillment) are wired but need real credentials and end-to-end testing.  
**Live URLs:**
- Frontend: https://proreadyengineer-web.onrender.com
- Backend API: https://proreadyengineer-api.onrender.com
- API Docs (Swagger): https://proreadyengineer-api.onrender.com/docs

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     BROWSER / CLIENT                         │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTPS
┌────────────────────────────▼─────────────────────────────────┐
│             Next.js 15 Frontend (Render: web)                │
│  App Router · TypeScript · Tailwind · shadcn/ui              │
│  https://proreadyengineer-web.onrender.com                   │
└────────────────────────────┬─────────────────────────────────┘
                             │ REST API calls (NEXT_PUBLIC_API_URL)
┌────────────────────────────▼─────────────────────────────────┐
│           FastAPI Backend (Render: web)                      │
│  Python 3.11 · SQLAlchemy · Alembic · slowapi               │
│  https://proreadyengineer-api.onrender.com                   │
└──────┬──────────────┬──────────────┬────────────────────┬────┘
       │              │              │                    │
┌──────▼──────┐ ┌─────▼──────┐ ┌────▼──────┐ ┌──────────▼────┐
│ PostgreSQL  │ │   Redis    │ │ DeepInfra │ │  AWS S3       │
│ + pgvector  │ │  (Celery   │ │ AI API    │ │  (file store) │
│ Render: db  │ │  broker)   │ │ (ext.)    │ │  (ext.)       │
└─────────────┘ └────────────┘ └───────────┘ └───────────────┘

External integrations:
  Stripe ──── payment processing & subscriptions
  PayPal ──── alternative payment option
  SignWell ── NDA document signing (embedded iframe)
  Resend ──── transactional email
  Sentry ──── error tracking (optional)

Background jobs:
  Celery tasks defined in backend/app/tasks/ BUT no separate
  Celery worker is deployed on Render. Instead, an asyncio
  background loop runs inside the FastAPI process as a backup
  dispatch trigger. The Render Cron Job is the primary trigger.
```

### Request Flow (Search)
1. User types natural language query on landing page
2. Frontend POSTs to `/api/v1/search/query`
3. Backend normalises query, calls DeepInfra LLM (Kimi-K2.5) for structured intent extraction
4. Backend generates query embedding via DeepInfra (BAAI/bge-large-en-v1.5)
5. pgvector cosine similarity selects top-50 candidates
6. Deterministic 100-point scoring (specialty 25 + capabilities 50 + tier 25)
7. Top-5 results returned with score breakdown

---

## 3. Directory Map

```
proreadyengineer-mvp/               ← GitHub repo root (= deploy/ folder)
│
├── backend/                        ← FastAPI application
│   ├── main.py                     ← App entry point, lifespan, middleware, router registration
│   ├── requirements.txt            ← Python dependencies (pinned versions)
│   ├── alembic.ini                 ← Alembic config pointing to DATABASE_URL
│   ├── alembic/versions/           ← 22 migration files (run in order)
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py           ← Pydantic Settings — ALL env vars documented here
│   │   │   ├── celery.py           ← Celery app instance
│   │   │   └── rate_limiter.py     ← slowapi limiter instance
│   │   ├── db/
│   │   │   ├── session.py          ← AsyncSessionLocal, engine, close_db
│   │   │   └── base.py             ← SQLAlchemy Base import
│   │   ├── models/                 ← SQLAlchemy ORM models
│   │   │   ├── user.py             ← User, RefreshToken, PasswordResetToken
│   │   │   ├── provider.py         ← Provider, ProviderMembership, ProviderClaimRequest, TierEvalRequest
│   │   │   ├── rfq.py              ← RFQ, RFQFile, RFQMatch, RFQDispatch, RFQUnlock
│   │   │   ├── quote.py            ← Quote, QuoteFile
│   │   │   ├── payment.py          ← PaymentAttempt, Subscription, WebhookEvent
│   │   │   ├── nda.py              ← RFQNDA
│   │   │   ├── advertising.py      ← AdSlot, Advertisement
│   │   │   ├── campaign.py         ← ProviderCampaign (email campaign feature)
│   │   │   ├── search.py           ← SearchRequest, IPUsageTracking
│   │   │   ├── admin.py            ← AuditLog
│   │   │   ├── support.py          ← SupportTicket, SupportMessage
│   │   │   ├── system_config.py    ← SystemConfig (admin-editable settings)
│   │   │   └── enums.py            ← All SQLAlchemy Enum types
│   │   ├── schemas/                ← Pydantic request/response schemas
│   │   ├── services/               ← Business logic layer
│   │   │   ├── auth_service.py     ← JWT, bcrypt, token management
│   │   │   ├── search_service.py   ← AI pipeline, embedding, scoring
│   │   │   ├── rfq_service.py      ← RFQ lifecycle, dispatch batching
│   │   │   ├── payment_service.py  ← Stripe + PayPal checkout, webhook handling
│   │   │   ├── nda_service.py      ← SignWell integration
│   │   │   ├── email_service.py    ← Resend integration, HTML templates
│   │   │   ├── file_service.py     ← S3 presigned URLs, local file fallback
│   │   │   ├── campaign_service.py ← Provider email campaign logic
│   │   │   └── config_service.py   ← SystemConfig CRUD
│   │   ├── api/endpoints/          ← FastAPI routers
│   │   │   ├── auth.py             ← /api/v1/auth/*
│   │   │   ├── search.py           ← /api/v1/search/*
│   │   │   ├── providers.py        ← /api/v1/providers/* + /api/v1/provider/*
│   │   │   ├── rfqs.py             ← /api/v1/rfqs/* + /api/v1/provider/rfqs/*
│   │   │   ├── quotes.py           ← /api/v1/customer/quotes + /api/v1/provider/quotes
│   │   │   ├── payments.py         ← /api/v1/webhooks/* + /api/v1/billing/*
│   │   │   ├── ads.py              ← /api/v1/ads/* + /api/v1/advertiser/*
│   │   │   ├── admin.py            ← /api/v1/admin/*
│   │   │   ├── campaigns.py        ← /api/v1/campaigns/*
│   │   │   ├── support.py          ← /api/v1/support/*
│   │   │   └── internal.py         ← /api/v1/internal/cron/* (cron trigger)
│   │   └── tasks/                  ← Celery task definitions
│   │       ├── rfq_tasks.py
│   │       ├── email_tasks.py
│   │       ├── search_tasks.py
│   │       └── crawl_tasks.py
│   ├── tests/                      ← pytest test suite
│   │   ├── integration/            ← API integration tests
│   │   └── unit/                   ← Unit tests for services
│   └── generate_embeddings.py      ← One-time backfill script for provider embeddings
│
├── frontend/                       ← Next.js 15 application
│   ├── src/
│   │   ├── app/                    ← Next.js App Router pages
│   │   │   ├── page.tsx            ← Landing page (search bar, tollgate map, nav)
│   │   │   ├── layout.tsx          ← Root layout with AuthContext, ConfigContext
│   │   │   ├── admin/              ← Admin backoffice pages
│   │   │   ├── customer/           ← Customer dashboard, RFQ flow, quotes
│   │   │   ├── provider/           ← Provider dashboard, profile, claim, RFQs
│   │   │   ├── search/             ← Search results page
│   │   │   ├── login/, register/   ← Auth pages
│   │   │   ├── advertise/          ← Ad purchase page
│   │   │   ├── featured-firms/     ← Public ad display page
│   │   │   ├── software-providers/ ← Public ad display page
│   │   │   └── nda/               ← NDA signing page (embedded SignWell)
│   │   ├── components/             ← Reusable React components
│   │   │   ├── ui/                 ← shadcn/ui base components
│   │   │   ├── search/             ← AI pipeline debug panel
│   │   │   ├── payment/            ← Stripe + PayPal payment components
│   │   │   ├── setup/              ← Admin setup wizard
│   │   │   └── admin/              ← Admin nav component
│   │   ├── contexts/
│   │   │   ├── AuthContext.tsx      ← Global auth state, login/logout, user info
│   │   │   └── ConfigContext.tsx    ← SystemConfig context (admin-editable settings)
│   │   ├── hooks/
│   │   │   ├── useApi.ts           ← Fetch wrapper with auth token injection
│   │   │   └── useAuth.ts          ← Auth hook shorthand
│   │   ├── lib/
│   │   │   ├── api.ts              ← API base URL, typed request helpers
│   │   │   └── utils.ts            ← Tailwind cn() helper
│   │   └── types/
│   │       └── index.ts            ← Shared TypeScript interfaces
│   └── public/
│       ├── favicon.svg
│       └── robots.txt
│
├── scripts/                        ← Database migration utilities
│   ├── engineering_directory.db    ← SOURCE: original SQLite provider database (6000+ firms)
│   ├── migrate_sqlite_to_postgres.py ← Full migration script (SQLite → PostgreSQL)
│   ├── migrate_providers.py        ← Providers-only migration
│   └── detect_and_resolve_duplicates.py ← Deduplication utility
│
├── render.yaml                     ← Render Blueprint (all services defined here)
├── .env.example                    ← Template for all env vars (safe to commit)
├── api_contract_v1.md              ← Full API route contract (63 routes)
└── DEPLOYMENT_GUIDE.md             ← Step-by-step deployment walkthrough
```

---

## 4. Local Dev Setup

### Prerequisites
- Python 3.11+
- Node.js 20+ (Next.js 15 requires Node 18.17+)
- PostgreSQL 15+ with pgvector extension (or use SQLite for local dev)
- Redis (or skip for local dev — Celery tasks won't run)

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and configure env
cp .env.example .env
# Edit .env — for local dev the defaults use SQLite (sqlite+aiosqlite:///./proready.db)
# No PostgreSQL needed for local dev!

# Run database migrations (creates tables in proready.db for SQLite or PostgreSQL)
python local_migrate.py       # SQLite local dev
# OR for PostgreSQL:
alembic upgrade head

# Start backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

### Frontend
```bash
cd frontend
npm install --legacy-peer-deps   # IMPORTANT: must use --legacy-peer-deps (React 19 peer dep issues)
npm run dev                       # http://localhost:3000
```

### Key env for local dev
```
# backend/.env
DATABASE_URL=sqlite+aiosqlite:///./proready.db   # SQLite, no postgres needed
SECRET_KEY=any-random-string-for-local
FRONTEND_URL=http://localhost:3000
OPENAI_API_KEY=your-deepinfra-key   # Required for AI search
OPENAI_API_BASE=https://api.deepinfra.com/v1/openai
STRIPE_SECRET_KEY=sk_test_...   # Test mode OK
EMAIL_PROVIDER=console   # Prints emails to terminal, no Resend needed
STORAGE_TYPE=local   # Files stored locally, no S3 needed

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

### Running Tests
```bash
cd backend
pytest tests/unit/ -v
pytest tests/integration/ -v
```

### Build (production)
```bash
cd frontend
npm run build    # Produces .next/ directory
```

---

## 5. Deployment (Render)

All services are defined in `render.yaml` at repo root. Use Render Blueprints.

### Services

| Service Name | Type | Plan | Purpose |
|---|---|---|---|
| `proreadyengineer-api` | Web (Python) | Starter | FastAPI backend |
| `proreadyengineer-web` | Web (Node) | Starter | Next.js frontend |
| `proreadyengineer-redis` | Redis | Starter | Celery broker / cache |
| `proreadyengineer-db` | PostgreSQL | Basic-256mb | Primary database |
| `proreadyengineer-rfq-cron` | Cron | Starter | RFQ batch dispatch every 15min |

**Note:** Render service IDs (srv-xxxxx) are not stored here — retrieve them from the Render dashboard at https://dashboard.render.com after logging in.

### Deploy Commands
- **Build (API):** `cd backend && pip install -r requirements.txt`
- **Start (API):** `cd backend && alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Build (Web):** `cd frontend && rm -rf node_modules .next && rm -f tsconfig.tsbuildinfo && npm install --legacy-peer-deps && npm run build`
- **Start (Web):** `cd frontend && npx next start -p $PORT`

### Health Check
- API health: `GET https://proreadyengineer-api.onrender.com/health`

### Region
- Oregon (US West) — Render default

### Env Vars NOT in render.yaml (must be set manually in dashboard)
These are marked `sync: false` — they must be added manually per service:
- `OPENAI_API_KEY` — DeepInfra key (despite name, points to DeepInfra)
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `RESEND_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `SIGNWELL_API_KEY`
- `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID`
- `PAYPAL_SANDBOX_CLIENT_ID`, `PAYPAL_SANDBOX_CLIENT_SECRET`, `PAYPAL_SANDBOX_WEBHOOK_ID`
- `SENTRY_DSN` (optional)
- `CRON_SECRET` (optional, for securing cron endpoint)
- `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` (on frontend service)

### Post-Deploy Steps
1. Set up Stripe webhook: `https://proreadyengineer-api.onrender.com/api/v1/webhooks/stripe`
   - Events: `payment_intent.succeeded`, `invoice.paid`, `customer.subscription.deleted`
2. Set up PayPal webhook pointing to: `/api/v1/webhooks/paypal`
3. Set up SignWell webhook pointing to: `/api/v1/webhooks/signrequest`
4. Create initial admin user via `/api/v1/auth/register` then manually set `is_super_admin=true` in DB
5. Run provider embedding backfill: `python backend/generate_embeddings.py`

---

## 6. External Services

| Service | Purpose | Docs | Env Var | Notes |
|---|---|---|---|---|
| **DeepInfra** | AI embeddings + LLM | https://deepinfra.com/docs | `OPENAI_API_KEY` | OpenAI-compatible API. Uses BAAI/bge-large-en-v1.5 for embeddings, moonshotai/Kimi-K2.5 for LLM |
| **Stripe** | Payments + subscriptions | https://docs.stripe.com | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | In test mode for MVP. Webhook required for payment fulfillment |
| **PayPal** | Alternative payments | https://developer.paypal.com/docs | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` | Sandbox mode for MVP. `PAYPAL_MODE=sandbox` in render.yaml |
| **SignWell** | NDA document signing | https://www.signwell.com/api/v1/ | `SIGNWELL_API_KEY` | Embedded iframe signing flow. Note: Originally specced as SignRequest, changed to SignWell |
| **Resend** | Transactional email | https://resend.com/docs | `RESEND_API_KEY` | From: noreply@proreadyengineer.com. Rate limit: 100 emails/day free tier |
| **AWS S3** | File storage | https://docs.aws.amazon.com/s3 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME` | Bucket: promechdirectory-uploads. Presigned URLs for uploads and downloads |
| **Sentry** | Error tracking | https://docs.sentry.io | `SENTRY_DSN` | Optional — gated on env var. traces_sample_rate=0.1 |
| **Render** | Hosting | https://render.com/docs | `RENDER_API_KEY` | Blueprint-based deployment. All services in render.yaml |

---

## 7. Database

### Engine
PostgreSQL 15+ with pgvector extension (plan: Basic-256mb on Render)

### Migration Tool
Alembic (SQLAlchemy async)

### Run Migrations
```bash
cd backend
alembic upgrade head    # Apply all pending migrations
alembic current         # Show current revision
alembic history         # Show all revisions
```

### Migration History (22 files, chronological)
| File | Change |
|---|---|
| `66ab93e4c8e1` | Initial schema — all core tables |
| `a1b2c3d4e5f6` | Unique constraint on ip_usage_tracking |
| `abc123resize` | Resize embedding vector |
| `b2c3d4e5f6a7` | Add timestamps to ip_tracking |
| `c1d2e3f4g5h6` | Add user profile fields |
| `d2e3f4g5h6i7` | Add dispatched fields to rfq_matches |
| `e1f2g3h4i5j6` | Add system_config table |
| `f1g2h3i4j5k6` | Fix system_config columns |
| `g2h3i4j5k6l7` | Final system_config schema fix |
| `h3i4j5k6l7m8` | Add invite_email to provider_memberships |
| `i4j5k6l7m8n9` | Add linked_provider_id to users |
| `j5k6l7m8n9o0` | Add document columns to quotes |
| `k6l7m8n9o0p1` | Add entity_type to users |
| `l7m8n9o0p1q2` | Add full_profile_edit_paid flag |
| `m8n9o0p1q2r3` | Add state to users |
| `n9o0p1q2r3s4` | Add provider campaign tables |
| `o0p1q2r3s4t5` | Add target_mode to campaigns |
| `p1q2r3s4t5u6` | Add account lockout fields |
| `q2r3s4t5u6v7` | Add email verification fields |
| `r3s4t5u6v7w8` | Add support ticket tables |
| `s5t6u7v8w9x0` | Add nda_credits to users (most recent) |

### Seed Data
- Provider data lives in `scripts/engineering_directory.db` (original SQLite, 6000+ firms)
- Run `scripts/migrate_sqlite_to_postgres.py` to migrate providers to PostgreSQL
- Run `backend/generate_embeddings.py` to backfill embeddings after migration
- No other seed data scripts — admin user must be created manually

### Backup
- Render PostgreSQL plan includes daily automated backups
- Manual backup: `pg_dump $DATABASE_URL > backup.sql`

---

## 8. Known Issues and Gotchas

### 🔴 Open / Unresolved
1. **NDA payments stuck in "Initiated" status** — User reported that NDA checkout payments stay in "Initiated" and never fulfill. Root cause: SignWell webhook not configured with real API key, so signing completion event never arrives. Fix: Set real `SIGNWELL_API_KEY` and configure webhook.
2. **No Celery worker deployed** — Celery task definitions exist (`backend/app/tasks/`) but no Celery worker service runs on Render. The asyncio background loop in `main.py` is the only background dispatcher. If it crashes, dispatch stops until service restarts.
3. **Render Cron Job needs Blueprint sync** — The `proreadyengineer-rfq-cron` service only activates if the Render Blueprint is synced in the dashboard. Without sync, cron never fires. The asyncio loop is the fallback.
4. **Provider embeddings not auto-backfilled** — After first migration, run `generate_embeddings.py` manually. No automatic backfill on cold start.
5. **PayPal in sandbox mode** — `PAYPAL_MODE=sandbox` in render.yaml. Real PayPal credentials not wired. Sandbox credentials needed before testing end-to-end.

### 🟡 Fixed But Fragile
1. **Subscription tier string mismatch** (commit `7b821a1`) — Query in `payments.py` used `search_tier1` but stored value is `search_tier_1`. Fixed. If you add new subscription types, ALWAYS use underscore-separated names consistently.
2. **Force Fulfill fallback** (commit `70d3ca3`) — Admin "Force Fulfill" button had silent failures when `provider_id` was missing from `extra_data`. Fixed with membership fallback. Still fragile if membership also absent.
3. **Revenue chart math** — Monthly Revenue bar chart was using a different filter than the total. Fixed. Be careful if you add new payment purposes — update ALL chart filters consistently.
4. **Provider dashboard overflow** (commit `ff905a2`) — Layout was broken with duplicate sections. Rebuilt with sub-navigation and preview sections. Don't add large blocks of content without testing scroll/overflow.
5. **Customer registration name field** (commit `79e6568`) — "Name" field wrongly marked optional. Fixed. RFQ draft save/restore via localStorage also added in same commit.
6. **SWC backslash-bang bug — recurring** (commits `5b55162`, `daa8d17`). Bash heredocs that contain `!=` or `!x` will silently insert a `\!` byte sequence into the file (`0x5C 0x21`). SWC then errors with `Expected unicode escape`. Always run a byte-level sweep `b"\\!".replace(b"\\!", b"!")` after writing TS/TSX/JSX/JS/PY via heredoc, or write through Python `Path.write_text` instead of heredoc.
7. **Alembic multiple-heads bug** (commit `cb3957e`). The migration history contains a merge migration `92a49adae23c_merge_nda_credits_and_advertisement_.py` whose `down_revision` is a tuple. Pointing a new migration at one of its already-merged parents produces two heads and breaks `alembic upgrade head` on deploy. **Before adding any new migration, run `alembic heads` (or grep for tuple-form `down_revision = (...)`) — chain off the merge commit, not its parents.**

### 🔵 Design Decisions to Know
1. **OPENAI_API_KEY points to DeepInfra, not OpenAI** — The env var is named `OPENAI_API_KEY` for SDK compatibility, but the `OPENAI_API_BASE` points to `https://api.deepinfra.com/v1/openai`. Don't get confused. Do not swap this to real OpenAI without checking model names.
2. **SignRequest → SignWell rename** — The original spec said SignRequest. We use SignWell. The webhook endpoint is still named `/webhooks/signrequest` for historical reasons. Don't rename without updating webhook registrations.
3. **No separate Celery worker** — Don't add Celery tasks expecting them to run automatically. The asyncio loop in `main.py` handles dispatch. True Celery tasks need a worker service added to render.yaml.
4. **`--legacy-peer-deps` is mandatory** — React 19 has peer dependency conflicts with shadcn components. Always `npm install --legacy-peer-deps` or builds will fail.
5. **SWC JSX parser gotchas** — Next.js SWC parser breaks on: nested functions returning JSX (lift to top-level components), inline TypeScript types with capital names in function parameters, and `Record<string, string>`. These caused multiple build failures.
6. **Dual dispatch guard** — Both the cron trigger and asyncio loop fire `cron_dispatch_rfq_batches`. There's a 14-minute interval guard in `internal.py` preventing duplicate batches. Don't remove this guard.
7. **`backend/.env` uses SQLite for local dev** — The default `.env` has `DATABASE_URL=sqlite+aiosqlite:///./proready.db`. This is intentional for local dev. The production DATABASE_URL comes from Render's database service.
8. **`engineering_directory.db` has 6000+ provider firms** — This SQLite file is the seed source. It lives in `scripts/` in the repo. Run `migrate_sqlite_to_postgres.py` to load providers into PostgreSQL.
9. **Render starter plan cold starts** — Free/Starter plan services spin down after inactivity. First request after sleep takes 30-60 seconds. For demo, ping the API first.
10. **git push needs `--force` sometimes** — The deploy/ directory is re-initialized each time for fresh pushes. Force push is expected and safe since this is a single-dev workflow.

---

## 9. Roadmap / Next Steps

### ✅ Done
- Full PostgreSQL schema (22 migrations)
- FastAPI backend with all 63 API routes wired
- JWT auth with refresh tokens, rate limiting, account lockout
- AI search pipeline (DeepInfra embeddings + LLM + pgvector + 100-point scoring)
- Provider claim/ownership flow
- RFQ lifecycle (draft → submitted → dispatch → quotes)
- Batch dispatch with asyncio background loop + Render cron
- Stripe checkout + webhook handler scaffolding
- PayPal checkout scaffolding (sandbox)
- SignWell NDA integration scaffolding
- Resend email service + HTML templates
- S3 file service + local dev fallback
- Admin backoffice (users, providers, RFQs, payments, webhooks, ads, support)
- Customer dashboard + RFQ tracking + quote viewer
- Provider dashboard + profile management + RFQ teasers + quote submission
- Advertising system (ad slots, Software Providers page, Featured Firms page)
- Provider campaign email system
- Support ticket system
- Sentry integration (optional)
- Email verification flow
- Account lockout fields
- NDA credits system
- RFQ draft save/restore (localStorage)
- Provider role gates: providers cannot submit RFQs or use customer search (commit `5dad5bb`)
- AI Help Assistant chatbot (subscriber-gated, LLM3-grounded on `docs/help/proreadyengineer_manual.md`) + public `/help` page (commits `113b709`, `daa8d17`)
- Per-button static help tooltips backed by `frontend/src/lib/help-registry.ts` and `<HelpTip />` component
- `help_chat_logs` table + admin review endpoint at `/api/v1/admin/help/logs`

### 🔨 Half-Done / Needs Real Credentials
- **Stripe payment fulfillment** — Checkout works, webhook handler exists, but needs real Stripe keys and webhook secret to test end-to-end
- **PayPal payments** — Sandbox scaffolded, needs real sandbox credentials
- **SignWell NDA signing** — Integration code exists, needs real API key and webhook configured
- **Email sending** — Resend integration complete, needs real RESEND_API_KEY and verified domain
- **S3 file storage** — Service exists with local fallback, needs real AWS credentials for production
- **Provider embedding backfill** — Script ready (`generate_embeddings.py`), needs to be run once after DB migration
- **SQLite → PostgreSQL migration** — Script ready (`scripts/migrate_sqlite_to_postgres.py`), needs to be run once against production DB

### 📋 Planned / Not Started
- Real-money Stripe testing (move from test to live keys)
- Email domain verification on Resend
- Proper Celery worker service on Render (currently using asyncio loop)
- Admin analytics refinement
- Provider tier evaluation workflow (UI exists, admin flow needs polish)
- Customer NDA download flow
- Full quote acceptance contact reveal flow
- Performance testing at scale
- Cloudflare DNS setup
- Custom domain (proreadyengineer.com)

---

## 10. AI Session Resume Guide

> Purpose: if the human operator (Bassam) returns to this project after a break, or hands the project to a different AI session, this section is the **minimum viable context** an incoming AI needs to be productive without re-asking everything.

### 10.1 What this project is, in 30 seconds
ProReadyEngineer is a B2B marketplace connecting **engineering firms (providers)** with **companies needing engineering work (customers)**. Customers post RFQs; providers pay an unlock fee (and possibly sign an NDA via SignWell) to see the full RFQ and submit a quote. Subscriptions and ads bring in additional revenue. There are exactly **two self-serve account types** (customer / provider) plus internal admin and (non-self-serve) advertiser records. The same email cannot hold both customer and provider roles.

### 10.2 Where things live (single source of truth)
- **GitHub repo (deployed branch is `main`):** `https://github.com/bmsabry/proreadyengineer-mvp`
- **Live URLs:** see Section 1.
- **Render dashboard:** all real env vars and secrets live there. Do not invent or guess them. Names and which service holds which secret are documented in the operator's local handoff notes.
- **Local working tree on operator's machine (Windows):** `G:\Other computers\My Laptop\Documents\ProReadyEngineer\Agent0_Projects\Engineering services directory\Website for Engineering Services (1)\proreadyengineer-mvp-new\` — used for editing, not for direct push. The user runs a small `.bat` to copy this into a clone for git push, OR an AI session pushes via a temp clone with a PAT-embedded remote.

### 10.3 Deploy workflow expected by the operator
1. Edit files in the working tree (Windows path above) **or** in a fresh `git clone` under `/tmp/`.
2. Commit on `main` and push. Render auto-deploys both services on push.
3. Backend startup runs `cd backend && alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT`. **A migration with multiple heads will crash this step** — see Section 8.
4. Frontend build runs `npm install --legacy-peer-deps && rm -f tsconfig.tsbuildinfo && next build`. **Stray `\!` bytes in TS/TSX will crash SWC** — see Section 8.
5. After a successful deploy, sync the same files back into the operator's local working tree so the Google-Drive-synced copy on their laptop matches `origin/main`.

### 10.4 The three LLMs (LLM1 / LLM2 / LLM3)
This is named, real architecture. Do not invent new LLMs.
- **LLM1 — Customer search / query generation.** Reads `OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_LLM_MODEL`. Note that despite the names, this is currently DeepInfra (Kimi-K2.5) — not real OpenAI. See Section 8 design decision #1.
- **LLM2 — Firm ranking.** Has its own optional key/model env vars; falls back to LLM1 if unset.
- **LLM3 — Document Collapse LLM.** Reads `DOC_LLM_API_KEY`, `DOC_LLM_API_BASE`, `DOC_LLM_MODEL`. Used by: support ticket classification, quote-document summarization, website content extraction for firm profiles, and the **AI Help Assistant chatbot**.

**Canonical config-read pattern** (see `app/services/help_service.py::_get_llm3_config` and `app/services/support_service.py`):
```python
from app.services.config_service import get_runtime_config
rt_cfg = await get_runtime_config(db)
api_key = (
    rt_cfg.get("DOC_LLM_API_KEY") or rt_cfg.get("doc_llm_api_key")
    or rt_cfg.get("OPENAI_API_KEY") or rt_cfg.get("openai_api_key")
    or getattr(settings, "DOC_LLM_API_KEY", None)
    or getattr(settings, "OPENAI_API_KEY", None)
)
```
**Always read admin-panel runtime config first, env vars second.** Admins can change LLM keys/models from the Admin → Settings page without a redeploy.

### 10.5 The AI Help Assistant — quick map
- **Source of truth:** `docs/help/proreadyengineer_manual.md`. Edit this file to change what the assistant knows about the product. Cached server-side for 5 minutes.
- **Service:** `backend/app/services/help_service.py` (subscription gate, system prompt, LLM3 call).
- **Endpoints:** `backend/app/api/endpoints/help.py` — `/help/status`, `/help/manual`, `/help/chat` (gated, 20/min, 50/day), `/admin/help/logs`.
- **Subscription gate:** Customer Search Tier 1/2 + Provider Profile/Annual unlock the chatbot. **Advertisement-only subscriptions do NOT.** Admins always have access.
- **Model:** `backend/app/models/help_chat.py` (table `help_chat_logs`).
- **Migration:** `u7v8w9x0y1z2_add_help_chat_logs.py` (chained off `92a49adae23c`).
- **Frontend:** floating widget `frontend/src/components/help/HelpChatWidget.tsx`, public manual page `frontend/src/app/help/page.tsx`, API client `frontend/src/lib/api.ts::helpApi`.
- **Per-button tooltips:** `frontend/src/lib/help-registry.ts` + `frontend/src/components/ui/HelpTip.tsx`. Drop `<HelpTip id="..." />` next to any button/label.

### 10.6 Recurring traps — read before editing
1. **Heredoc `\!` bug.** Already documented in Section 8 (gotcha #6). It has bitten this project at least three times: admin payments, help chat widget, help service. Always do a byte-level sweep after heredoc writes.
2. **Alembic multiple heads.** Already documented in Section 8 (gotcha #7). Run `alembic heads` before adding migrations.
3. **Subscription enum strings are underscore-separated.** Already documented in `DEVELOPMENT_HISTORY.md` and Section 8.
4. **Provider role gates.** `backend/app/api/deps.py::reject_provider_only` is wired into the search and RFQ endpoints. Do not remove. The frontend equivalent is `useEffect` redirects in `frontend/src/app/search/*` and the landing page form.
5. **Email-collision rule.** `auth_service.py::register_user` rejects creating a customer account on an email that already has a provider account (and vice versa). Tests rely on this — don't relax it.
6. **`--legacy-peer-deps` is non-negotiable.** Already in `render.yaml`.

### 10.7 Operator (Bassam) expectations
- Communicates from a non-engineer-but-technical perspective. Wants concise, decision-ready writeups, not lectures.
- Strongly prefers the AI **grep the codebase for named components before asking** ("LLM3", "DOC_LLM_*", "reject_provider_only", "HelpChatWidget" are all real, searchable names).
- Will sometimes paste raw Render build logs as the entire user message. Treat that as a deploy failure to debug, not as a request for general advice.
- Wants final deliverables on `origin/main` AND synced back to the local Google-Drive-synced workspace.

### 10.8 Quick health-check commands an incoming AI can run
```bash
# Confirm only one alembic head:
cd backend && alembic heads     # should print exactly one revision
# Or, without alembic installed:
python3 -c "from pathlib import Path,PurePath; import re;
revs={};downs={};
for f in Path('backend/alembic/versions').glob('*.py'):
    s=f.read_text()
    m=re.search(r'^revision(?:\s*:\s*[^=\n]+)?\s*=\s*[\'\"]([^\'\"]+)', s, re.M)
    d=re.search(r'^down_revision(?:\s*:\s*[^=\n]+)?\s*=\s*(.+)$', s, re.M)
    if m: revs[m.group(1)]=f.name;
    if m and d:
        raw=d.group(1).strip()
        if raw=='None': downs[m.group(1)]=()
        elif raw.startswith('('): downs[m.group(1)]=tuple(x.strip().strip(chr(39)+chr(34)) for x in raw.strip('()').split(',') if x.strip())
        else: downs[m.group(1)]=(raw.strip(chr(39)+chr(34)),)
parents=set(); [parents.update(v) for v in downs.values()]
print('heads:', [r for r in revs if r not in parents])"

# Confirm zero stray `\!` bytes:
python3 -c "from pathlib import Path; bad=bytes([0x5c,0x21]); print('hits:', sum(bad in p.read_bytes() for ext in ('*.ts','*.tsx','*.js','*.jsx','*.py') for p in Path('.').rglob(ext) if not any(x in p.parts for x in ('node_modules','.git','.next'))))"

# Confirm provider role gates still in place:
grep -n "reject_provider_only" backend/app/api/endpoints/rfqs.py backend/app/api/endpoints/search.py
```

### 10.9 What is NOT in this repo (intentional)
- Real secret values. Always pull from Render Dashboard.
- A Celery worker service (asyncio loop is the runtime; see Section 8).
- Provider escrow / project-fee flow (out of scope for MVP — payments between customer and provider happen off-platform).
- Native mobile clients (responsive web only).

