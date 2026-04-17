/**
 * Central registry of short static help texts shown as tooltips/popovers
 * next to major buttons and form fields across the app.
 *
 * Keep copy short (one or two sentences). For anything longer, point the
 * user to the /help page via `learnMore`.
 *
 * Convention: keys are `<area>.<element>` in kebab-case.
 */

export type HelpEntry = {
  title: string;
  body: string;
  learnMore?: string; // path or anchor on /help
};

export const HELP: Record<string, HelpEntry> = {
  // -------- Top nav / global ------------------------------------------------
  "nav.help": {
    title: "Help & AI Assistant",
    body: "Browse the full manual and chat with the AI Help Assistant (subscribers only).",
    learnMore: "/help",
  },

  // -------- Customer search -------------------------------------------------
  "search.query": {
    title: "Natural-language project search",
    body:
      "Describe your engineering need in plain English — e.g. \"FEA for a stamped bracket, aerospace, 4 weeks\". We rank matching firms for you.",
    learnMore: "/help#4-2-searching-for-engineering-firms",
  },
  "search.upload": {
    title: "Upload RFQ instead",
    body:
      "Have a spec doc already? Upload it and we'll draft an RFQ you can edit before posting.",
    learnMore: "/help#4-3-submitting-an-rfq",
  },

  // -------- RFQ submission --------------------------------------------------
  "rfq.title": {
    title: "Short RFQ title",
    body: "One line that summarises the project. Providers see this first.",
  },
  "rfq.description": {
    title: "Full description",
    body:
      "Problem statement, constraints, deliverables and success criteria. The clearer you are, the better the quotes.",
  },
  "rfq.tollgate": {
    title: "Engineering maturity (tollgate)",
    body:
      "TG0 is idea stage, TG6 is full system testing. Providers use this to gauge effort and team fit.",
    learnMore: "/help#2-glossary",
  },
  "rfq.deadline": {
    title: "When do you need results?",
    body: "Hard date or 'ASAP' — providers use this to decide whether they can bid.",
  },
  "rfq.nda": {
    title: "Require an NDA?",
    body:
      "If ticked, providers must sign your NDA (or our mutual default) and pay the NDA fee before unlocking the full RFQ.",
    learnMore: "/help#4-6-ndas",
  },
  "rfq.files": {
    title: "Supporting files",
    body:
      "Up to 5 files, 25 MB each. PDF, DOCX, DWG, STEP, IGES, STL and common CAD formats are accepted.",
  },
  "rfq.submit": {
    title: "Submit RFQ",
    body: "Posts the RFQ. A summary becomes visible to providers; full details are gated behind unlock/NDA.",
  },

  // -------- Provider dashboard ---------------------------------------------
  "provider.rfqs": {
    title: "All RFQs",
    body:
      "Every RFQ currently open. Click one to see the summary; unlock it (and sign an NDA if required) to quote.",
    learnMore: "/help#5-3-finding-rfqs",
  },
  "provider.unlock": {
    title: "Unlock this RFQ",
    body:
      "Pays the unlock fee and reveals the full RFQ, contact details and attachments so you can submit a quote.",
    learnMore: "/help#5-4-unlocking-an-rfq",
  },
  "provider.quote-submit": {
    title: "Submit quote",
    body:
      "Send price, timeline, scope and assumptions to the customer. You'll be notified by email if they accept.",
    learnMore: "/help#5-5-submitting-a-quote",
  },
  "provider.profile-edit": {
    title: "Edit firm profile",
    body:
      "Services, industries, certifications and portfolio. A complete profile ranks higher in customer searches.",
    learnMore: "/help#5-2-completing-your-profile",
  },
  "provider.advertise": {
    title: "Buy an ad slot",
    body:
      "$50/month to feature your firm at the top of matching searches. Cancel any time; runs through the end of the paid month.",
    learnMore: "/help#5-6-advertisements",
  },

  // -------- Subscriptions / billing ----------------------------------------
  "billing.manage": {
    title: "Manage billing",
    body:
      "Change plan, update payment method, or cancel. Cancellations take effect at the end of the current billing period.",
    learnMore: "/help#3-subscriptions-and-pricing",
  },
  "billing.cancel": {
    title: "Cancel subscription",
    body:
      "Stops auto-renewal. You keep access until the end of the current period; we don't issue partial-month refunds.",
    learnMore: "/help#cancelling-a-subscription",
  },
  "billing.upgrade": {
    title: "Upgrade or subscribe",
    body:
      "Customer Search Tier 1/2 unlocks the directory and AI Help Assistant. Provider Profile/Annual keeps your firm listed and lets you quote.",
    learnMore: "/help#3-subscriptions-and-pricing",
  },

  // -------- NDA -------------------------------------------------------------
  "nda.sign": {
    title: "Sign NDA",
    body:
      "Opens SignWell. Once signed and the NDA fee is paid, you can unlock the RFQ's full details.",
    learnMore: "/help#4-6-ndas",
  },

  // -------- AI Help Assistant ----------------------------------------------
  "help.assistant": {
    title: "AI Help Assistant",
    body:
      "Grounded on our manual only. It won't give engineering, legal or financial advice, and it can't take actions for you.",
    learnMore: "/help#7-the-ai-help-assistant-in-app-chatbot",
  },

  // -------- Admin -----------------------------------------------------------
  "admin.llm-settings": {
    title: "LLM configuration",
    body:
      "LLM1 = customer search, LLM2 = firm ranking, LLM3 = Document Collapse (used for classification, extraction and the help chatbot). Change without redeploying.",
    learnMore: "/help#the-three-llms",
  },
  "admin.help-logs": {
    title: "Help chat logs",
    body:
      "Every AI Help Assistant turn is logged here so staff can review quality and spot abuse.",
  },
};

export function getHelp(id: string): HelpEntry | null {
  return HELP[id] ?? null;
}
