# ProReadyEngineer / ProMechDirectory — Canonical System Specification

> **This is the single source of truth for how this application works.**
> Read it before changing anything. If code and this document disagree, that is a
> bug in one of them — reconcile it, don't guess. When you change a behaviour or flow,
> **update this document in the same commit.** Where this file conflicts with
> `HANDOFF.md`, `DEVELOPMENT_HISTORY.md`, `api_contract_v1.md`, or older notes, **this
> file wins.**
>
> Last verified against the code on **2026-05-29** (branch `main`). Section §20 lists
> known inconsistencies between the live behaviour and stale constants/comments — read
> it before trusting any number you find inline in the code.

---

## 0. How to work in this repo (read first)

1. **Read this file, then verify against the code.** Numbers and flows here were read
   out of the running code on the date above, but code changes — confirm the specific
   lines before you rely on them for anything money-, legal-, or signature-related.
2. **Do not break the invariants in §19.** They encode business rules the owner has had
   to re-explain repeatedly. They are not stylistic preferences.
3. **One source of truth per concept.** This project has been burned by duplicated /
   half-migrated logic. Don't add a second NDA model, a second dispatch trigger, or a
   parallel "notifications" mechanism. Extend the existing one.
4. **Deploy flow:** push to `main` on `github.com/bmsabry/proreadyengineer-mvp` → Render
   auto-deploys the `proreadyengineer-api` and `proreadyengineer-web` services. There is
   no separate staging. CI (`.github/workflows/ci.yml`) runs the backend unit tests on
   every push/PR; a red run is a real regression.
5. **Secrets** live in the Render dashboard (write-only) and in `system_config` (DB,
   editable via Admin → Settings). They are NOT in the repo. See §17.

---

## 1. What the product is

A B2B engineering marketplace with four personas:

- **Customer** — posts an RFQ (request for quote) describing an engineering project,
  optionally requires an NDA, and receives quotes from matched providers.
- **Provider** — an engineering firm. Gets matched to RFQs by AI, pays to unlock and
  read an RFQ, optionally signs an NDA, and submits a quote.
- **Advertiser** — pays for featured-firm / software-provider listings.
- **Admin** — operates the platform (settings, users, providers, RFQs, payments,
  webhooks, campaigns, ads, support, debugging).

A single user row can hold multiple roles (the `users.roles` column is a text array:
`customer`, `provider`, `advertiser`, `admin`).

**Revenue:** provider per-RFQ unlock fees, an optional customer NDA fee, provider annual
subscriptions, customer search subscriptions, and advertising. See §3.

---

## 2. Stack & hosting

- **Backend:** FastAPI (Python 3.11), SQLAlchemy **async**, Alembic, slowapi rate limiting.
- **Frontend:** Next.js 15 (App Router), React 19, TypeScript, Tailwind + shadcn-style UI,
  `sonner` toasts, axios API client.
- **DB:** PostgreSQL 15 + **pgvector** (provider embeddings). SQLite is used only for the
  unit-test suite.
- **Hosting:** Render, defined in `render.yaml`. Services: `proreadyengineer-api`
  (backend), `proreadyengineer-web` (frontend), `proreadyengineer-redis`,
  `proreadyengineer-db`, and the `proreadyengineer-rfq-cron` cron job.
- **External services:** DeepInfra (AI, via the `OPENAI_*` settings), Stripe (live payment
  processor), PayPal (sandbox, **not configured** — effectively unused), SignWell (NDA
  e-signature — the API-key env var is named `SIGNREQUEST_API_KEY`/`SIGNWELL_API_KEY` for
  historical reasons), Resend (email), AWS S3 (file storage).

Brand naming is mixed in the code ("ProReadyEngineer", "ProMechDirectory",
`@promechdirectory.com` email). They refer to the same product.

---

## 3. Money model

**The authoritative amount is the `amount=` value (in cents) at the Stripe checkout call
site.** Some config constants and product-name strings are stale — see §20. Live values:

| Charge | Who pays | Live amount | When / rule | Code |
|---|---|---|---|---|
| **RFQ unlock** | Provider | **$50** (`amount=settings.RFQ_UNLOCK_PRICE`, =5000) | To read ANY RFQ they were matched to. **Free** for providers with an active `provider_annual` subscription. | `rfqs.py:987` |
| **NDA handling fee** | Customer | **$10** (`amount=1000`) | Charged when the customer marks an RFQ "NDA required" — UNLESS the customer has an active search subscription and free NDA credits left this month (5/month, `NDA_FREE_CREDITS_PER_MONTH`), in which case it's waived and a credit consumed. Metered on `users.monthly_nda_credits_used` / `nda_credits_reset_at`. | `rfqs.py` (nda_checkout) |
| **Provider annual subscription** | Provider | **$1,000/yr** (`PROVIDER_ANNUAL_SUBSCRIPTION_PRICE=100000`) | Grants unlimited free RFQ unlocks while active. | `config.py`, `payments.py` |
| **Customer search subscription** | Customer | **$50/month or $500/year** (`search_tier_1`; `SEARCH_TIER_1_PRICE=5000`, `SEARCH_ANNUAL_PRICE=50000`) | Raises monthly search quota 5 → 100 AND grants **5 free NDA-required RFQs/month** (`NDA_FREE_CREDITS_PER_MONTH=5`). Monthly vs annual differ only in price + granted period (30 vs 365 days) via metadata `billing_interval`; both are `search_tier_1` so all gates work unchanged. (Tier 2 retired — no longer sold.) | `payments.py` |
| **Provider full-profile-edit unlock** | Provider | one-time | Unlocks full profile editing (or comes free with annual sub). | `payment_service.py` |
| **Advertisement** | Advertiser | subscription | Featured-firm / software-provider listings. | `ads.py`, `payment_service.py` |

**Search quota:** an account is REQUIRED to search (anonymous returns `registration_required`; the `/search/query` endpoint also hard-rejects unauthenticated callers with 401). Free registered = **5** searches/month, paid = **100** (`FREE_SEARCH_LIMIT=5`,
`PAID_SEARCH_LIMIT=100` in `search_service.py`). Counter resets monthly. ⚠️ The
`config.py` constant `REGISTERED_SEARCH_LIMIT_PER_MONTH=5` is **NOT used** by the live
search path — do not "fix" code to match it (§20). (The RFQ unlock fee now correctly
reads `RFQ_UNLOCK_PRICE=5000` → $50.)

---

## 4. Data model (key tables)

UUIDs unless noted. Providers use integer ids.

- **User** (`users`) — `id`, `email`, `roles` (text[]: customer/provider/advertiser/admin),
  `first_name`, `last_name`, `full_name`, `business_name`, `state`, **`phone`** (optional;
  added 2026-05-30, migration `d4a7e2b91c08`), `entity_type`, auth fields, `created_at`.
  **Customer registration requires name + company (`business_name`) + state + email** (phone
  optional); enforced both client-side (register form) and server-side (the `/auth/register`
  endpoint returns 422 for a non-provider sign-up missing any of name/company/state). Provider
  sign-ups use the separate firm-lookup flow and aren't subject to this check.
- **Provider** (`providers`, **int id**) — firm profile, `embedding` (pgvector),
  ranking tier, `full_profile_edit_paid`, claim/membership relations.
- **RFQ** (`rfqs`) — `id`, `customer_user_id`, `nda_required` (bool), `rfq_status`
  (`RfqStatus`), **`is_closed`** (bool), `quote_count`, `selected_provider_id`, project
  description + metadata. `is_closed` is kept **in lockstep with `rfq_status`** by a model
  validator (`RFQ._sync_is_closed`), so the two can never drift: any ORM assignment of
  `rfq_status` recomputes `is_closed = rfq_status in _CLOSED_RFQ_STATUS_VALUES`. The column
  is retained (some admin endpoints read/write it via raw SQL). The quote-submit gate checks
  `is_closed` OR live submitted-quote count >= `RFQ_MAX_QUOTES`.
