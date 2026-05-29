# ProReadyEngineer — Development History Brain Dump

> Not a polished changelog. This is everything the previous agent remembers about how this was built, what broke, what we tried, and what the next agent needs to know.

---

## Phase 0 — Planning

### Starting Point
The user provided a comprehensive 35-section MVP specification (v2) for a B2B Engineering Services Directory and Marketplace. The spec was extremely detailed — it specified every table, every enum value, every API route, every lifecycle state, and architectural rules.

### First Decision: Don't Start with Frontend
The spec explicitly said: DO NOT begin with frontend. The first focus is database inspection, schema design, migration planning, and API contract design.

We honored this. The execution order was:
1. Inspect existing SQLite database (`engineering_directory.db`) — 6000+ provider firms
2. Design PostgreSQL schema
3. Write API route contract (63 routes across 10 modules)
4. Build FastAPI backend
5. Build Next.js frontend
6. Wire integrations (Stripe, PayPal, SignWell, Resend, S3)
7. Deploy to Render

### Key Architectural Decisions Made Early

**AI Provider: DeepInfra instead of OpenAI**
- Spec said OpenAI. We used DeepInfra with OpenAI-compatible API.
- Why: Cost. DeepInfra is significantly cheaper for both embeddings and LLM calls.
- Important: `OPENAI_API_KEY` env var is actually a DeepInfra API key. `OPENAI_API_BASE` points to `https://api.deepinfra.com/v1/openai`.
- Embedding model: `BAAI/bge-large-en-v1.5` (better for domain-specific engineering content than OpenAI's text-embedding-3-small)
- LLM model: `moonshotai/Kimi-K2.5` (good reasoning at low cost)
- DO NOT swap to real OpenAI without updating model names and checking rate limits.

**Document Signing: SignWell instead of SignRequest**
- Spec said SignRequest. We switched to SignWell.
- Why: SignWell has better embedded iframe support and cleaner webhook API.
- The webhook endpoint is still named `/webhooks/signrequest` for backwards compatibility. Don't rename it.
- Env var is `SIGNWELL_API_KEY`.

**No Separate Celery Worker on Render**
- Spec envisioned Celery for background tasks.
- Celery task definitions exist in `backend/app/tasks/` (rfq_tasks, email_tasks, search_tasks, crawl_tasks).
- BUT: We never deployed a separate Celery worker on Render. It would cost money and the tasks are simple enough.
- Instead: asyncio background loop in `main.py` handles RFQ dispatch every 15 minutes.
- Render Cron Job (`proreadyengineer-rfq-cron`) is the primary trigger.
- Both have a 14-minute interval guard to prevent duplicate dispatches.
- WARNING: If you add Celery tasks expecting automatic execution, they won't run without a worker.

**Local Dev Uses SQLite, Production Uses PostgreSQL**
- This was intentional to make local setup trivial.
- `backend/.env` defaults to `sqlite+aiosqlite:///./proready.db`.
- Production `DATABASE_URL` is auto-set by Render from the PostgreSQL service.
- The ORM (SQLAlchemy async) works with both. Most migrations work on both, but pgvector extension obviously only works on PostgreSQL.
- For local dev, search works without embeddings (falls back gracefully).

---

## Phase 1 — Database and Backend

### SQLite Inspection
We inspected `engineering_directory.db` before writing any schema. The source database had:
- `providers` table with ~6000+ rows
- Fields included: name, website, phone, address, city, state, postal_code, primary_specialty, business_description, tier (A/B/C/D/E), capabilities, specialties, software_tools, email_addresses, certifications, notable_clients, is_engineering_service, is_mechanical_focus, various boolean flags
- Some fields were comma-separated strings that needed to be converted to PostgreSQL TEXT[] arrays
- Some fields had mixed quality — many null values, inconsistent formatting

### Schema Design Decisions
- Used JSONB for flexible fields (scoring_inputs, metadata, extra_data)
- Used TEXT[] for plain string lists (software_tools, certifications, specialties)
- Used proper enum types for all lifecycle states (rfq_status, quote_status, nda_status, etc.)
- Added `vector(1536)` column to providers for embeddings (later resized — see migration `abc123resize`)
- All new fields added as nullable to preserve migration safety

### Initial Migration Issues
The initial migration (`66ab93e4c8e1`) was huge — all tables at once. This caused problems:
- Had to fix system_config table schema multiple times (3 migrations: e1f2g3h4i5j6, f1g2h3i4j5k6, g2h3i4j5k6l7)
- The embedding vector was sized incorrectly initially, required a resize migration (`abc123resize`)
- ip_usage_tracking uniqueness constraint was missing and needed its own migration (`a1b2c3d4e5f6`)

### Backend Implementation Order
1. `app/core/config.py` — Pydantic Settings (all env vars in one place)
2. `app/db/session.py` — async SQLAlchemy engine
3. `app/models/` — all ORM models
4. `app/services/auth_service.py` — JWT + bcrypt
5. `app/api/endpoints/auth.py` — auth routes
6. Iteratively added: search, providers, rfqs, quotes, payments, ads, admin, campaigns, support

### Rate Limiting
- Used `slowapi` (Starlette-compatible rate limiter)
- `limiter` instance in `app/core/rate_limiter.py`
- Applied to auth endpoints: login (5/min), password reset (3/hour), refresh (10/min)
- CORS restricted via `EXTRA_CORS_ORIGINS` env var

### Sentry Integration
- Added Sentry SDK gated on `SENTRY_DSN` env var
- If env var not set, Sentry does nothing — safe for local dev
- `traces_sample_rate=0.1` — 10% of requests traced

---

## Phase 2 — Frontend

### Stack Choices
- Next.js 15 with App Router (not Pages Router)
- React 19 (latest at time of build)
- TypeScript throughout
- Tailwind CSS + shadcn/ui components
- NO external state management library (just React context + useState)

### SWC Parser Problems (Major Time Sink)
Next.js uses SWC (Rust-based compiler) instead of Babel. SWC's JSX parser is stricter than Babel's and caused multiple cryptic build failures with messages like "Unexpected token div. Expected jsx identifier".

Root causes discovered:
1. **Nested functions returning JSX inside React components** — SWC doesn't handle these well. Solution: Lift to top-level components.
2. **Inline TypeScript type annotations with capital names in function parameters** — `function Foo({ bar }: { bar: MyType[] }
2. **Inline TypeScript type annotations with capital names in function parameters** — `function Foo({ bar }: { bar: MyType[] })` breaks SWC. Solution: Use named interfaces.
3. **`Record<string, string>` with capital R** — Can confuse SWC JSX parser in certain contexts.
4. **Unclosed JSX tags and braces** — SWC error messages are unhelpful. Use systematic grep to find unclosed tags.

Strategy that worked:
- Run `npm run build` to see SWC error
- Identify the file from error message
- Scan for nested function components and lift them out
- Scan for inline type annotations and replace with interfaces
- Rebuild

### React 19 Peer Dependency Issue
- shadcn/ui and some other packages have peer deps on React 18
- React 19 breaks `npm install` without `--legacy-peer-deps`
- This flag is hardcoded into the Render build command in render.yaml
- NEVER remove it or builds will fail
- `tsconfig.tsbuildinfo` also needed to be deleted on fresh builds (hence `rm -f tsconfig.tsbuildinfo` in build command)

### Auth Context
- `AuthContext.tsx` provides global auth state
- Login sets access token (stored in memory / httpOnly cookie depending on implementation)
- All API calls go through `useApi.ts` hook which injects auth header
- Token refresh is handled automatically when 401 is received

### ConfigContext
- `ConfigContext.tsx` provides admin-editable system config (pricing, feature flags, etc.)
- Config is stored in `system_config` table in DB
- Fetched on app load from `/api/v1/admin/config` (or public config endpoint)
- Used for dynamic pricing display without code deploys

### Frontend Pages Architecture
- App Router with nested layouts
- `/customer/layout.tsx` — customer portal layout with sidebar nav + RFQ draft resume banner
- `/provider/layout.tsx` — provider portal layout with sidebar nav + tooltips on nav items
- `/admin/layout.tsx` — admin backoffice layout with `DashboardNav` component
- Each portal has its own auth guard (redirects to login if not authenticated)

---

## Phase 3 — Bugs Fixed

### Bug: Subscription Tier String Mismatch (commit `7b821a1`)
**Problem:** Customer dashboard showed 'Free' even after successful payment and Force Fulfill.
**Root cause:** Query in `payments.py` used `'search_tier1'` but stored enum value is `'search_tier_1'`.
**Fix:** Corrected string literals at lines 80, 298, 371 in payments.py.
**Lesson:** Use consistent underscore-separated names for ALL subscription type strings. Check every file.

### Bug: Force Fulfill Button Silent Failure (commit `70d3ca3`)
**Problem:** Admin "Force Fulfill" button created no subscription, failed silently.
**Root cause:** Older bug saved payments without `provider_id` in `extra_data`. Fulfillment checked and exited silently.
**Fix:** Added fallback — if `provider_id` missing in `extra_data`, look up `ProviderMembership`.
**Lesson:** Never exit silently in payment fulfillment. Log loudly. Add fallback lookups.

### Bug: Monthly Revenue Chart Math Mismatch
**Problem:** Admin dashboard bar chart total didn't match sum of individual cards.
**Root cause:** Bar chart used different payment purpose filter than the total cards.
**Fix:** Updated bar chart to use same filter. Then also removed Revenue by Purpose donut chart (redundant). Centered bar chart.

### Bug: Provider Dashboard Layout Overflow (commit `ff905a2`)
**Problem:** Provider dashboard had content overflow, duplicate sections, broken filters.
**Fix:** Complete rebuild with stacked rows, sub-navigation, max 3 items per preview section, dedicated RFQ/quote pages, closed RFQ warning modal, filter tabs.

### Bug: Customer Registration Name Field + RFQ Draft (commit `79e6568`)
**Problem:** "Name" field wrongly marked optional. Placeholder didn't change to "Firm name" for Company type.
**Fix:** Fixed field validation, dynamic placeholder. Also added RFQ draft save/restore via localStorage with "Resume RFQ" banner.

### Bug: NDA Payments Stuck in "Initiated" (OPEN)
**Problem:** NDA checkout payments never fulfill — stuck at Initiated status permanently.
**Root cause:** SignWell API key not configured. Webhook never arrives. Fulfillment never fires.
**Fix needed:** Real `SIGNWELL_API_KEY` + SignWell webhook → `/api/v1/webhooks/signrequest`.

### Bug: Nav Tooltips Missing
**Problem:** Hovering nav buttons only showed URL at browser bottom, no descriptive tooltip.
**Fix (commit `f279665`):** Added `tooltip` to navItems, wrapped Links in `relative group` div, added `span` with `title` attribute for both `customer/layout.tsx` and `provider/layout.tsx`.

### Bug: Provider Upgrade Page Access Check
**Problem:** Provider portal upgrade page used wrong field to check subscription status.
**Fix:** Changed check to rely on `User.linked_provider_id` and `ProviderMembership` for access control.
**Pricing confirmed:** $50/RFQ unlock, $500/full profile edit unlock, $10/month subscription.

---

## Phase 4 — Deployment History

### Git Architecture
The project directory lives inside Agent Zero framework at `/a0/usr/projects/website_for_engineering_directory/`. Agent Zero's git points to `github.com/agent0ai/agent-zero` — unrelated.

ProReadyEngineer uses a `deploy/` subdirectory pattern:
- Dev code: `backend/` and `frontend/`
- Sync to: `deploy/backend/` and `deploy/frontend/` using Python `shutil.copytree`
- Push to: `github.com/griggril000/proreadyengineer-mvp` (force push)

**Why:** Can't create a separate git inside an existing git repo cleanly without submodule complexity. The deploy/ pattern sidesteps this.

**Sync script pattern** (run before every push):
```python
shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', 'proready.db', 'uploads/'))
```

**Push pattern:**
```bash
cd deploy/
git add -A
git commit -m "message"
git push origin main --force  # force because deploy/ git is re-initialized each session
```

### Render Deployment Issues
1. **Blueprint sync required for cron** — `proreadyengineer-rfq-cron` service needs Render Blueprint sync. Without it, cron never activates. Go to Render Dashboard → Blueprints → Sync.
2. **Cold start latency** — Starter plan services spin down. First request after sleep = 30-60s delay.
3. **Build failures due to `tsconfig.tsbuildinfo`** — Stale build cache causes mysterious Next.js build failures. Solution: `rm -f tsconfig.tsbuildinfo` in build command (already in render.yaml).
4. **`--legacy-peer-deps` mandatory** — React 19 peer dep conflicts. Already in render.yaml.
5. **`alembic upgrade head` in start command** — Migrations run on every service start. This is intentional and safe because Alembic is idempotent.

### GitHub PAT Issues
- GitHub Personal Access Tokens must start with `ghp_`
- Token expires — if push fails with 401, create new token at GitHub → Settings → Developer Settings → Personal Access Tokens
- Token scope needed: `repo` (all repo permissions) or fine-grained with contents:write
- Username: `griggril000`
- Repo: `proreadyengineer-mvp`

---

## Phase 5 — Additional Features Added

### Provider Campaign System
- Added beyond original spec (migration `n9o0p1q2r3s4` + `o0p1q2r3s4t5`)
- Allows admins to send targeted email campaigns to providers
- `backend/app/models/campaign.py`, `backend/app/services/campaign_service.py`
- Frontend: `frontend/src/app/admin/campaigns/page.tsx`

### Support Ticket System
- Added beyond original spec (migration `r3s4t5u6v7w8`)
- Customers and providers can submit support tickets
- Admin can view and respond
- `backend/app/models/support.py`, `backend/app/services/support_service.py`
- Frontend: `frontend/src/app/admin/support/` and `frontend/src/app/contact/`

### Email Verification
- Added (migration `q2r3s4t5u6v7`)
- `email_verified`, `email_verification_token`, `email_verification_sent_at` on User
- Email template: `backend/app/templates/emails/email_verification.html`

### Account Lockout
- Added (migration `p1q2r3s4t5u6`)
- `failed_login_attempts`, `locked_until`, `last_failed_login_at` on User
- Threshold configurable via SystemConfig

### NDA Credits
- Added (migration `s5t6u7v8w9x0` — most recent, Apr 8 2026)
- `nda_credits` field on User model
- Allows pre-purchased NDA credits to skip per-RFQ NDA payment

### System Config
- Admin-editable settings stored in DB (migrations e, f, g for system_config)
- Frontend: `frontend/src/app/admin/settings/page.tsx`
- `ConfigContext` provides settings app-wide without code deploys

### RFQ Draft Save/Restore
- Added in commit `79e6568`
- RFQ form data saved to `localStorage` with key `RFQ_DRAFT_KEY`
- Restored on mount (only project fields)
- Draft cleared on successful submission
- "Resume RFQ" banner shown in `customer/layout.tsx` when draft exists

---

## Phase 6 — May 2026 batch (provider gates, AI Help Assistant, recurring SWC + Alembic traps)

### Provider role gates (commit `5dad5bb`)
The product had blurred role boundaries: providers could see the customer search box on the landing page and the customer dashboard's RFQ-submission form. Both were filtered out at the navigation level but reachable by direct URL. Bassam wanted a hard ban with both a UI redirect and a server-side reject so that pen-testing a provider account doesn't yield customer-only flows.

**Backend** (`app/api/deps.py::reject_provider_only`): a small dependency that 403s when the only role on the user is `provider`. Wired into:
- `POST /api/v1/rfqs` (RFQ creation)
- `POST /api/v1/search/query` (search)
- `POST /api/v1/search/upload/initiate` (doc-driven search)

**Frontend:** `useEffect` redirects on `app/search/page.tsx`, `app/search/upload/page.tsx`, and the landing-page search form in `app/page.tsx`. Providers landing on these pages are bounced to `/provider/dashboard`.

**Email-collision** rule was already in `auth_service.py::register_user` (lines 146-162) — it rejects creating a customer on an email that already holds provider, and vice versa. Confirmed working; no change required.

### AI Help Assistant + manual + per-button tooltips (commit `113b709`)
Bassam asked for "comprehensive help on all buttons as well as a detected help chatbot that uses LLM3 to educate them about anything related to the website." The plan was approved with two constraints: subscriber-only access, and a clear paywall message that converts non-subscribers.

What we built:
- **`docs/help/proreadyengineer_manual.md`** — single source of truth. The chatbot is grounded on it; `/help` renders it. Edit this file to change what the assistant knows.
- **`backend/app/services/help_service.py`** — uses LLM3 (`DOC_LLM_*`), runtime-config-first read, 5-min manual cache, role-aware system prompt with explicit guardrails (no legal/medical/engineering advice; never act on the user's behalf; never disclose other users' data).
- **`backend/app/api/endpoints/help.py`** — `/help/status`, `/help/manual`, `/help/chat` (subscription-gated, 20/min slowapi, 50/day non-admin cap), `/admin/help/logs`.
- **`backend/app/models/help_chat.py` + migration `u7v8w9x0y1z2`** — `help_chat_logs` table.
- **Subscription gate:** Customer Search Tier 1/2 + Provider Profile/Annual unlock the chatbot. Advertisement-only subscribers do NOT (per product direction). Admins always pass.
- **Frontend:** floating `<HelpChatWidget />` (paywall view for non-subscribers with subscribe CTA + "Included with your subscription" badge for paid users), public `/help` page (markdown render with paywall/active banner), `helpApi.{status,manual,chat}` in `lib/api.ts`.
- **Per-button tooltips:** `lib/help-registry.ts` + `<HelpTip id="..." />`. Wired on landing search button, RFQ submission form (description, tollgate, NDA). Drop in elsewhere with one line.

### Build break #1 — recurring SWC backslash-bang (commits `5b55162`, `daa8d17`)
Render's SWC (Next.js compiler) errored with `Expected unicode escape` on the new TS files. Root cause: bash heredocs used to write the source code escaped every `!` as `\!` (byte sequence `0x5C 0x21`). SWC parses `\` as the start of a unicode escape and dies on the `!` that follows.

This is the **third** time this exact bug has hit the project. We have a stable fix recipe now:
```python
# Sweep all source files in the repo (run before commit if any were heredoc-written):
from pathlib import Path
bad = bytes([0x5c, 0x21])
for ext in ("*.ts","*.tsx","*.js","*.jsx","*.py","*.md"):
    for p in Path(".").rglob(ext):
        if any(x in p.parts for x in ("node_modules",".git",".next","dist","build")): continue
        d = p.read_bytes()
        if bad in d:
            p.write_bytes(d.replace(bad, bytes([0x21])))
```
Better long-term: avoid heredocs for source — use Python `Path.write_text()` directly when an editor tool isn't available.

### Build break #2 — multiple Alembic heads (commit `cb3957e`)
Backend startup ran `alembic upgrade head` and bailed with `Multiple head revisions are present`. The new migration `u7v8w9x0y1z2_add_help_chat_logs.py` had `down_revision = 't6u7v8w9x0y1'`, but `t6u7v8w9x0y1` had **already been merged** into `92a49adae23c_merge_nda_credits_and_advertisement_.py` (whose down_revision is the tuple `('s5t6u7v8w9x0', 't6u7v8w9x0y1')`). Pointing the new migration at one of the merged parents created a second head.

Fix: `down_revision = '92a49adae23c'` so the help_chat migration is a single linear successor of the merge.

**Lesson saved as gotcha #10:** before adding any new migration, run `alembic heads` (or grep for tuple-form `down_revision`) and chain off the **merge** commit, not its parents. A naive `^revision = ` regex also misses typed migrations like `revision: str = '...'` — when programmatically scanning, match `^(revision|down_revision)(\s*:\s*[^=]+)?\s*=\s*`.

### What landed where
| Concern | File(s) | Commit |
|---|---|---|
| Provider role gates | `app/api/deps.py`, `app/api/endpoints/rfqs.py`, `app/api/endpoints/search.py`, `frontend/src/app/{page,search/page,search/upload/page}.tsx` | `5dad5bb` |
| Help manual | `docs/help/proreadyengineer_manual.md` | `113b709` |
| Help backend | `app/models/help_chat.py`, `app/services/help_service.py`, `app/api/endpoints/help.py`, `app/db/base.py`, `app/api/endpoints/__init__.py`, `main.py` | `113b709` |
| Help migration | `alembic/versions/u7v8w9x0y1z2_add_help_chat_logs.py` | `113b709` (parent fix `cb3957e`) |
| Help frontend | `frontend/src/components/help/HelpChatWidget.tsx`, `frontend/src/components/ui/HelpTip.tsx`, `frontend/src/lib/help-registry.ts`, `frontend/src/lib/api.ts`, `frontend/src/app/help/page.tsx`, `frontend/src/app/layout.tsx` | `113b709` |
| Tooltip wiring | `frontend/src/app/page.tsx`, `frontend/src/app/customer/rfq/new/page.tsx` | `113b709` |
| SWC fixes | `frontend/src/lib/api.ts`, `frontend/src/components/ui/HelpTip.tsx`, `frontend/src/components/help/HelpChatWidget.tsx`, `frontend/src/app/help/page.tsx` | `daa8d17` |
| Alembic head fix | `alembic/versions/u7v8w9x0y1z2_add_help_chat_logs.py` | `cb3957e` |

---

## Version Pins (Do Not Upgrade Without Reason)

| Package | Version | Why Pinned |
|---|---|---|
| `fastapi` | 0.115.0 | Tested stable version |
| `sqlalchemy[asyncio]` | 2.0.36 | Async engine API stable |
| `pydantic` | 2.10.0 | v2 API used throughout |
| `next` | 15.2.4 | App Router stable |
| `react` | ^19.0.0 | Required for Next.js 15 features |
| `alembic` | 1.14.0 | Migration tool stable |
| `pgvector` | 0.3.6 | Matches DB extension version |

---

## User Preferences and Constraints

1. **No unnecessary speculative features** — Build only what's in the spec or explicitly requested.
2. **Reliability over cleverness** — Explicit status modeling, audit trails, replay-safe webhooks.
3. **Don't start frontend until backend is solid** — Original spec constraint, honored.
4. **Keep costs low** — Why DeepInfra instead of OpenAI. Why no separate Celery worker.
5. **Deploy to Render** — Not AWS, not GCP. Render for everything.
6. **GitHub for version control** — griggril000/proreadyengineer-mvp, public repo.
7. **Provider pricing is intentional** — $10/month subscription, $50/RFQ unlock, $500/full profile edit. Don't change without user approval.
8. **SignWell not SignRequest** — User made this call. The webhook is named /webhooks/signrequest for compatibility.
9. **RESEND_API_KEY is available** (from agent secrets injection).
10. **Agent works within Agent Zero framework** — The project lives at `/a0/usr/projects/website_for_engineering_directory/`. The deploy/ subdirectory is the git-tracked portion.

---

## May 2026 — Stabilization, security, and NDA consolidation

A full audit (`CODE_AUDIT_2026-05-28.md`) was run and acted on:

- **RFQ dispatch:** fixed the trap where NDA-required RFQs stranded in
  `awaiting_customer_signature` and never dispatched. `submit_rfq` is now tolerant of
  pre-dispatch states and **concurrency-safe** (atomic claim) so duplicate triggers
  can't double-dispatch.
- **NDA consolidated to ONE model** — mutual, provider-first "sign to read" (see
  ARCHITECTURE.md §6). The legacy customer-iframe-first path (endpoints + service
  functions) was removed.
- **Security:** production refuses to boot on the default `SECRET_KEY`; PayPal webhook
  now verifies signatures (fail-closed); CORS scoped to project origins; a latent
  naive/aware datetime bug in refresh-token/lockout checks was hardened.
- **Correctness:** subscriber RFQ unlocks now use the recognized `unlocked` status (they
  were granted but never honored); free-tier search limit corrected to 10 (matched the
  admin UI / advertised value); an N+1 in the customer RFQ list was batched.
- **Hygiene:** 34 broad `except Exception: pass` blocks and 6 fire-and-forget frontend
  `.catch(() => {})` now log instead of swallowing; stale fee comments corrected.
- **Safety net:** added a GitHub Actions CI that runs the backend unit suite on every
  push/PR (none existed before); added regression tests for the dispatch trap, the
  mutual-NDA webhook, auth, payments, and search quota.
