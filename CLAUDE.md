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
   are $20 unlock / $10 NDA / $1,000 provider-annual; search quota 10 free / 100 paid).
2. **Trust the live behaviour, not stale constants/comments.** `SYSTEM_SPEC.md` §20 lists
   the known inconsistencies (e.g. `RFQ_UNLOCK_PRICE=5000` is stale; live unlock is $20).
3. **Keep the spec in sync:** when you change a flow, fee, status, gate, integration, or UI
   convention, update `SYSTEM_SPEC.md` in the **same commit**.
4. **Verify against code before relying on a number** for anything money-, legal-, or
   signature-related — confirm the specific lines.
5. **Deploy:** push to `main` → Render auto-deploys api + web. CI runs `pytest tests/unit`.

Where `SYSTEM_SPEC.md` conflicts with `ARCHITECTURE.md`, `HANDOFF.md`,
`DEVELOPMENT_HISTORY.md`, or `api_contract_v1.md`, **`SYSTEM_SPEC.md` wins.**
