# Working in this repo — read first

**Before changing anything, read [`SYSTEM_SPEC.md`](SYSTEM_SPEC.md).** It is the single
source of truth for how this application works: the RFQ lifecycle, the provider-first
mutual NDA "sign-to-read" flow, fees, access gating, payments, the AI/search stack,
integrations (SignWell, Stripe, Resend, S3), config/secrets, deploy, and the UI
conventions.

Hard rules:

1. **Do not violate the invariants in `SYSTEM_SPEC.md` §19** — they are business rules,
   not preferences (e.g. dispatch never waits on a signature; `unlock_status=="unlocked"`
   is the only access gate; NDA is provider-first/mutual/one-model; NDA notifications use
   both email + the in-app Activity Summary pattern; SignWell template id is the API UUID;
   never set document-level `embedded_signing`; don't pre-fill NDA signer fields; live fees
   are $50 provider unlock / $10 customer NDA / $1,000 provider-annual; search quota 10 free / 100 paid).
2. **Trust the live behaviour, not stale constants/comments.** `SYSTEM_SPEC.md` §20 lists
   the known inconsistencies (e.g. `REGISTERED_SEARCH_LIMIT_PER_MONTH=5` in `config.py` is unused; the live search quota is 10 free / 100 paid).
3. **Keep the spec AND the user manual in sync:** when you change a flow, fee, status,
   gate, integration, capability, button, or UI convention, in the **same commit** update
   BOTH `SYSTEM_SPEC.md` (engineering source of truth) AND
   `docs/help/proreadyengineer_manual.md` (the user-facing manual rendered at `/help` and
   used as the grounding context for the AI Help Assistant). A capability the manual omits
   is one the assistant can't help users with; a stale fee/flow in the manual becomes a
   wrong answer shown to paying users. The manual is user-facing — it must say
   **ProMechDirectory** (never the internal codename ProReadyEngineer). Treat "did I update
   the manual?" as a required checklist item for every user-visible change.
4. **Verify against code before relying on a number** for anything money-, legal-, or
   signature-related — confirm the specific lines.
5. **Deploy:** push to `main` → Render auto-deploys api + web. CI runs `pytest tests/unit`.

Where `SYSTEM_SPEC.md` conflicts with `ARCHITECTURE.md`, `HANDOFF.md`,
`DEVELOPMENT_HISTORY.md`, or `api_contract_v1.md`, **`SYSTEM_SPEC.md` wins.**