- **RFQFile** (`rfq_files`) — uploaded project files (S3 keys).
- **RFQMatch** (`rfq_matches`) — AI match results: `rfq_id`, `provider_id`, rank/score.
- **RFQDispatchBatch** / **RFQDispatch** — teaser dispatch batching + per-provider sends.
- **RFQUnlock** (`rfq_unlocks`) — `rfq_id`, `provider_id`, **`unlock_status`**
  (`UnlockStatus`). `unlock_status == "unlocked"` is the ONLY value that grants access
  (§8). Subscription-granted unlocks also write `"unlocked"` but have no `PaymentAttempt`.
- **RFQNDA** (`rfq_ndas`) — one row per (rfq, provider). Fields: `rfq_id`, `provider_id`,
  `customer_user_id`, `nda_status` (`NdaStatus`), `signrequest_document_id`,
  `signrequest_template_id`, `signed_pdf_s3_key`, `audit_trail_s3_key`,
  **`customer_signed_at`**, **`provider_signed_at`**, **`fully_signed_at`**, timestamps.
- **Quote** (`quotes`) — provider's bid: pricing, turnaround, assumptions, scope,
  `quote_status` (`QuoteStatus`), optional quote document (S3), and
  **`provider_contacted_at`** (timestamp, migration `e5b8c3d21f09`, 2026-05-30): set when the
  provider marks an accepted RFQ "customer already contacted" on `/provider/accepted-rfqs`.
  Persists the dismissal server-side (was localStorage-only and reset every session); the
  `/provider/quotes/me` serializer exposes it as `provider_contacted` and
  `POST /provider/quotes/{id}/mark-contacted` sets it (idempotent, ownership-checked).
- **PaymentAttempt** — one row per checkout attempt; `purpose` (`PaymentPurpose`),
  `status` (`PaymentStatus`), deterministic `idempotency_key`.
- **WebhookEvent** — inbound webhook dedup/audit (`provider`, `external_event_id`,
  `signature_verified`, `processing_status`).
- **Subscription** — `subscription_type` (`SubscriptionType`), `status`, period dates,
  Stripe ids.
- **SystemConfig** (`system_config`) — runtime config / secrets editable via Admin →
  Settings. Read through `config_service` (see §17).
- Plus: Advertisement, Campaign/Invite, SupportTicket, EmailFailure, Search models.

Enums live in `app/models/enums.py` (RfqStatus, QuoteStatus, NdaStatus, UnlockStatus,
PaymentStatus, PaymentPurpose, SubscriptionType/Status, AdStatus, etc.).

---

## 5. RFQ lifecycle (`RfqStatus`)

```
draft
  → submitted
     → (awaiting_nda_payment → awaiting_customer_signature)   # NDA RFQs only, transitional
        → open_for_dispatch
           → dispatching
              → open_for_unlock
                 → quote_limit_reached
                 → customer_selected_provider
                 → closed_no_selection
                 → cancelled
```

The `awaiting_nda_payment` / `awaiting_customer_signature` states are **transitional
only and MUST NOT block dispatch** (§19). They exist for bookkeeping; dispatch proceeds
once the customer's $10 NDA fee is recorded.

---

## 6. Search & AI matching (the LLM stack)

Search powers both the public provider search and RFQ→provider matching. Config is read
**runtime-config-first** (the `system_config` DB table via `config_service.get_runtime_config`),
falling back to env / `settings`. Default provider is **DeepInfra**
(`OPENAI_API_BASE=https://api.deepinfra.com/v1/openai`).

Four configurable LLMs (originally "the three LLMs"; LLM4 added for the chatbot):

1. **Embeddings** — `BAAI/bge-large-en-v1.5` (default). Provider profiles are embedded and
   stored on `Provider.embedding`; candidate retrieval is a pgvector cosine prefilter
   (top ~50). Keys: dedicated `EMBEDDING_API_KEY`/`EMBEDDING_API_BASE` if both set, else
   the `OPENAI_*` keys. (`search_service.py`)
2. **Search/ranking chat LLM** — default `moonshotai/Kimi-K2.5` (via `OPENAI_*`). Used for
   query→structured-intent extraction and the two ranking passes
   (`llm_pass1_filter`, `llm_pass2_rank`). (`search_service.py`)
3. **Doc / analysis LLM (LLM3)** — `DOC_LLM_*` keys (fallback to `OPENAI_*`), default
   `gpt-4o-mini`. The capable, more-expensive specialist: document collapse,
   support-ticket classification, and image/document analysis delegated by the
   chatbot. (`support_service.py`, `help_service.py`)
