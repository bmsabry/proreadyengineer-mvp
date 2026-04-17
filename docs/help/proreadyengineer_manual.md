# ProReadyEngineer - User Manual

> This is the source-of-truth help document for the ProReadyEngineer platform. It is rendered at /help for end users and loaded into the in-app AI Help Assistant as its grounding context. Edit this file to change what the platform says about itself.

## 1. What ProReadyEngineer is

ProReadyEngineer is a B2B marketplace that connects companies needing engineering services ("customers") with engineering consulting firms ("providers"). Customers post Requests for Quotation (RFQs) that describe an engineering problem, and providers unlock those RFQs to submit competitive quotes. The site also offers a searchable directory of engineering firms, paid advertisement slots for providers, and NDA management for confidential projects.

There are exactly **two kinds of accounts**:

- **Customer** - a company (or individual) that needs engineering work done.
- **Provider** - an engineering firm that performs work for customers.

The same email address cannot hold both a customer and a provider account. If you need both roles, use two separate emails.

There are also administrator accounts (internal ProReadyEngineer staff) and advertiser records (providers who buy advertisement slots) - those are not self-serve signup flows.

## 2. Glossary

- **RFQ** - Request for Quotation. A customer's description of a project, uploaded files, deadline, and preferences.
- **Quote** - a provider's price/timeline proposal for a specific RFQ.
- **Unlock** - a provider pays a fee to see the full details of an RFQ (contact info, uploaded files) so they can quote on it.
- **NDA** - Non-Disclosure Agreement. Customers can require providers to sign an NDA before unlocking an RFQ.
- **Tollgate (TG0-TG6)** - engineering development phases used to tag the maturity of a project. Options in RFQ submission:
  - TG0: Idea Generation
  - TG1: Basic Engineering
  - TG2: Concept Validation
  - TG3: Intermediate Analysis
  - TG4: Full Scale Modeling
  - TG5: Pre-Production Testing
  - TG6: Full System Testing
- **Firm Directory** - the searchable catalog of engineering providers, with ranking.
- **Subscription** - a recurring paid plan. Both customers and providers can subscribe.

## 3. Subscriptions and pricing

There are **two subscription audiences** (customer, provider), each with tiers, and both billing monthly or annually.

### Customer subscriptions
- **Search Tier 1** - $20/month. Basic natural-language search of the firm directory, limited query volume.
- **Search Tier 2** - higher monthly price. Larger query volume and premium ranking features.

### Provider subscriptions
- **Provider Profile (monthly)** - keeps your firm listed in the directory and allows quote submission.
- **Provider Annual ($1,000/yr)** - the "Annual Professional" plan. Everything in monthly plus a discount and year-long commitment.

### One-off payments (not subscriptions)
- **RFQ Unlock fee** - providers pay per RFQ to see full details and submit a quote.
- **NDA fee** - when a customer requires an NDA, the provider pays a small signing fee before unlocking.
- **Advertisement slot** - $50/month subscription for a featured slot. Cancelling stops auto-renewal; the ad remains visible until the last paid month ends.

### Cancelling a subscription
Go to your profile -> "Manage Billing" or the Provider Dashboard -> "Subscriptions." Click **Cancel** next to the plan you want to stop. We use Stripe's "cancel at period end" semantics: you keep access until the end of the current billing period, then the subscription stops. We do not issue partial-month refunds.

### Refunds
Refund requests are reviewed case by case. Contact support via the contact page; include your email and the payment date.

## 4. Customer walkthrough

### 4.1 Creating a customer account
1. Go to the homepage and click **Sign Up** (top right).
2. Choose **Customer** as the account type.
3. Enter your email, password, company name. Verify the email from the link we send.
4. Log in.

### 4.2 Searching for engineering firms
From the landing page or the top nav, enter a natural-language description of what you need: "FEA simulation for a stamped metal bracket, aerospace, SLA 4 weeks." The system returns ranked providers with short summaries of why each one matches. Click a firm to see its public profile.

