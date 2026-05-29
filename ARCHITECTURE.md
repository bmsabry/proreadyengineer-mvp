# ProReadyEngineer — Architecture & Flows (Current)

**Last updated:** 2026-05-29. This document reflects the code as it actually runs today.
It supersedes the older status claims in `HANDOFF.md` / `DEVELOPMENT_HISTORY.md` where
they disagree. When you change a flow, update this file in the same commit.

---

## 1. What it is

A B2B marketplace: **customers** post RFQs (requests for quote); **providers**
(engineering firms) are matched by AI, pay to unlock an RFQ, and submit quotes.
Revenue: per-RFQ provider unlock fees, an optional customer NDA fee, provider
annual subscriptions, customer search subscriptions, and advertising.

## 2. Stack & services

- **Backend:** FastAPI (Python 3.11), SQLAlchemy async, Alembic, slowapi.
- **Frontend:** Next.js 15 (App Router), React 19, TypeScript, Tailwind + shadcn/ui.
- **DB:** PostgreSQL 15 + pgvector (Render). SQLite only for tests.
- **Hosting:** Render, defined in `render.yaml`. Production services:
  `proreadyengineer-api`, `proreadyengineer-web`, `proreadyengineer-db`, and the
  `proreadyengineer-rfq-cron` cron job.
- **External:** DeepInfra (AI — via the `OPENAI_*` env vars), Stripe, PayPal
  (sandbox, **not currently configured** — only mode/currency set), SignWell (NDA —
  the env var is named `SIGNREQUEST_API_KEY` for historical reasons), Resend (email),
  AWS S3.
- **Repo / deploy:** `github.com/bmsabry/proreadyengineer-mvp`, branch `main`. Push to
  `main` → Render auto-deploys api + web. (No `deploy/` subdirectory; that workflow is
  retired.)

## 3. Money model (source of truth: the `amount=` values, in cents)

| Charge | Who pays | Amount | When |
|---|---|---|---|
| RFQ unlock | Provider | **$20** (`amount=2000`) | To read any RFQ they receive. Waived for active **annual** subscribers. |
| NDA handling fee | Customer | **$10** (`amount=1000`) | When the customer marks an RFQ "NDA required". |
| Provider annual subscription | Provider | **$1,000/yr** (`PROVIDER_ANNUAL_SUBSCRIPTION_PRICE=100000`) | Grants free RFQ unlocks. |
| Customer search subscription | Customer | tier_1 / tier_2 | Raises the monthly search quota from 10 to 100. |

Search quota: **Free = 10 searches/month**, paid tiers = 100 (`FREE_SEARCH_LIMIT` /
`PAID_SEARCH_LIMIT` in `search_service.py`). Counter resets monthly.

## 4. RFQ lifecycle (`RfqStatus`)

`draft → submitted → (awaiting_nda_payment → awaiting_customer_signature) →
open_for_dispatch → dispatching → open_for_unlock → quote_limit_reached /
customer_selected_provider / closed_no_selection / cancelled`

The `awaiting_*` NDA states are transitional only and **never block dispatch** (see §6).

## 5. Dispatch (provider matching + teaser emails)

- Triggered when an RFQ is **submitted** (and, for NDA RFQs, after the customer's $10
  fee is recorded). `submit_rfq` runs the AI search, stores ranked `RFQMatch` rows,
  sets the RFQ `open_for_dispatch`, and sends teaser emails in batches.
- **Concurrency-safe:** `submit_rfq` claims the RFQ with a single conditional
  `UPDATE ... WHERE status IN (pre-dispatch states)`. Only the winning caller searches
  and dispatches; concurrent triggers no-op. This prevents duplicate matches/emails.
- **Batching:** `RFQ_DISPATCH_BATCH_SIZE=5` providers per batch, min interval
  `RFQ_DISPATCH_BATCH_INTERVAL_HOURS` (with a 15-min floor guard). `RFQ_MAX_QUOTES=5`.
- **Schedulers:** the `proreadyengineer-rfq-cron` Render job is the primary trigger;
  an in-process asyncio loop in `main.py` is the backup. Both share the interval guard.
  (No Celery worker runs — `app/tasks/` Celery files are not executed by a worker.)

## 6. NDA flow — "sign to read" (mutual, provider-first)

When a customer marks an RFQ **NDA required**:

1. Customer pays the **$10** NDA fee (always, when NDA is required). The RFQ then
   **dispatches normally** — the NDA does not hold up dispatch.
2. A provider receives the teaser and **unlocks** ($20, or free for annual subscribers).
3. To **read** the RFQ, the provider clicks **Sign NDA**. The backend creates **one
   mutual NDA document** in SignWell with both the provider and the customer as
   signers (`add_provider_to_nda`). The provider signs (embedded URL); the customer is
   emailed to countersign. There is **no** "customer must sign first" precondition.