4. **Chatbot LLM (LLM4)** — `CHAT_LLM_*` keys (fallback to `DOC_LLM_*` → `OPENAI_*`),
   default `gpt-4o-mini`. Cheap/fast model that is the **default brain of the help
   chatbot**. It answers ordinary platform questions itself in a single call. When a
   turn requires analysing an image or reading a specific document's contents, LLM4
   replies with a one-line `DELEGATE: <focus>` directive and `help_service` re-runs the
   turn on LLM3 (the specialist). Sentinel-based, so one model call on normal turns and
   a second only when delegating; provider-agnostic (no function-calling dependency).
   Note: the chatbot does **not** yet fetch a user's specific RFQ/Quote by id — pasted/attached
   document text in the conversation is what LLM3 analyses today. (`help_service.py`)

   **Phase 1 cost/scope controls (2026-05-30, `help_service.py`):**
   - **RAG:** instead of stuffing the whole manual every turn, the manual is chunked by
     `##`/`###` headers, each chunk embedded once (in-memory cache keyed by manual hash,
     reusing `search_service.generate_embedding`), and only the top-`_RAG_TOP_K=4` chunks
     for the query are put in the prompt. **Fail-safe:** if embeddings are unavailable it
     falls back to the full manual, so the chatbot never breaks because of RAG.
   - **Scope-gate:** the query embedding's best chunk similarity is checked against
     `_SCOPE_MIN_SIM=0.20`; a clearly off-topic question is refused with a canned message
     BEFORE any paid LLM call. Conservative threshold to avoid false refusals.
   - **Budget cap:** every turn's estimated cost (`_estimate_cost`, default
     Gemini 2.5 Flash $0.0003/$0.0025 per 1K in/out, overridable via runtime-config `CHAT_LLM_PRICING` JSON)
     is stored in `help_chat_logs.cost_usd` (migration `f6c9d4e32a10`). A pre-flight sums the
     user's month-to-date cost; at `CHATBOT_MONTHLY_BUDGET_USD=15.0` it **hard-blocks** with a
     "contact us to raise your limit" message (zero cost). Admins are exempt. This is in
     addition to the existing 50-messages/day cap.
   - **Scope widened (2026-05-30):** the assistant answers BOTH platform and general
     mechanical-engineering questions; the scope-gate allows engineering-intent queries
     (`_looks_engineering`) so eng questions aren't refused. Still no legal/financial/medical
     advice and no safety-critical engineering sign-off.
   - **Cost accuracy:** uses real API `usage` tokens with a char-based (~4 chars/token) fallback
     in `_call_llm` so a turn is never undercounted to $0 if usage is omitted.

   **Operating Cost panel (admin, 2026-05-30):** `/admin/operating-cost` (endpoint
   `GET /admin/operating-cost`) shows where money goes: LLM cost per model from REAL token
   usage in `help_chat_logs` (chatbot = actual), search/ranking + Stripe fees as labelled
   ESTIMATES, Render hosting from `RENDER_MONTHLY_BUDGET`, and arbitrary fixed monthly line
   items from the admin-editable `OPERATING_COST_ITEMS` JSON. Prices come from
   `app/services/cost_catalog.py` — read LIVE from the admin-editable `LLM_PRICING` runtime
   config (takes effect instantly) with a hardcoded STATIC fallback (so it still works mid-deploy
   or with no network); update `LLM_PRICING` in Settings when a vendor changes prices rather than
   web-scraping. Untracked-but-billing services (AWS/Resend/SignWell/DeepInfra) are listed as a
   reminder to add via `OPERATING_COST_ITEMS`.

   **Bandwidth panel (admin, 2026-05-30):** `/admin/bandwidth` (page) → `GET /admin/bandwidth`
   pulls CPU, memory, HTTP request volume and latency from the Render Metrics API
   (`/v1/metrics/{cpu,memory,http_requests,http_latency}`, Bearer `RENDER_API_KEY`,
   time-series JSON) for the web+API services over a trailing window (6h/24h/3d/7d). Pure logic
   in `app/services/capacity_advisor.py` (unit-tested): parse_series, summarize (avg/peak/p95 +
   downsampled sparkline), trend_pct (recent-half vs earlier-half growth), and recommend()
   which turns PEAK utilization % vs the instance's plan capacity (RENDER_PLANS ladder) + trend
   into a healthy / watch / scale_now recommendation naming the next Render plan. Frontend draws
   inline-SVG sparklines (no chart lib). Degrades cleanly when RENDER_API_KEY is unset or the
   instance is free (Render metrics need a paid plan). The search/ranking LLM row is now ALSO
   actual: `search_service` accumulates `response.usage` tokens across the intent + pass1 +
   pass2 calls into `pipeline_info`, persisted on `search_requests.llm_prompt_tokens/
   llm_completion_tokens/llm_cost_usd` (migration `c9f2a7e54b33`); the panel sums them
   (falling back to a labelled estimate only for older rows with no tokens). Settings exposes
   editable `LLM_PRICING` + `OPERATING_COST_ITEMS` JSON fields. NOTE: vendor prices are NOT
   auto-scraped (vendor pricing pages have no stable API and a mis-parse would be a silent
   1000x cost error) — update `LLM_PRICING` manually; the static catalog is the safe fallback.

   **Phase 2 personalization (2026-05-30, `help_context.py`):** before answering, the backend
   builds a COMPACT, user-scoped account snapshot — subscription, RFQ/quote counts, free-NDA
   credits, and prioritized ACTION ITEMS (customer: NDAs awaiting countersignature, RFQs with
   quotes to review; provider: accepted quotes awaiting contact, NDAs to sign on open RFQs) —
   via `build_account_context`/`render_account_context`, and injects it into the system prompt
   so the assistant answers "what should I do next?" and questions about the user's OWN
   RFQs/quotes/subscription. Read-only and scoped to the authenticated user (never another
   user's data); every query is defensive and degrades to an empty snapshot on error. The chat
   widget also passes the current page path (`ChatRequest.page`) for context-awareness.
   Account-related questions bypass the scope-gate so they're never wrongly refused. (2026-05-30: the snapshot was expanded to the FULL dashboard metric set — provider rfqs_received/quotes_submitted/accepted/pending/not_selected/ndas_signed/win_rate; customer rfqs total/open/quoted/selected/cancelled/quotes-received + searches-used; identity + member_since — so the assistant answers any account-figure question directly. Every query is filtered by the signed-in user's id / provider membership, so there is zero cross-user contamination.)

   **Phase 3 navigation + drafting (2026-05-30):** the system prompt lets the model end a reply
   with a `SUGGESTED_LINKS: /path|Label ;; ...` line; `help_service._extract_links` strips it
   from the visible text and returns validated **internal-only** links (allowlisted prefixes,
   no external/`/admin`/`//`, max 3) as `ChatResponse.links`. The chat widget renders them as
   buttons that `router.push` in-app (and close the widget). The prompt also instructs the model
   to draft RFQ descriptions / messages for the user to review and submit.

   **Phase 4 confirm-then-execute actions (2026-05-30):** the assistant can perform a tightly
   bounded set of SAFE, REVERSIBLE writes — currently only `mark_contacted` / `undo_mark_contacted`
   on a provider's accepted-RFQ quote. Security model (do not weaken):
   - **The LLM can only PROPOSE, never execute.** It emits `PROPOSE_ACTION: type|quote_id|summary`;
     `help_service._extract_action` validates the type against `_PROPOSABLE_ACTIONS`, strips the
     line, and returns an INERT `ChatResponse.action`. No write happens during answer generation.
   - **Explicit user confirmation** — the widget renders a Confirm/Cancel card; only the user's
     Confirm click calls `POST /help/action`.
   - **The endpoint is the authorization source of truth** — it requires auth + chatbot access,
     enforces the `_EXECUTABLE_ACTIONS={mark_contacted, undo_mark_contacted}` allowlist, and calls
     `quotes.set_quote_contacted` which **re-checks ownership** (the quote must belong to the
     caller's provider membership). It writes an `AuditLog` (`extra_data`, separate commit). It
     NEVER trusts the LLM's framing or a hallucinated id (a non-owned id → 404, no harm).
   - **Allowlist is intentionally tiny and reversible.** Pay, sign NDA, submit/accept a quote,
     cancel, delete, change settings, and send messages are NOT executable — the assistant gives a
     navigation link for those and the user does them. Reversibility: `undo_mark_contacted` (and an
     Undo button on the Accepted-RFQs closed cards) restores state. See §19 invariant 16.

   **Phase 4b OPT-IN AUTONOMOUS MODE (2026-05-30):** a user can enable autonomous mode
   (`users.agent_autonomous_enabled`, migration `a7d0e5f41b22`) via `POST /help/agent/enable`
   which REQUIRES `accept_risk=true` and records `agent_autonomous_consented_at`. When ON, the
   assistant auto-executes proposed allowlisted actions WITHOUT a per-action confirm card. The
   executable set expands to `accept_quote`, `cancel_rfq`, `withdraw_quote` (plus the safe
   mark/undo) — all on the user's OWN records, ownership re-checked, audit-logged, via the single
   `help_actions.execute_action` authority. **HARD STOP:** `POST /help/agent/disable` (the red STOP
   button in the widget) flips the flag off; the flag is re-read FRESH from the user row on every
   turn and at the executor, so the stop takes effect immediately. **Payments and NDA e-signing are
   NEVER autonomous** — they live in `help_actions.FORBIDDEN_ACTIONS` and are rejected (403) even
   with the flag on; the assistant instead gives full step-by-step guidance (manual §15b/§15c) and
   the user clicks. See §19 invariant 17. 
   **Admin actions (2026-05-31):** when the signed-in user is an ADMIN, the assistant can act on support tickets directly — `resolve_ticket` / `escalate_ticket` / `archive_ticket` / `mark_ticket_spam` (in `help_actions.ADMIN_ACTIONS`). These are gated on the admin ROLE (admins don't need the consumer autonomous-consent flag) and run for admins via `_maybe_autoexecute`. The ticket id comes from the current page path (`/admin/support/<id>`), parsed server-side — the LLM never supplies it. The admin prompt block names the exact on-screen buttons (Resolve/Escalate/Archive/Mark Spam) so guidance is accurate. Payments and NDA signing remain in FORBIDDEN_ACTIONS even for admins.

   **Phase 4c DOCUMENT-DRIVEN WORKFLOWS (2026-05-30):** the chat widget has an upload button
   (paperclip). `POST /help/upload` stages a PDF/DOCX/TXT (<=10MB) to S3 under
   `assistant-uploads/{user_id}/` (ownership provable by key prefix), extracts text, and returns
   `{key, filename, mime, excerpt}`. Staged attachments ride with the next chat message. Two new
   autonomous-tier actions run the workflow: `create_rfq_from_docs` (customer — creates a DRAFT
   RFQ via `create_rfq` from the doc text + a model summary, attaches the files as `RFQFile`,
   and links the user to review/SUBMIT it themselves) and `submit_quote_from_docs` (provider —
   LLM-extracts quote fields, `submit_quote`, attaches the doc). **Security:** file keys come
   ONLY from staged uploads and are re-validated by `help_actions._validate_attachments` to the
   caller's own `assistant-uploads/{user_id}/` prefix — the LLM never supplies a key, so a
   malicious uploaded document is inert data and cannot attach a foreign file or escalate. These
   are gated exactly like other autonomous actions (confirm-then-execute, or auto with consent +
   hard-stop). Submitting the RFQ (which triggers the $10 NDA fee / dispatch) and all payments/NDA
   signing remain human-clicked. See §19 invariant 17.

   **Phase 5 quality flywheel (2026-05-30):**
   - **Feedback loop:** each assistant turn returns its `log_id`; the widget shows 👍/👎 which
     POST `/help/feedback` (ownership-checked — a user may only rate their OWN
     `help_chat_logs` row; idempotent). The rating is stored in `help_chat_logs.feedback`
     (1/-1/NULL, migration `b8e1f6c43d21`) and surfaced (with `cost_usd`) in `/admin/help/logs`
     for weekly review of 👎 and refusals.
   - **Golden evals in CI:** `backend/tests/eval/` (driven by `golden_help.yaml`) asserts the
     deterministic guardrails — link allowlist accept/reject, the proposable-action set, the
     forbidden (payments/NDA) set, the PROPOSE_ACTION parser, and that the manual still says
     ProMechDirectory / $50 / $500-yr / 5-free-NDA / account-required (and NOT the stale
     ProReadyEngineer / $20 / 10-free). CI runs `pytest tests/eval` after the unit suite.
   - **Deliberately deferred (documented, not built):** a cross-user semantic answer cache is
     NOT implemented because Phase 2 injects each user's OWN account data/actions into answers,
     so a question-keyed shared cache could leak one user's data to another. Token-streaming is
     deferred because links/action/cost are computed from the FULL reply after one synchronous
     call; SSE would require reworking that post-processing for marginal benefit on short answers.

(A support-ticket classifier in `support_service.py` reuses LLM3 keys.)

`EMBEDDING_*`, `DOC_LLM_*` and `CHAT_LLM_*` are **runtime-config keys only** (no Pydantic
settings field), so in practice they must be set in Admin → Settings, not env. See §20.

---

## 7. Dispatch (matching + teaser emails)

- **Trigger:** an RFQ dispatches when it is **submitted** (for NDA RFQs, after the $10
  customer fee is recorded — but the NDA itself never blocks dispatch). `submit_rfq`
  runs the AI search, writes ranked `RFQMatch` rows, sets the RFQ to `open_for_dispatch`,
  and sends teaser emails in batches. (`rfq_service.py`)
- **Concurrency-safe:** `submit_rfq` claims the RFQ with a single conditional
  `UPDATE ... WHERE rfq_status IN (<pre-dispatch states>)`. Only the winning caller
  searches/dispatches; concurrent triggers no-op. This prevents duplicate matches/emails.
  It is also idempotent (skips re-search if `RFQMatch` rows already exist).
- **Batching:** `RFQ_DISPATCH_BATCH_SIZE=5` providers per batch; interval
  `RFQ_DISPATCH_BATCH_INTERVAL_HOURS` (default 24, **15-minute floor** enforced).
  `RFQ_MAX_QUOTES=5` — once 5 quotes arrive the RFQ hits `quote_limit_reached`.
- **Schedulers (live mechanism — NOT Celery):**
  - **Primary:** the Render cron `proreadyengineer-rfq-cron` (`*/15 * * * *`) POSTs
    `/api/v1/internal/cron/dispatch-rfq-batches`.
  - **Backup:** an in-process asyncio loop in `app/main.py` calls the same dispatch
    function (~every 5 min). Both honour the interval floor.
  - The internal cron endpoint is **unauthenticated by design** (CRON_SECRET was removed).
  - **Celery exists in the code but no worker/beat runs in `render.yaml`** — the entire
    Celery layer is dormant in production. Emails and dispatch run inline / via cron. See §20.

---

## 8. Provider unlock & access gating

- Access to an RFQ is granted by an `RFQUnlock` row with **`unlock_status == "unlocked"`**.
  Every backend access check recognizes only this value. Two ways to get it:
  1. Pay the **$50** unlock fee (Stripe) → `PaymentAttempt` + `RFQUnlock(unlocked)`.
  2. Hold an active **`provider_annual`** subscription → free `RFQUnlock(unlocked)` with
     **no** `PaymentAttempt` (this absence is how subscription unlocks are distinguished).
  ⚠️ Historical bug: subscription unlocks once wrote a non-recognized status
  (`granted_by_subscription`) and stayed locked. Never reintroduce a status other than
  `"unlocked"` for granting access.
- **For NDA RFQs**, the full project description + files are *additionally* gated on the
  mutual NDA being fully signed. The provider unlock endpoint returns:
  - `unlocked` — has an unlocked `RFQUnlock`.
  - `provider_has_signed` — THIS provider has signed (`provider_signed_at` set), may still
    be waiting on the customer.
  - `provider_nda_signed` — BOTH parties signed (`fully_signed_at` set) → full access.
  - `_can_view_full = (not nda_required) or provider_nda_signed`.

---

## 9. NDA flow — "sign to read" (mutual, provider-first) — CRITICAL

This is the flow most often re-explained. Do not redesign it without the owner's say-so.

**Intended end-to-end:**

1. Customer marks an RFQ **NDA required** and pays the **$10** NDA fee (always, when NDA
   required). The RFQ then **dispatches normally** — the NDA does NOT hold up dispatch.
2. A provider receives the teaser and **unlocks** ($50, or free for annual subscribers).
3. To **read** the RFQ, the provider clicks **Sign NDA**. The backend
   (`nda_service.add_provider_to_nda`) creates **ONE mutual NDA document** in SignWell with
   **both** the provider and the customer as signers. The provider signs; the customer is
   then emailed by SignWell to countersign. There is **no "customer signs first"
   precondition**.
4. SignWell records each signer separately (matched by email) and marks the NDA
   `fully_signed` only once **both** have signed. The backend also defensively polls
   SignWell on every status read (`_sync_nda_signatures`) so it does not depend solely on
   the webhook.
5. Once fully signed, the provider sees the **full description + files** and can quote.
   Until then, only the redacted teaser/preview is shown.

**SignWell integration specifics (these have each caused outages — respect them):**

- **Template ID must be the API UUID**, e.g. `162095ae-2e32-4afd-b170-fb5753d8e923`
  (`SIGNWELL_TEMPLATE_ID` in `system_config`, set via Admin → Settings → Document Signing).
  It is **NOT** the share-link slug from `https://www.signwell.com/new_doc/<slug>/` — the
  slug returns `404 "Couldn't find the template"` and silently breaks the whole NDA flow.
  When you recreate a template in SignWell, re-copy its API UUID.
- **Auth header is `X-Api-Key`** (not Bearer). Base URL `https://www.signwell.com/api/v1`.
  Key is read from `system_config` (`SIGNWELL_API_KEY`). Render returns this secret as
  empty via API/dashboard (write-only) — only the running process (Render Web Shell) can
  read it live for diagnostics.
- **Label vs api_id:** when you rename a field's label in the SignWell editor (e.g. to
  `provider_company`, `prs`), SignWell **keeps the original auto api_id**
  (`TextField_1`, `Signature_1`). So api_ids in the API ≠ the labels you see. The account
  has exactly **one** template (`promechdirectory NDA 3`).
- **NDA prefill is ENABLED but careful** (verified via draft-mode test 2026-05-30).
  `add_provider_to_nda` pre-fills only values we hold from the authenticated accounts / our
  records (customer & provider name + company, customer governing state, provider state) plus
  the system-owned `effective_date`. It does NOT guess unknown fields (`*_entity_type` left
  empty) and NEVER sends signature fields. Prefilled values are **editable defaults, not
  locks** (SignWell returns `read_only=None`); the draft test confirmed the signature fields
  (`prs`, `cus`) stay empty+required, so prefilling text does NOT skip signing. The old
  "Thanks for filling out / no signature prompt" short-circuit needs a signer whose fields
  are ALL pre-filled — leaving entity_type + signature empty prevents it. **To truly LOCK a
  value, mark that field read-only in the SignWell template itself** (the API only sets a
  default). Still required: **OMIT the `template_fields` key when it would be empty** —
  sending `template_fields: []` makes SignWell reject the create with
  `400 {"invalid_keys":["template_fields"]}`. The `/nda/signing-url` endpoint catches
  Signwell HTTP errors and returns a clean 502 (an uncaught 500 reaches the browser without
  CORS headers and shows as a misleading "Network Error").
- **Signing order:** the document uses email-based signing with `apply_signing_order: True`
  (provider = signer "1", customer = signer "2"). **Do NOT set document-level
  `embedded_signing`** — it suppresses ALL SignWell invitation emails (that was the bug
  that left the customer un-notified).
- **Webhook:** `/api/v1/webhooks/signrequest` (name kept for historical registration —
  do not rename). It records each signer and downloads the signed PDF to S3 on completion.

**Notifications are part of the NDA workflow, not optional.** At every step the waiting
party MUST be told there is an action for them, through BOTH channels:

- Provider clicks Sign NDA → SignWell emails the **provider** their signing link.
- Provider signs → SignWell automatically emails the **customer** to countersign, AND the
  customer's portal surfaces it (see §16 — it appears in the **Activity Summary** panel as
  an amber "Action required: N NDA(s) awaiting your signature" callout; the
  `/customer/my-rfqs` payload sets `nda_awaiting_customer_signature = true` when the
  provider has signed but the customer hasn't).
- Both signed → the provider's RFQ view unlocks (full description + files + quote form).

Any future change to the NDA flow MUST preserve both channels (SignWell email + in-app
portal) for whichever party is being waited on, and MUST keep in-app notifications inside
the existing **Activity Summary** pattern — not as bolted-on one-off banners.

**There is exactly ONE provider-first NDA model.** The old customer-iframe-first path
(`/nda/initiate`, `/nda/confirm-signed`, `create_customer_nda`, `get_customer_signing_url`)
has been removed. A separate `create_post_acceptance_nda` exists for a post-quote-acceptance
NDA path; note it still uses customer-first ordering and DOES pre-fill fields (§20).

---

## 10. Quotes

- A provider with full access submits a quote (`QuoteForm`): min/max price (USD),
  turnaround, assumptions, scope notes, optional quote document. An AI extractor can
  pre-fill the form from an uploaded quote document.
- The customer reviews quotes on the RFQ and **accepts** one
  (`/customer/quotes/{id}/accept`). On acceptance the provider sees the customer's contact
  details (revealed only at `quote_status == "accepted"`), and the RFQ moves to
  `customer_selected_provider`.
- `RFQ_MAX_QUOTES = 5`: only the first 5 quotes are accepted/shown; the RFQ then reaches
  `quote_limit_reached`.
- **`is_closed` is auto-synced from `rfq_status` (never set it directly).** The RFQ model
  has a `@validates("rfq_status")` hook (`_sync_is_closed`) that recomputes
  `is_closed = rfq_status in {quote_limit_reached, customer_selected_provider,
  closed_no_selection, cancelled}` on every status assignment, so the two can't drift. **To
  close an RFQ, set `rfq_status` to a closed status — do NOT assign `is_closed`.** Unlocking
  must NEVER close an RFQ (unlocks are unlimited paid revenue); only submitted quotes
  reaching `RFQ_MAX_QUOTES`, provider selection, or cancellation close it. (History:
  `is_closed` used to be set independently in ~6 places, which let it drift — e.g.
  `rfq_status=open_for_unlock` + `is_closed=True` wrongly rejecting quotes as "This RFQ is
  closed". Fixed 2026-05-30: the redundant `is_closed = True` writes were removed and the
  validator now derives it. The DB column is retained because some admin endpoints
  read/write it via raw SQL.)

---

## 11. Payments & webhooks

- **Stripe** is the live processor. Stripe-hosted Checkout for one-time fees and
  subscriptions (`create_stripe_checkout_session`). Secret/keys read from runtime config.
- **Idempotency:** every checkout uses a deterministic `idempotency_key`; `PaymentAttempt`
  rows dedupe, and fulfillment functions early-return on an existing COMPLETED/active record.
- **Webhooks:**
  - Stripe → `/api/v1/payments/webhooks/stripe`: signature-verified
    (`stripe.Webhook.construct_event`), deduped via `WebhookEvent`, fulfillment idempotent.
  - PayPal → `/api/v1/payments/webhooks/paypal`: signature-verified against PayPal's
    verify-webhook-signature API, **fail-closed in production**. PayPal is not configured,
    so this path is effectively unused.
  - SignWell → `/api/v1/webhooks/signrequest` (see §9). **Not** signature-verified (§20).
  - Resend → `/api/v1/payments/webhooks/resend`: records bounces/complaints/failures.
- **Fulfillment map** (`fulfill_payment_purpose` routes by `PaymentPurpose`):
  - `rfq_unlock` → `rfq_service.complete_rfq_unlock` (writes unlocked `RFQUnlock`).
  - `nda_fee` → finds/creates `RFQNDA`, sets `customer_signature_pending`; **does NOT
    change `rfq_status`** (must not strand the RFQ — §19).
  - `search_subscription`, `provider_annual_subscription`, `advertisement_subscription`,
    `full_profile_edit_unlock` → create/renew the relevant `Subscription` / flag.

---

## 12. Subscriptions

- **Provider annual** (`provider_annual`, $1,000/yr) — grants free RFQ unlocks while
  active (the unlock path checks for it and writes an unlocked `RFQUnlock` with no payment).
  As of 2026-05-30 it ALSO grants **direct customer-contact visibility**: on an RFQ the
  subscriber has unlocked, `/provider/rfqs/{id}/unlock/status` returns `customer_contact`
  (name, company, email, **phone**, state — phone added 2026-05-30; still no street address
  field). Gating mirrors the NDA rules: non-NDA RFQ shows contact on unlock; an
  NDA-required RFQ returns `contact_locked_reason='nda_required'` and reveals contact only
  after the mutual NDA is fully signed (never overrides the NDA the customer paid for).
  Non-subscribers get `customer_contact=null`. The provider RFQ page renders this as an
  emerald "Customer Contact (Annual member)" card; the upgrade page lists it as the first
  annual feature.
- **Customer search** (`search_tier_1`, **$50/month or $500/year**) — raises the monthly
  search quota from 5 → 100 and grants **5 free NDA-required RFQs per calendar month**
  (the $10 NDA fee is waived until the allowance is used; metered on
  `users.monthly_nda_credits_used` + `nda_credits_reset_at`, enforced in `nda_checkout`).
  Monthly vs annual is the SAME subscription type (`search_tier_1`) and the SAME access —
  only the price and granted period differ (30 vs 365 days), carried in checkout metadata
  `billing_interval` and applied in `_fulfill_search_subscription`. This is the only
  customer subscription. `search_tier_2` has been **retired** (no longer sold/displayed);
  any pre-existing tier-2 subscriber is still honored via the `.in_(['search_tier_1',
  'search_tier_2'])` quota lookup, but it cannot be purchased.
- **Provider full-profile-edit** — one-time unlock (or included with annual).
- **Advertisement** — featured-firm / software-provider listings.
- **Founding-member promo (2026-05-31)** — when a provider accepts a campaign invite at
  registration, `campaign_service.redeem_campaign_invite` grants a REAL `provider_annual`
  ($1,000 tier) subscription whose `current_period_end = now + founding_duration_days`
  (default 90 = 3 months), tagged `provider_name="founding_campaign"` /
  `external_subscription_id="founding:{campaign_id}"`. It is the full annual tier (free RFQ
  unlocks + customer-contact visibility), just time-boxed. Wired in the registration
  endpoint's campaign-invite branch (the campaign token is a RANDOM string, not the JWT
  invite the RFQ-dispatch flow uses, so it is matched separately). Idempotent; consumes one
  founding slot; marks the invite `REGISTERED`.
