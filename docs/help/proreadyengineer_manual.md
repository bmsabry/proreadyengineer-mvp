# ProMechDirectory — Complete User Manual

> This is the source-of-truth help document for the **ProMechDirectory** platform. It is rendered at `/help` for end users and loaded into the in-app AI Help Assistant as its grounding context. Every fact here is meant to match the live product exactly. Edit this file to change what the platform — and the assistant — says about itself.
>
> Maintenance rule: whenever a feature, fee, status, workflow, gate, or button changes in the code, this manual MUST be updated in the same change. The assistant can only be as accurate as this document.

---

## 1. What ProMechDirectory is

ProMechDirectory is a B2B marketplace that connects companies that need engineering work ("customers") with engineering consulting firms ("providers"). Customers post **Requests for Quotation (RFQs)** describing an engineering problem; the platform uses AI to match each RFQ to the most relevant providers and emails them a short teaser. Providers pay to **unlock** an RFQ, optionally **sign an NDA**, then submit a competitive **quote**. The platform also offers an AI-powered searchable **directory of engineering firms**, **featured advertisement** placements for providers, and built-in **NDA management** for confidential projects.

How the platform makes money: provider per-RFQ unlock fees, an optional customer NDA handling fee, provider annual subscriptions, customer search subscriptions, and advertising. ProMechDirectory does **not** take a percentage of the project fees that customers pay providers — in the current product, project payment happens directly between the two parties, off-platform.

## 2. Accounts and roles

There are four personas:

- **Customer** — a company or individual that needs engineering work done. Posts RFQs and receives quotes.
- **Provider** — an engineering firm that performs the work. Gets matched to RFQs, unlocks them, and quotes.
- **Advertiser** — pays for featured-firm / software-provider listings (typically a provider promoting itself).
- **Admin** — internal ProMechDirectory staff who operate the platform. Not a self-serve signup.

A single login can technically hold more than one role, but the self-serve signup creates either a customer or a provider. The customer project search and RFQ submission are **customer-only**; provider accounts are blocked from them by design (a provider cannot hire other providers through the platform). If you genuinely need both sides, the cleanest approach is separate accounts.

### 2.1 What's required to create a customer account
Creating a customer account requires, and validates, all of the following:

- **Email address** (you must verify it via the link we send).
- **Full name.**
- **Company name.**
- **State / province** (used for the governing-law clause of any NDA).
- **Password.**
- **Phone number is optional.**

If any required field is missing, the sign-up is rejected. Providers register through a separate firm-lookup flow (see §6) and are not subject to this exact field set.

## 3. Glossary

- **RFQ — Request for Quotation.** A customer's description of a project: the problem, constraints, deliverables, deadline, tollgate, uploaded files, and whether an NDA is required.
- **Quote.** A provider's proposal for a specific RFQ: price (or price range), turnaround, scope, and assumptions.
- **Unlock.** A provider pays the unlock fee (or uses an annual subscription) to gain access to an RFQ so they can read it fully and quote.
- **NDA — Non-Disclosure Agreement.** A mutual confidentiality agreement. When a customer marks an RFQ "NDA required," a provider must sign the NDA before the full project description and files are revealed.
- **Match.** An AI-scored pairing between an RFQ and a provider. Matched providers receive a teaser email.
- **Dispatch.** The process of matching an RFQ to providers and sending teaser emails in batches.
- **Teaser.** The short, redacted preview of an RFQ that a matched provider sees before unlocking.
- **Tollgate (TG0–TG6).** The engineering maturity phase of a project. Options when submitting an RFQ:
  - **TG0** — Idea Generation
  - **TG1** — Basic Engineering
  - **TG2** — Concept Validation
  - **TG3** — Intermediate Analysis
  - **TG4** — Full Scale Modeling
  - **TG5** — Pre-Production Testing
  - **TG6** — Full System Testing
- **Firm Directory.** The public, searchable, AI-ranked catalog of engineering providers.
- **Subscription.** A recurring paid plan (provider annual, or customer monthly search).
- **Activity Summary.** The dashboard panel (both customer and provider) where your stats and your "action required" notifications appear. This is where the platform tells you what needs your attention.