4. The SignWell webhook records each signer separately (matched by email) and marks the
   NDA `fully_signed` only once **both** have signed.
5. Once fully signed, the provider sees the **full project description + files** and can
   submit a quote. Until then, only a redacted preview is shown.

**Notifications are part of the NDA workflow (not optional).** At each step the
waiting party MUST be told there is an action for them:

- Provider clicks **Sign NDA** → SignWell emails the **provider** their signing link
  (signer 1). The document uses email-based signing with `apply_signing_order: true`
  — do NOT use document-level `embedded_signing`, which suppresses ALL invitation
  emails (that bug left the customer un-notified).
- Provider signs → SignWell automatically emails the **customer** (signer 2) to
  countersign, AND the customer's portal shows an **"Action required: NDA awaiting
  your signature"** banner (`/customer/my-rfqs` returns
  `nda_awaiting_customer_signature` = provider signed but customer hasn't).
- Both signed → the provider's RFQ view unlocks (full description + files + bid).

Any future change to the NDA flow must preserve both channels (email + in-app/portal)
for whichever party is being waited on.

There is exactly **one** NDA model. The older customer-iframe-first path (`/nda/initiate`,
`/nda/confirm-signed`, `create_customer_nda`, `get_customer_signing_url`, etc.) has been
removed.

## 7. Unlock & access gating

- Access is granted by an `RFQUnlock` row with `unlock_status == "unlocked"`. **Both**
  paid unlocks and annual-subscriber free unlocks write this status (subscription
  unlocks are distinguishable by having **no** `PaymentAttempt`).
- For NDA RFQs, the full description + files are additionally gated on the mutual NDA
  being `fully_signed` (see §6).

## 8. Payments

- Stripe Checkout for one-time fees + subscriptions. Webhooks at
  `/api/v1/webhooks/stripe`: **signature-verified** (`construct_event`), de-duplicated
  via `WebhookEvent`, and fulfillment is **idempotent** (deterministic idempotency keys
  + "already COMPLETED" guards).
- PayPal webhook at `/api/v1/webhooks/paypal`: **signature-verified** against PayPal's
  verify-webhook-signature API and **fail-closed in production**. PayPal is not
  currently configured (no client id/secret/webhook id), so it is effectively unused.
- SignWell (NDA) webhook at `/api/v1/webhooks/signrequest` (name kept for historical
  registration compatibility — do not rename).

## 9. Auth & security

- JWT (HS256) access + refresh tokens; bcrypt (cost 12); account lockout; slowapi rate
  limiting (the `@limiter.limit` decorator must be the **outer** decorator).
- `SECRET_KEY` is auto-generated by Render (`generateValue: true`); the app **refuses to
  boot in production** if it is left at the insecure default.
- CORS is scoped to the project's own origins (not any `*.onrender.com`).
- Known hardening backlog: provider/customer auth tokens are stored in `localStorage`
  (XSS exposure) — moving to httpOnly cookies is a tracked follow-up.

## 10. Testing & CI

- `backend/tests/unit/` runs on every push/PR via `.github/workflows/ci.yml`
  (SQLite-backed; needs no DB service). Green suite covers: NDA dispatch
  (incl. the stuck-RFQ regression + mutual-NDA webhook), auth (hashing, JWT, password
  policy, datetime safety), payment idempotency keys, and search-quota constants.
- Some legacy suites (`test_payment_service`, `test_file_service`, `test_search_service`,
  `test_rfq_service`, `test_auth_service`) are **quarantined** (skipped) — they were
  written against a removed API and are pending a rewrite. A red CI run = a real
  regression.

## 11. Known constraints / backlog

- PayPal not configured (intentional; Stripe is the live processor).
- httpOnly-cookie auth migration (replace localStorage) — tracked.
- Rewrite the quarantined legacy test suites against the current API.
- Live end-to-end verification of SignWell signing, Resend domain, and S3 with real
  credentials is required to certify those flows "operational" (code review alone
  cannot).

See `CODE_AUDIT_2026-05-28.md` for the full findings register.

## 12. Gotcha: SignWell template ID

`SIGNWELL_TEMPLATE_ID` (Admin → Settings → Document Signing; stored in `system_config`)
**must be the template's API UUID** (e.g. `162095ae-2e32-4afd-b170-fb5753d8e923`),
**not** the share-link slug from the SignWell `https://www.signwell.com/new_doc/<slug>/`
URL. The slug is rejected by the API with `404 "Couldn't find the template"`, which
silently breaks the entire NDA flow. Get the UUID from `GET /api/v1/document_templates`
or the template's API settings in SignWell. (This was the real cause of NDA failures in
May 2026 — the config held the `new_doc` slug.)