- **Subscription expiry enforcement (2026-05-31) — CRITICAL, see §19 invariant.** Access
  gates check ONLY `subscription_status=='active'`; nothing else ends a subscription when
  its paid period lapses. The daily Celery beat task `maintenance.expire_subscriptions`
  (`expire-subscriptions`, 24h) is the SOLE enforcement point: it cancels any ACTIVE sub
  whose `current_period_end < now - 1 day` (grace absorbs recurring-renewal webhook
  timing), setting status `CANCELLED` + `cancelled_at`. Recurring Stripe subs keep their
  end date pushed forward by `invoice.paid` / `subscription.updated` webhooks, so only
  genuinely-lapsed ones are caught; one-time annual ($1,000) and founding promos (which
  never renew) end exactly on schedule. NULL end dates are skipped. Testable helper:
  `maintenance.expire_due_subscriptions(db, now=, grace=)`. Tests:
  `tests/unit/test_subscription_timing.py`.

---

## 13. Email & notifications (Resend)

- Sent via Resend API (`https://api.resend.com/emails`), SMTP fallback, then console +
  failure record. Templates are Jinja2 under `app/templates/emails`.
- Active notification emails include: RFQ teaser (`rfq_teaser`), quote received
  (`quote_received`), quote accepted (`quote_accepted`), welcome, password reset, email
  verification, ad approved/rejected, campaign invite.