**Note:** provider accounts cannot use the project search - it is designed for customers hiring firms. If you are a provider and want to see the directory, browse via the public /providers pages.

### 4.3 Submitting an RFQ
1. From the customer dashboard, click **Submit New RFQ** (or go to /customer/rfq/new).
2. Fill in:
   - **Title** - short, descriptive.
   - **Description** - the problem, constraints, deliverables.
   - **Tollgate (TG0-TG6)** - the phase of engineering maturity.
   - **Deadline** - when you need results.
   - **NDA required?** - check if the work requires an NDA before unlock.
3. Attach supporting files (PDF, DOCX, DWG, STEP, IGES, STL, and others). Max 5 files, 25 MB each.
4. Submit. The RFQ becomes visible to providers immediately (as a summary); full details are gated behind unlock + NDA.

### 4.4 Tracking your RFQ
From the customer dashboard you can view:
- **All RFQs** - every RFQ you've posted.
- **Active** - RFQs open for quoting.
- **Quoted** - RFQs that have received at least one quote.
- **Accepted** - RFQs where you accepted a quote.
- **Cancelled** - RFQs you withdrew.

Click any RFQ to see the quotes, shortlist providers, and accept a quote.

### 4.5 Accepting a quote
On an RFQ's detail page, review each quote (price, timeline, scope notes). Click **Accept** on the one you want. The provider is notified by email. Contact details are exchanged. Payment between you and the provider is handled off-platform (we do not escrow project fees in the MVP).

### 4.6 NDAs
If you marked "NDA required," providers must sign the NDA (via SignWell) and pay the NDA fee before they can unlock your RFQ. You can upload your own NDA template in the RFQ form; otherwise we use a standard mutual NDA.

## 5. Provider walkthrough

### 5.1 Claiming or creating a firm profile
Two paths:

- **Claim an existing firm.** On signup, search for your firm by name. If we already index it, pick it from the list - the account is linked to that firm directly and you skip manual entry.
- **Create a new firm.** If your firm isn't in the directory, fill out the new-firm form on signup or later via Provider Dashboard -> **Add Firm**.