## 4. Pricing and fees (exact, current)

All charges are processed through Stripe.

### 4.1 Provider charges
- **RFQ unlock fee — $50, paid by the provider, per RFQ.** Pays to read the full RFQ and submit a quote. **Free** for providers with an active annual subscription.
- **Provider Annual subscription — $1,000 per year.** Grants **unlimited free RFQ unlocks** while active, plus direct visibility of the customer's contact details on RFQs you've unlocked (see §7.6), plus full profile editing. This is the best value for active providers.
- **Provider full-profile-edit unlock — one-time fee** to unlock editing of all profile fields (included free with the annual subscription).
- **Advertisement — a recurring subscription** for a featured slot (featured-firm / software-provider listings). Cancelling stops auto-renewal; the ad stays visible through the end of the paid period.

### 4.2 Customer charges
- **NDA handling fee — $10, paid by the customer**, charged when the customer marks an RFQ "NDA required." Charged once per such RFQ. **Customers with an active Search subscription get 5 free NDA-required RFQs each calendar month** — the $10 fee is waived until those 5 credits are used, then it applies normally. The allowance resets on the 1st of each month.
- **Customer Search subscription — $50 per month, or $500 per year.** Raises the monthly search quota from **5** searches to **100**, and includes **5 free NDA-required RFQs per month** (see below). The monthly and annual plans grant identical features — annual just bills yearly and saves $100. This is the only customer subscription.

### 4.3 Search quota
- **An account is required to search at all — anonymous visitors cannot search.**
- **Free registered accounts: 5 searches per month.**
- **Search subscribers: 100 searches per month.**
- The counter resets monthly.

### 4.4 Cancellation, refunds, and what's NOT charged
- **Cancellation** uses Stripe's "cancel at period end": you keep access until the end of the current billing period, then it stops. There are no partial-period refunds.
- **Refunds** are reviewed case by case — contact support with your account email and the payment date.
- ProMechDirectory does **not** escrow or take a cut of project fees. The customer pays the provider directly, off-platform, in the current product.

## 5. Customer guide

### 5.1 Create your account and verify email
Sign up as a **Customer**, providing your email, full name, company name, state, and password (phone optional). Open the verification email and click the link. If it doesn't arrive, check spam and request a resend from the login page. Then log in — you land on the customer dashboard.

### 5.2 Search the firm directory
From the landing page or the top navigation, type a natural-language description of what you need — for example, "FEA simulation for a stamped sheet-metal bracket, aerospace, 4-week turnaround." The system returns AI-ranked providers, each with a short explanation of why it matched. Click any firm to view its public profile. You must be signed in to search — anonymous visitors are prompted to create an account. Search consumes your monthly quota (5 on a free account, 100 with a subscription). Note: provider accounts cannot use this search.

### 5.3 Submit an RFQ
From the customer dashboard, start a new RFQ (the **Submit New RFQ** action, at `/customer/rfq/new`). Provide:

- **Title** — short and descriptive.
- **Description** — the problem, constraints, and deliverables.
- **Tollgate (TG0–TG6)** — the engineering maturity phase.
- **Deadline** — when you need results.
- **NDA required?** — check this if providers must sign an NDA before seeing full details. If you check it, you pay the **$10** NDA handling fee, and you can optionally provide your own NDA template (otherwise a standard mutual NDA is used).
- **Files** — attach supporting documents. **Up to 5 files, 25 MB each.** Supported types include PDF, DOC/DOCX, TXT, DWG, DXF, STEP (STP), IGES (IGS), SolidWorks (SLDPRT, SLDASM), CATIA (CATPART, CATPRODUCT), STL, Parasolid (X_T, X_B), and NX (PRT, ASM).

On submission the platform immediately runs AI matching and begins dispatching teaser emails to matched providers in batches. Providers only see the full description and files after they unlock (and, if required, sign the NDA).

### 5.4 Track your RFQs
The customer portal organizes your RFQs into views: **All**, **Active** (open for quoting), **Quoted** (received at least one quote), **Accepted** (you accepted a quote), and **Cancelled**. There's also a per-RFQ **tracking** view. Your dashboard's **Activity Summary** highlights what needs you — for example, "you have N new quotes to review" appears when new quotes arrive and clears once you open that RFQ.