- **Failure tracking:** send failures and inbound bounce/complaint webhooks are recorded
  as `EmailFailure` rows and surface in Admin → Debugging (the nav row turns red).
- **Inbound reply de-duplication (2026-05-31):** `support_service.strip_quoted_reply()` removes quoted prior-thread content (Gmail "On … wrote:", Outlook "-----Original Message-----", `>`-quoted blocks) from an inbound email body at ingest in `find_or_create_ticket_from_inbound`, so each stored `SupportTicketMessage` holds ONLY the sender's new text — the thread already tracks history separately. Safety net: if stripping would empty the message, the original body is kept. Going-forward only (existing rows unchanged). All referenced email templates now exist in `app/templates/emails/` (several were
  historically missing → empty body → Resend 422; all created 2026-05-29). NDA workflow
  notifications in §9 rely on SignWell's own emails, not these.
- **Provider campaign deliverability (2026-05-31):** the founding-member invite campaign
  (Admin -> Campaigns) sends bulk email that must clear the 2024->2026 Gmail/Yahoo
  bulk-sender rules. `app/services/campaign_email.py` owns a deliverability-safe shell:
  `body_to_html()` (plain text -> safe paragraphs/autolinks; passes existing HTML through),
  `wrap_campaign_email()` (600px table-based branded shell with `#0F2B54` header + a
  CAN-SPAM footer carrying the physical address and unsubscribe link),
  `html_to_text()` (plain-text alternative part), and `build_unsubscribe_headers()`
  (RFC 8058 `List-Unsubscribe` with both https + mailto, plus
  `List-Unsubscribe-Post: List-Unsubscribe=One-Click`). `campaign_service.send_next_batch`
  wraps every authored body in this shell and posts `from/to/subject/html/text/headers`
  to Resend. **Suppression:** any provider with an `UNSUBSCRIBED` invite in ANY campaign is
  excluded from future sends; `BOUNCED`/`UNSUBSCRIBED` are never re-emailed.