After signup, you may still need to verify ownership (email from the firm's domain or admin approval).

### 5.2 Completing your profile
Go to Provider Dashboard -> **Profile**. Fill in:
- Services offered
- Industries served
- Certifications
- Portfolio / case studies
- Team size and locations
- Contact email

A complete profile ranks higher in customer searches.

### 5.3 Finding RFQs
Provider Dashboard -> **All RFQs** shows every visible RFQ. You see:
- Title, short description
- Tollgate, industry tags
- Deadline
- Whether the customer requires an NDA

### 5.4 Unlocking an RFQ
1. Open the RFQ summary.
2. Click **Unlock**. If an NDA is required, you'll be taken to the NDA signing page (SignWell); sign + pay the NDA fee, then return.
3. Pay the unlock fee. Full details (customer contact, files) become visible to you.
4. Click **Submit Quote** on the detail page.

### 5.5 Submitting a quote
Quote form fields:
- **Price** - fixed amount in USD.
- **Timeline** - delivery window.
- **Scope** - what's included and what isn't.
- **Assumptions** - anything the price depends on.

The customer sees all quotes side by side. You're notified by email when your quote is accepted or declined.

### 5.6 Advertisements
Provider Dashboard -> **Advertise**. Choose a slot (categories and locations available). Pay $50/month. The slot is featured at the top of matching search results. Cancel any time; the ad remains until the last paid month ends.

### 5.7 Restrictions on provider accounts
Provider accounts **cannot**:
- Use the customer project search (/search).
- Submit RFQs (the customer-side form).

If you also need to hire engineering firms as a customer, create a separate customer account with a different email address.

## 6. Admin overview (staff only)

Administrators can:
- Approve provider claims and firm-verification requests.
- Review support tickets, including AI-classified triage suggestions.
- Inspect payments, refunds, and subscription statuses.
- Manage ad slots.
- Configure the three LLM backends (see below).
- View webhook logs for Stripe, PayPal, SignWell, Resend.

### The three LLMs
- **LLM1** - customer search / query generation. Configured via OPENAI_* env vars or Admin Settings.
- **LLM2** - firm ranking. Uses its own key/model; falls back to LLM1.
- **LLM3** - Document Collapse LLM (DOC_LLM_*). Used for support ticket classification, quote-document summarization, website extraction for firm profiles, and the in-app AI Help Assistant.

Admins can swap any LLM's provider, model, or key without a redeploy via **Admin -> Settings**.

## 7. The AI Help Assistant (in-app chatbot)

The chat widget in the lower-right opens the AI Help Assistant. It answers questions about the platform itself: how to submit an RFQ, how unlock fees work, what a tollgate means, how to cancel a subscription, and so on. It is grounded on this manual only.

**Who can use it:** users with an active paid subscription (Customer Search Tier 1/2, Provider Profile monthly, or Provider Annual). Advertisement-only subscriptions do not grant access. Free and anonymous visitors see a preview and a prompt to subscribe.

**What it won't do:**
- Give legal, financial, medical, or engineering advice.
- Take actions for you (submit, cancel, or pay). It will tell you which page to go to.
- Discuss other users' data.
- Generate content unrelated to the platform.

**Limits:** subscribers get 50 messages per day. If you hit the limit, try again tomorrow or browse the manual at /help.

## 8. FAQ

**Can I have both a customer and a provider account?**
Yes, but they must use different email addresses. The platform refuses to create two accounts on the same email with conflicting roles.

**What files can I attach to an RFQ?**
PDF, DOCX, DOC, TXT, DWG, DXF, STEP (STP), IGES (IGS), SolidWorks (SLDPRT, SLDASM), CATIA (CATPART, CATPRODUCT), STL, Parasolid (X_T, X_B), NX (PRT, ASM). Max 5 files, 25 MB each.

**How long does an RFQ stay open?**
Until you mark it accepted or cancelled. If there's no activity for 90 days, we email you to ask whether to keep it open.

**How much does it cost a provider to unlock an RFQ?**
The unlock fee is shown on each RFQ before you pay. NDA fees are separate and only apply when the customer requires an NDA.

**I cancelled my provider subscription - why can I still see my firm in the directory?**
You have access until the end of the current billing period. After that, your profile is delisted (you can re-subscribe to relist it).

**How do I change my password?**
Log out, click **Forgot password**, enter your email, follow the link.

**How do I delete my account?**
Email support from the contact page. We delete account data within 30 days of request.

**Does ProReadyEngineer take a cut of project payments?**
Not in the MVP. Project fees are paid directly by the customer to the provider off-platform. We make money from subscriptions, unlock fees, NDA fees, and ads.

## 9. Troubleshooting

**"This email is already registered as a provider account."** - You already have a provider account on this email. Use a different email to make a customer account, or log in with your provider credentials.

**"Provider accounts cannot submit RFQs or search for firms."** - You're logged in as a provider. Log out and use a customer account, or create one under a different email.

**My payment went through but my subscription isn't active.** - Stripe/PayPal webhooks are processed asynchronously; wait a minute and reload. If still inactive after 10 minutes, contact support.

**My ad is still showing after I cancelled.** - Correct behavior: cancellation stops auto-renewal; the ad runs through the end of the current billing month.

**I didn't get my verification email.** - Check spam, then request a resend from the login page. Corporate mail servers sometimes hold our emails; allowlist noreply@proreadyengineer.com.

**I'm a provider and I can't use the search bar.** - Intentional. Providers are blocked from hiring other providers via the platform.

## 10. Contacting support

Email support via the **Contact** page (link in the footer). Include:
- Your account email
- A short description
- Screenshots if possible

For billing issues, include the payment date and Stripe/PayPal receipt number if you have one.

---

_Last updated: 2026-04-17. This manual is the source of truth for the AI Help Assistant - edit here to update what the assistant knows._