### 5.5 Review and accept a quote
Open an RFQ to see its quotes side by side — price, turnaround, scope, and assumptions. The received quote is shown prominently. When you accept one (the **Accept** action), the provider is notified by email, the provider gains visibility of your contact details, and the RFQ moves to "provider selected." Up to 5 quotes are collected per RFQ; after that the RFQ reaches its quote limit and closes to new quotes.

### 5.6 NDAs from the customer side
If you required an NDA, here's your part: you pay the $10 fee up front — unless you have a Search subscription and free NDA credits remaining this month, in which case it's waived (5 free per month) — and this does **not** delay providers from being matched — dispatch proceeds normally). When a provider signs the NDA, you are asked to **countersign** — you'll get an email from our e-signature provider (SignWell) AND an amber "Action required: NDA awaiting your signature" note in your dashboard's Activity Summary. The agreement is a single, mutual NDA; the full project details are unlocked to that provider only once **both** of you have signed.

## 6. Provider guide

### 6.1 Register: claim or add your firm
Providers register through a firm-lookup flow:

- **Claim an existing firm.** Search for your firm by name; if it's already in our directory, select it and your account links to it directly.
- **Add a new firm.** If it isn't listed, create it (on signup or later from the provider dashboard's add-firm flow at `/provider/add-firm`).

You may need to verify ownership of the firm (via a company-domain email or admin approval) before you have full control.

### 6.2 Complete your profile
From the provider dashboard's **Profile** area (`/provider/profile`; full editing at `/provider/profile/full-edit`), fill in your firm's details. The more specific and complete your profile, the more — and more relevant — RFQs reach you. Be concrete and technical, not vague:

- **Capabilities** — the engineering services you actually perform (e.g. "FEA structural analysis", "HVAC load calculations", "pressure-vessel design to ASME VIII").
- **Specialties / industries served** — e.g. "oil & gas", "data-center cooling", "medical devices".
- **Software & tools, equipment, certifications** — SolidWorks, ANSYS, in-house machining, ISO 9001, ASME stamps, PE licensure, etc.
- **Notable Projects** — the most important. For each past project, write one clear sentence: what you did, the method/approach, and the outcome. Add several, specific and factual. Your project history is used to match you to work and is not shown publicly.

Editing all profile fields requires the full-profile-edit unlock (a one-time fee, or free with the annual / founding membership).

**Let the AI assistant help.** Open the chat assistant and ask it to help improve your profile — it will coach you on what to add and can draft your Notable Projects from a few details you give it. You can also attach a capability statement, brochure, line card, or past-project write-ups (the paperclip in the chat), and the assistant will extract the details and add them to your profile for you to review. It merges with what you already have and never removes anything (saving requires the full-profile-edit unlock or annual / founding membership).

### 6.3 Receive and review RFQs
When the AI matches your firm to an RFQ, you receive a **teaser email** and the RFQ appears in your provider dashboard (`/provider/rfqs`). The teaser shows enough to decide whether to pursue it — title, short description, tollgate, deadline, and whether an NDA is required — but not the customer's identity, full details, or files.

### 6.4 Unlock an RFQ
Open the RFQ and **Unlock** it. If you hold an active **annual subscription**, unlocking is free and immediate. Otherwise you pay the **$50** unlock fee through Stripe. Unlocking grants access to the RFQ; for NDA RFQs, the full description and files remain gated on the NDA (next step).

### 6.5 Sign the NDA (only for NDA-required RFQs)
ProMechDirectory uses a **provider-first, mutual, single-document** NDA:

1. You click **Sign NDA**. (This call can take a few seconds while the document is prepared — wait for the confirmation rather than clicking again.)
2. One mutual NDA is created with both you and the customer as signers. You sign first, via the link our e-signature provider (SignWell) emails you.
3. The customer is then automatically asked to countersign (by email and in their dashboard).
4. Once **both** parties have signed, the **full project description and files unlock** for you, and you can submit a quote.

Until both signatures are in, you only see the redacted teaser/preview. There is no "customer signs first" requirement — you always sign first to read.