- **Public unsubscribe (no auth):** `POST /api/v1/campaigns/unsubscribe/{token}` is the
  one-click target Gmail/Yahoo call; `GET` returns a friendly HTML page when a recipient
  clicks the link. Both are idempotent and flip the invite to `UNSUBSCRIBED`.
- **AI "Draft with AI" (2026-05-31):** `POST /api/v1/admin/campaigns/draft-email` (admin
  only) takes a plain-language brief and uses LLM4 (`_get_chat_llm_config`/`_call_llm` from
  `help_service`) to return `{subject, body}` in plain text with `{{firm_name}}` /
  `{{invite_link}}` etc. placeholders; the system adds the shell/footer/unsubscribe, so the
  model is instructed NOT to write a signature, footer, or address. Frontend: a "Draft with
  AI" panel in the Email Composer fills the subject + body fields. External DNS steps
  (DMARC publish, Postmaster Tools) are the operator's, documented in
  `EMAIL_DELIVERABILITY_SETUP.md`. Tests: `tests/unit/test_campaign_email.py` (9).

---

## 14. Files & storage (AWS S3)

- Uploads via presigned POST (25 MB cap); downloads via presigned GET. RFQ files, quote
  documents (`quote-documents/...`), and signed NDA PDFs (`ndas/{rfq_id}/...`) live in the
  S3 bucket (`promechdirectory-uploads` per `render.yaml`).
- Text extraction supports PDF (PyPDF2), DOCX (python-docx), and plain text.

---

## 15. Auth & security

- JWT (HS256) access (60 min) + refresh (7 day) tokens; bcrypt password hashing; account
  lockout; slowapi rate limiting (the `@limiter.limit` decorator must be the **outer**
  decorator on a route).
- `SECRET_KEY` is generated by Render; the app **refuses to boot in production** if it is
  left at the insecure default (`config.py` model validator).
- CORS is scoped to the project's own origins (not any `*.onrender.com`).
- Email verification is required (`REQUIRE_EMAIL_VERIFICATION=True`).
- ⚠️ Frontend stores access/refresh tokens in `localStorage` (XSS exposure) — moving to
  httpOnly cookies is tracked backlog (§20).

---

## 16. Frontend structure & UI conventions

**Routes by area** (`frontend/src/app`):
- Public/marketing: `/`, `/search`, `/for-customers`, `/for-providers`, `/advertise`,
  `/featured-firms`, `/software-providers`, `/providers/[id]`, `/contact`, `/help`,
  `/privacy`, `/terms`.
- Auth: `/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email`,
  `/check-email`.
- Customer portal (`/customer/*`): `dashboard`, `rfq/new`, `rfq/[id]`,
  `rfq/[id]/tracking`, `quotes`, `active-rfqs`, `quoted-rfqs`, `accepted-rfqs`,
  `all-rfqs`, `cancelled-rfqs`, `profile`.
- Provider portal (`/provider/*`): `dashboard`, `rfq/[id]` (the unlock→sign→view→quote
  flow), `rfqs`, list pages, `nda/[id]/sign`, `profile`, `profile/full-edit`, `upgrade`,
  `claim`, `add-firm`, `advertise`.
- Shared: `/nda/[id]/sign` (customer NDA pay/sign), `/rfqs/[id]/unlock`.
- Admin (`/admin/*`): `dashboard`, `rfqs`(+`[id]`), `claims`, `providers`, `payments`, `operating-cost`,
  `webhooks`, `campaigns`, `support`(+`[id]`), `ads`, `users`, `data-extraction`,
  `debugging`, `settings`, `operating-cost`, `bandwidth`.

**API client:** `frontend/src/lib/api.ts` — axios instance, `Authorization: Bearer
<localStorage access_token>` request interceptor, single-flight 401→refresh→retry response
interceptor. Some pages bypass the interceptor with raw `fetch` (they do not get the
refresh-retry) — see §20.

**UI/UX conventions (follow these — the owner enforces them):**
- The **Activity Summary** panel (customer `AnalyticsPanel` on the dashboard, and the
  provider analytics panel) is THE place where stats and **action-required notifications**
  appear. New notifications for a persona go here, not as separate top-of-page banners.
- **Action-required notes must be LIVE.** Both dashboards refresh their data on mount, on a
  20s interval, and on window focus / tab `visibilitychange` (silent background refresh — no
  skeleton flicker), so guidance reflects current state without a manual reload. Each note's
  visibility must be derived from CURRENT data, not just an event flag: e.g. the provider
  "Accepted RFQ — contact the customer" note excludes quotes whose `rfq_status` is
  `cancelled`; the customer "NDA awaiting your signature" note is driven by the live
  `nda_awaiting_customer_signature` field from `/customer/my-rfqs`; the customer
  "you have N new quotes to review" prompt surfaces RFQs whose `quote_count` exceeds the
  count the customer has already viewed (tracked in `localStorage['customer_reviewed_quote_counts']`
  as rfqId->count, so it clears when they open the RFQ and re-appears if more quotes arrive),
  excluding closed/cancelled/selected RFQs. The NDA note (which EXCLUDES closed
  RFQs server-side — `awaiting_customer_sig` subtracts any RFQ with `is_closed`, so a
  cancelled/selected RFQ never asks the customer to countersign; the dashboard also guards
  with `!is_closed && rfq_status !== 'cancelled'`). When adding a note,
  derive its condition from live status/flags so it auto-clears when the underlying state
  changes (e.g. an RFQ is cancelled, an NDA is countersigned).
- **Async actions must guard against double-clicks and show progress.** Any button that
  fires a request which can take more than ~1s (Sign NDA / Resend, Check Status, Unlock,
  Submit Quote, Accept Quote, NDA pay) must: (a) set an in-flight state and `return` early
  if re-clicked, (b) `disabled` while in flight, (c) swap its label to a `Loader2` spinner
  + 'Working…/Checking…/Accepting…' text, and for multi-second ops (e.g. Sign NDA, which
  calls SignWell) (d) show a short inline 'please wait, don't click again' banner. This is
  the standard interactive pattern across both portals (see provider `handleSignNda`/
  `signingNda`, customer `handleAcceptQuote`/`acceptingId`).
- **"Action required" pattern:** amber card (`bg-amber-50 border-amber-200`) with an
  `AlertCircle` icon, a bold "Action required: …" heading, and explanatory subtext.
- Status pills via the shared `STATUS_COLORS` map; NDA state via `NdaBadge`.
- Toasts via `sonner` (`toast.success/error/info`).
- Customer shared list logic in `app/customer/_shared/RfqListPage.tsx`
  (`CustomerRFQ` type, `ACTIVE_STATUSES`, `useRfqs`, `RfqCard`).

---

## 17. Config & secrets

- **Runtime-config-first:** most settings (LLM keys/models, Stripe, PayPal, Resend, AWS,
  SignWell key + template id, RFQ batch params) are read from the `system_config` DB table
  via `config_service`, falling back to env / `settings`. They are editable live in
  **Admin → Settings** (tabs: AI, Payments, Email, Storage, Doc Signing, RFQ).
  `get_config_value` is uncached, so a corrected value takes effect immediately (no restart).
- **Where real secret values live:** the Render dashboard (`proreadyengineer-api` →
  Environment, write-only/masked) and `system_config`. The repo holds none. The Render API
  and dashboard return secret values as empty/masked — to read one live, use the Render Web
  Shell of the running service.
- `EMBEDDING_*` and `DOC_LLM_*` are runtime-config-only keys (no env settings field).

---

## 18. Deploy & CI

- `render.yaml`: `proreadyengineer-api` (build `pip install -r requirements.txt`; start
  `alembic upgrade head && uvicorn main:app`), `proreadyengineer-web`,
  `proreadyengineer-redis`, `proreadyengineer-db`, and `proreadyengineer-rfq-cron`
  (`*/15 * * * *` → POST the dispatch endpoint).
- **Deploy:** push to `main` → Render auto-deploys api + web.
- **CI:** `.github/workflows/ci.yml` runs `pytest tests/unit` on push/PR (SQLite-backed,
  no DB service). Covers NDA dispatch (incl. the stuck-RFQ regression + mutual-NDA webhook),
  auth, payment idempotency keys, and search-quota constants. Legacy suites
  (`test_payment_service`, `test_file_service`, `test_search_service`, `test_rfq_service`,
  `test_auth_service`) are **quarantined** (skipped) pending rewrite against the current API.

---

## 19. Invariants — rules that must never break

These encode business rules the owner has had to repeat. Treat a change that violates one
as a bug, even if tests pass.

1. **Dispatch never waits on a signature.** NDA RFQs dispatch as soon as the customer's
   $10 fee is recorded. The `awaiting_*` statuses are transitional and must not gate
   `submit_rfq`. (Regression test exists.)
2. **`unlock_status == "unlocked"` is the only access gate.** Both paid and
   subscription-granted unlocks write exactly this. Never invent another status to grant
   access.
3. **NDA is provider-first and mutual, one document, one model.** Provider signs first to
   read; customer is then asked to countersign; both signatures = full access. No
   "customer signs first" precondition. No second NDA model.
4. **NDA notifications use both channels and the existing UI pattern.** SignWell email +
   in-app, and the in-app notice lives in the **Activity Summary** panel (amber
   action-required card), not a bespoke banner.
5. **SignWell template id is the API UUID, never the `new_doc` slug.**
6. **Never set document-level `embedded_signing`** on the mutual NDA (it kills invitation
   emails). Use email-based signing with `apply_signing_order`.
7. **NDA prefill must never include signature fields, and must OMIT `template_fields` when
   empty.** Pre-fill only known account/record values + date as editable defaults; to lock a
   value, mark the template field read-only in SignWell (the API only sets a default).
8. **`nda_fee` fulfillment must not change `rfq_status`** (it once stranded NDA RFQs).
9. **Live fees are $50 provider unlock / $10 customer NDA (5 free/month for search subscribers) / $1,000 provider annual / $50-mo or $500-yr customer search.**
   Trust the checkout `amount=`, not product-name strings. (Provider unlock now reads the
   `RFQ_UNLOCK_PRICE=5000` constant.)
10. **Search requires an account (no anonymous search); quota is 5 free / 100 paid** (`FREE_SEARCH_LIMIT=5`/`PAID_SEARCH_LIMIT=100` in `search_service.py`). The `/search/query` and `/search/extract-and-describe` endpoints hard-reject unauthenticated callers with 401 (do not let the quota fallback fail open).
11. **Webhooks stay idempotent and signature-verified** (Stripe/PayPal); dedup via
    `WebhookEvent`.
12. **Production refuses to boot with the default `SECRET_KEY`** — keep that guard.
13. **One dispatch mechanism in prod:** Render cron + the in-process backup loop. Do not
    add a third trigger or assume a Celery worker exists.
14. **`is_closed` is a DATABASE-GENERATED column — unwritable, cannot drift.** As of migration
    `c3f8e1a90b21` (2026-05-30) `rfqs.is_closed` is `GENERATED ALWAYS AS (rfq_status IN
    ('quote_limit_reached','customer_selected_provider','closed_no_selection','cancelled'))
    STORED`; the ORM maps it with `Computed(...)`. NO path (ORM, Core `update()`, raw SQL) can
    write it — they error if they try. Close an RFQ ONLY by setting `rfq_status` to a closed
    status; `is_closed` follows in the DB. NOTE: because it is Computed, after a Core UPDATE of
    `rfq_status` the attribute is expired — re-load with `db.get(RFQ, id, populate_existing=True)`
    or `select(...).execution_options(populate_existing=True)` before reading it in async code,
    or you'll hit MissingGreenlet (see `dispatch_next_batch`).
15. **NDA action prompts must be gated on an OPEN RFQ.** The provider "Sign the NDA" /
    "awaiting signature" card, its auto-poll, and the dashboard `ndaTasks` filter — and the
    customer "NDA awaiting your signature" note — must all require the RFQ to be NOT closed
    (exclude `is_closed` / cancelled / selected). A half-signed NDA on a cancelled or
    superseded RFQ must never tell either party there is signing to do.

---


16. **The AI assistant may only EXECUTE allowlisted, reversible, non-financial actions, and
    only after explicit user confirmation.** The LLM proposes (`PROPOSE_ACTION`, inert); the
    hardened `POST /help/action` endpoint is the sole executor, enforces
    `_EXECUTABLE_ACTIONS` (currently just `mark_contacted`/`undo_mark_contacted`), re-checks
    resource ownership server-side, and audit-logs. Never let the assistant pay, sign, submit,
    accept, cancel, delete, change permissions/settings, or send messages — those stay
    navigation-only and user-performed. Adding to the allowlist is a deliberate security decision.