### 6.6 Submit a quote
With full access, submit your quote: price or price range (USD), turnaround, scope (what's in and out), and assumptions; you can optionally upload a quote document, and an AI extractor can pre-fill the form from it. The customer sees all quotes together. You're notified when your quote is accepted or declined. When the customer **accepts** your quote, their contact details are revealed to you so you can coordinate the work directly.

### 6.7 Annual subscription benefits (the customer-contact perk)
Beyond free unlocks, an active **Provider Annual** subscription reveals the customer's **direct contact details** — name, company, email, **phone**, and state — on any RFQ you've unlocked, shown as a "Customer Contact (Annual member)" card. This lets you reach out and win the deal directly. It respects NDAs: on an NDA-required RFQ the contact is revealed only after the mutual NDA is fully signed (it never bypasses an NDA the customer paid for). Non-subscribers do not see this.

### 6.8 Advertise
From the provider dashboard's **Advertise** area, choose a featured slot. Featured listings appear prominently in relevant results. It's a recurring subscription; cancel any time and the placement runs through the end of the paid period.

### 6.9 Upgrade
The provider **Upgrade** page (`/provider/upgrade`) compares the plans: the **Annual Professional** plan ($1,000/yr, recommended — free unlocks, customer contact on every RFQ, unlimited profile edits), a one-time **Profile Edit** unlock, and **Pay Per RFQ** ($50 per unlock, no commitment).

### 6.10 Provider restrictions
Provider accounts **cannot** use the customer project search or submit RFQs — those are customer-only. To browse the directory, use the public provider pages.

## 7. RFQ lifecycle and statuses

An RFQ moves through these stages (you'll see status labels reflecting them):

- **Draft** — being created, not yet submitted.
- **Submitted** — submitted by the customer; AI matching runs.
- **(NDA RFQs, transitional)** — bookkeeping states around the customer's NDA fee. These never block matching; dispatch proceeds as soon as the $10 fee is recorded.
- **Open for dispatch / Dispatching** — matched providers are being emailed in batches.
- **Open for unlock** — providers can unlock and quote.
- **Quote limit reached** — 5 quotes received; closed to new quotes.
- **Provider selected** — the customer accepted a quote.
- **Closed (no selection)** / **Cancelled** — closed without a selection, or withdrawn by the customer.

Unlocking an RFQ never closes it (unlocks are unlimited). An RFQ closes only when it reaches the quote limit, the customer selects a provider, or it's cancelled.

## 8. NDA workflow (detail)

- It is **one mutual NDA document** per (RFQ, provider), with both parties as signers.
- It is **provider-first**: the provider signs to read; the customer then countersigns.
- The customer pays the **$10** NDA handling fee when they require the NDA; this never delays provider matching/dispatch.
- Both parties are always notified when it's their turn — by email (SignWell) **and** in the in-app Activity Summary.
- Full project details + files unlock to the provider only after **both** signatures are recorded.
- Action prompts only appear for **open** RFQs — a half-signed NDA on a cancelled or already-selected RFQ won't ask anyone to keep signing.

## 9. Subscriptions and billing management

- **Provider Annual ($1,000/yr):** unlimited free unlocks, customer-contact visibility, full profile editing.
- **Customer Search ($50/mo or $500/yr):** raises search quota 5 → 100 and includes 5 free NDA RFQs/month. Monthly or annual (same features).
- **Advertisement:** recurring featured placement.
- **Provider full-profile-edit:** one-time unlock (free with annual).
- Manage or cancel from your profile's billing area / the provider dashboard's subscriptions area. Cancellation takes effect at period end; no partial refunds.

## 10. Notifications and where to find what needs you

Your dashboard's **Activity Summary** panel is the single place for "action required" items, and it updates live (on load, every ~20 seconds, and when you refocus the tab) — no manual reload needed. Examples:

- **Customer:** "N new quotes to review" (clears when you open the RFQ); "NDA awaiting your signature" (when a provider has signed and you must countersign).
- **Provider:** "Accepted RFQ — contact the customer"; "Sign the NDA to read this RFQ" while an NDA is pending on an open RFQ.

Email notifications (via Resend / SignWell) accompany the key events: RFQ teaser, quote received, quote accepted, NDA signing requests, welcome, password reset, and email verification.

## 11. The AI Help Assistant (in-app chatbot)

The chat widget (lower-right) is the AI Help Assistant. It answers questions about the platform itself — how to submit an RFQ, how unlock fees work, what a tollgate means, how to cancel a subscription, what to do next, and so on — grounded on this manual.

- **Who can use it:** users with an active paid subscription (Customer Search, Provider Annual, or provider profile subscription) plus admins. Advertisement-only subscriptions do not grant access. Free and anonymous visitors see a preview and a prompt to subscribe.
- **Scope:** the ProMechDirectory platform AND general mechanical-engineering questions (design, materials, manufacturing, FEA/CFD, thermodynamics, standards, CAD, etc.). It politely declines topics unrelated to the platform or engineering, and never gives legal/financial/medical advice or safety-critical engineering sign-off — for anything code-stamped or safety-critical it points you to a qualified licensed engineer.
- **What it won't do:** take consequential actions on your behalf (it will point you to the exact page and button), discuss other users' data, or give professional advice.
- **Document/image analysis:** for questions that require reading a document or image, the assistant routes the request to a more capable model behind the scenes.
- **Do the work from your files:** click the paperclip to upload a document (PDF/DOCX/TXT) and ask the assistant to create an RFQ from it (customers) or draft and submit a quote from it (providers). It attaches your file to the right place. It creates RFQs as a draft for you to submit, and never pays a fee or signs an NDA for you.
- **Usage limits:** there is a per-user daily message limit and a monthly usage budget; if you hit a limit, it resets (daily, or monthly on the 1st), and you can always read this manual at `/help`.

## 12. Account and security

- **Email verification** is required before full use.
- **Change/reset password:** use **Forgot password** on the login page; enter your email and follow the link.
- **Account lockout:** repeated failed logins temporarily lock the account as a security measure.
- **Delete account:** request deletion via the Contact page; data is removed within 30 days of the request.
- Sessions use short-lived access tokens with automatic refresh.

## 13. For administrators (staff only)

Admins operate the platform from the `/admin` area: dashboard, RFQs, provider claims, providers, payments, webhooks, campaigns, support tickets (with AI-classified triage), ads, users, data extraction, debugging, and settings. Admin → Settings configures the four LLM backends, payment/email/storage/e-signature credentials, and RFQ batch parameters live (no redeploy needed). Admin → Debugging exposes per-LLM connectivity tests (including the chatbot LLM) and webhook/email health.

## 14. FAQ

**Can I be both a customer and a provider?** The self-serve flows create one side; the customer search and RFQ submission are customer-only and providers are blocked from them. Use separate accounts if you truly need both.

**What does it cost a provider to see an RFQ?** $50 per RFQ unlock — or $0 with an active annual subscription. If the customer required an NDA, you also sign it (the customer, not you, pays the $10 NDA handling fee).

**What files can I attach to an RFQ?** PDF, DOC, DOCX, TXT, DWG, DXF, STEP (STP), IGES (IGS), SLDPRT, SLDASM, CATPART, CATPRODUCT, STL, X_T, X_B, PRT, ASM. Up to 5 files, 25 MB each.

**How many quotes can an RFQ get?** Up to 5; then it closes to new quotes.

**How long does an RFQ stay open?** Until you accept a quote or cancel it.

**I cancelled my subscription — why do I still have access?** Cancellation is effective at the end of the current billing period; you keep access until then.

**Does ProMechDirectory take a cut of the project fee?** No. You pay the provider directly, off-platform. We earn from unlock fees, the NDA fee, subscriptions, and ads.

**Why can't I (a provider) use the search bar or post an RFQ?** Those are customer-only by design — providers can't hire other providers through the platform.

**How do I change my password / delete my account?** Password: "Forgot password" on the login page. Deletion: request via the Contact page (completed within 30 days).

## 15. Troubleshooting

- **"This email is already registered."** You already have an account on this email; log in, or use a different email for a different role.
- **"Provider accounts cannot submit RFQs or search for firms."** You're logged in as a provider; this is intentional.
- **Payment went through but my subscription/unlock isn't active yet.** Payments confirm via webhook asynchronously — wait a minute and reload. If it's still not active after ~10 minutes, contact support.
- **My ad is still showing after I cancelled.** Correct — cancellation stops renewal; the placement runs through the end of the paid period.
- **I didn't get my verification or NDA email.** Check spam, request a resend, and allowlist our sender domain (`@promechdirectory.com`). Corporate mail filters sometimes hold these.
- **Sign NDA seems to hang.** It can take a few seconds to prepare the document — wait for the confirmation; don't click repeatedly.

## 15b. Payments — full step-by-step (the assistant can walk you through every step)

The AI Assistant can guide you through these end to end, but for your security **you click the
final payment button yourself** — the assistant never enters card details or completes a charge.

**Provider — paying the $50 RFQ unlock fee:**
1. Open the RFQ from your dashboard (`/provider/rfqs`) or the teaser email and click into it.
2. Click **Unlock**. If you have an active **annual** subscription, unlocking is free and instant — no payment screen.
3. Otherwise you're taken to Stripe-hosted Checkout. Enter your card and confirm the $50 payment.
4. After Stripe confirms (a few seconds, processed by webhook), return to the RFQ — full details and the Submit Quote button are now available.
5. If access doesn't appear within ~1 minute, reload; payments confirm asynchronously.

**Provider — Annual ($1,000/yr) or other plans:** go to **Upgrade** (`/provider/upgrade`), pick a plan, and complete Stripe Checkout. Manage or cancel later from the provider dashboard's billing area.

**Customer — Search subscription ($50/mo or $500/yr):** go to **Billing** (`/billing`), choose monthly or annual, and complete Stripe Checkout. Cancellation is effective at period end (no partial refund); manage it from your profile's billing area.

**Customer — the $10 NDA handling fee:** charged automatically when you mark an RFQ "NDA required" — UNLESS you have a Search subscription with free NDA credits left this month (5/month), in which case it's waived. If charged, you complete it via Stripe Checkout during RFQ submission.

**General payment notes the assistant can explain:** all payments use Stripe (PCI-compliant); we never store your card; confirmations arrive by webhook so allow up to a minute; receipts come from Stripe by email; for billing problems use the Contact page with the payment date and Stripe receipt number.

## 15c. NDA process — full step-by-step (the assistant can guide; you sign yourself)

The NDA is a single **mutual** agreement, signed **provider-first**, via our e-signature provider (SignWell). For your legal protection, **you click "Sign" yourself** — the assistant explains every step but never signs on your behalf.

**Customer side:**
1. When submitting an RFQ, check **NDA required** (optionally upload your own NDA template; otherwise a standard mutual NDA is used). Pay/clear the $10 handling fee.
2. Your RFQ dispatches to matched providers normally — the NDA never delays matching.
3. When a provider signs first, you're notified to **countersign**: by email from SignWell AND an amber "Action required: NDA awaiting your signature" note in your dashboard Activity Summary.
4. Open the SignWell email (or the dashboard prompt), review, and sign. Once both parties have signed, the provider gets full access and can quote.

**Provider side:**
1. After unlocking an NDA-required RFQ, click **Sign NDA** on the RFQ page (`/provider/rfq/[id]`). Preparing the document takes a few seconds — wait for the confirmation; don't click repeatedly.
2. SignWell emails you a signing link; open it and sign.
3. The customer is then asked to countersign. Once **both** signatures are recorded, the full project description and files unlock for you and you can submit a quote.
4. Until both have signed, you see only the redacted teaser.

**NDA notes the assistant can explain:** it's one document with both parties as signers; provider signs first to read; full access requires both signatures; signing requests come by email and in-app; a half-signed NDA on a cancelled/closed RFQ won't keep asking you to sign; if a signing email doesn't arrive, check spam and allowlist the sender, or use the in-app prompt.

## 16. Contacting support

Use the **Contact** page (linked in the footer). Include your account email, a short description, and screenshots if possible. For billing issues, add the payment date and the Stripe receipt number if you have it.

---

_This manual is the source of truth for the AI Help Assistant — edit here to update what the assistant knows. Keep it in lockstep with the product: any change to a feature, fee, status, workflow, or gate must be reflected here in the same change._