17. **Autonomous mode is opt-in, consented, hard-stoppable, and NEVER financial/legal.**
    `agent_autonomous_enabled` is set only via `/help/agent/enable` with explicit `accept_risk`,
    and cleared instantly by `/help/agent/disable` (STOP). Even when ON, the executor's
    `FORBIDDEN_ACTIONS` (payments, NDA e-signing) are rejected with 403 — the agent guides but
    the human clicks. All autonomous actions re-check ownership and audit-log. The autonomous
    allowlist (`accept_quote`/`cancel_rfq`/`withdraw_quote` + safe mark/undo) is a deliberate
    security decision; do not add money or signature actions to it.
18. **Every paid subscription must END as advertised, and the daily `expire_subscriptions`
    job is the ONLY thing that enforces it.** Access gates check ONLY
    `subscription_status=='active'` — they never look at `current_period_end`. So a sub left
    ACTIVE past its period would grant access forever (this was a real latent leak: one-time
    `provider_annual` and the founding promo never renew, so nothing else ends them). The
    `maintenance.expire_subscriptions` beat task (daily) cancels ACTIVE subs whose
    `current_period_end < now - 1 day`. Do NOT remove this job, do NOT make gates ignore the
    cancel, and when creating any non-Stripe (free/promo) subscription you MUST set a real
    `current_period_end` so it expires. Recurring Stripe subs are safe — their end date is
    extended by `invoice.paid` / `subscription.updated` webhooks before the grace window.
## 20. Known inconsistencies & landmines (current as of 2026-05-29)

- **`updated_at` migration drift on campaign tables (fixed 2026-05-31):** every model
  inherits `updated_at` from `Base`, but the hand-written migration that created
  `provider_campaign_invites` and `founding_access_grants` omitted that column, so any ORM
  INSERT raised `UndefinedColumnError: column "updated_at" does not exist` — which silently
  broke **all campaign creation** (the invite-row INSERT). SQLite tests use
  `Base.metadata.create_all` (always includes `updated_at`), so the drift never showed up in
  CI. Fixed by migration `u1v2w3x4y5z6` (adds `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
  to both tables). **Rule: when adding a hand-written `create_table` migration, include
  `created_at` AND `updated_at` to match `Base`; or assert model/DB parity against real
  Postgres, not just create_all.**

Things that look wrong/confusing but are intentional, or are real bugs not yet fixed.
Documented so they stop costing time. **None of these should be "fixed" by making the
live behaviour match the stale value** — the live behaviour is correct.

- **`is_closed` drift via Core/raw UPDATE (fixed 2026-05-30):** the `@validates('rfq_status')` hook that keeps `is_closed` in lockstep ONLY fires on ORM attribute assignment. `submit_rfq` sets `rfq_status` via SQLAlchemy **Core `update().values()`** (and admin repair uses raw SQL), which bypass the validator — so a stale `is_closed=True` persisted while `rfq_status` moved to `open_for_dispatch/unlock`, making an RFQ show OPEN in admin yet behave CLOSED in quote/provider gates. Fix: `submit_rfq`'s Core update now sets `is_closed=False, closed_at=None` explicitly, and a one-time reconcile (`UPDATE rfqs SET is_closed = (rfq_status IN <closed set>)`) cleared all drift. **Rule: any Core/raw write of `rfq_status` MUST also write `is_closed`.** The bulletproof end-state (not yet done) is to make `is_closed` a Postgres GENERATED column = (rfq_status IN closed-set), which removes every write path and the validator entirely.

- **Admin "Force close" (override-status) contract mismatch (fixed 2026-05-30):** the admin
  "Force close" button calls `overrideRFQStatus` which POSTed **`{ status }`**, but
  `/admin/rfqs/{id}/override-status` requires **`{ new_status, reason }`** (`reason` required,
  min 5 chars). So the cancel **422'd before touching the DB** and the RFQ stayed OPEN FOR
  UNLOCK with no visible error. Fixed the frontend to send `{ new_status, reason }`. (The other
  admin cancel path, `/terminate-dispatch`, uses a different body and worked.)
- **AuditLog field gotcha:** the `AuditLog` model's free-form column is the attribute
  **`extra_data`** (NOT `metadata` — `metadata` is reserved by SQLAlchemy declarative and is
  silently swallowed as a non-column instance attr, so `AuditLog(metadata=...)` records
  nothing and the audit is lost). Many admin endpoints still pass `metadata=` and thus don't
  persist their audit detail (functionally harmless; flagged for cleanup). Also: write
  best-effort audit logs in a SEPARATE commit AFTER the primary change is committed, with
  `await db.rollback()` on failure, so an audit error can never gate a real mutation.

- **Search limit:** live free is **5** (`FREE_SEARCH_LIMIT=5`), paid **100**; this now matches `config.py REGISTERED_SEARCH_LIMIT_PER_MONTH=5`. `ANONYMOUS_SEARCH_LIMIT_PER_MONTH=0` — anonymous cannot search (account required, enforced with a 401 in the search endpoints).
- **`OPENAI_LLM_MODEL` default differs:** `config.py` says `gpt-4o-mini`; runtime-config
  default is `moonshotai/Kimi-K2.5` (the live model). Runtime config wins.
- **Celery is dormant in production:** no worker/beat in `render.yaml`. Dispatch runs via
  Render cron + the in-process asyncio loop; emails send inline. The beat schedule also
  references a nonexistent `app.tasks.maintenance` module. Don't rely on `.delay()`.
- **In-process dispatch loop** runs ~every 5 min despite a "15 min" comment.
- **Signed-NDA-PDF S3 upload is broken:** `nda_service._s3_upload_bytes` imports
  `upload_file_bytes` from `file_service`, which doesn't exist (the real function is
  `upload_bytes_to_s3`). The error is caught and only logged, so signed PDFs silently fail
  to store. (Real bug — fix when prioritized.)
- **`create_post_acceptance_nda` still pre-fills `template_fields` and uses customer-first
  signer order** (opposite of `add_provider_to_nda`). If that path is exercised, it may hit
  the same "thanks for filling out" issue that was fixed in the provider-first path.
- **SignWell webhook is not signature-verified** (`SIGNWELL_WEBHOOK_SECRET` exists but is
  unused in the handler). Defensive polling (`_sync_nda_signatures`) compensates.
- **Internal cron endpoint is unauthenticated** (CRON_SECRET removed by design).
- **Frontend:** two near-duplicate API modules (`providerRFQ` vs `providerRfqAccess`);
  several pages use raw `fetch` and bypass the 401→refresh interceptor; auth tokens are in
  `localStorage` (httpOnly-cookie migration is tracked backlog).
- **Render free-tier Web Shell** frequently fails to attach ("instance not found"),
  especially during deploys; retry until an instance id appears. The shell is the only
  place secrets (e.g. the SignWell key) are readable for live diagnostics.

---

## 21. Maintenance rule

When you change any flow, fee, status, gate, integration, capability, or UI convention
described here:

1. Update the relevant section of this file **in the same commit** as the code change.
2. **Also update the user-facing manual `docs/help/proreadyengineer_manual.md` in the same
   commit** for any user-visible change (new capability, changed fee, new button/workflow,
   status rename, etc.). That manual renders at `/help` AND is the grounding context for the
   AI Help Assistant, so a stale manual = wrong answers to paying users and a capability the
   assistant can't help with. The manual is user-facing: it must say **ProMechDirectory**
   (never the internal codename ProReadyEngineer) and quote the live fees ($50 unlock /
   $10 NDA / $1,000 annual / $20-mo search).
3. If you change a number, update §3 / §19 here, §4 of the manual, and remove or correct the
   stale constant in §20.
4. If you fix a §20 landmine, move it out of §20 (and into the body) so the doc reflects
   reality.
5. Keep this file as the single source of truth for engineering and the manual as the single
   source of truth for users — fold new knowledge into both rather than creating parallel docs.

_Companion docs:_ `ARCHITECTURE.md` (short pointer to this file), `HANDOFF.md` /
`DEVELOPMENT_HISTORY.md` (historical), `api_contract_v1.md` (route contract, may lag),
`DEPLOYMENT_GUIDE.md` (ops). Where any of them conflicts with this file, this file wins.
