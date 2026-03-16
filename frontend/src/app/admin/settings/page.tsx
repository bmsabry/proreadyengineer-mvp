'use client'

export const dynamic = 'force-dynamic'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, CheckCircle2, XCircle, AlertCircle, Brain, CreditCard, Mail, HardDrive, FileSignature, LayoutDashboard } from 'lucide-react'
import { api } from '@/lib/api'
import { useRequireAuth } from '@/hooks/useAuth'

interface ServerConfig {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any
  openai_api_key_set: boolean
  stripe_secret_key_set: boolean
  paypal_configured: boolean
  aws_access_key_set: boolean
  resend_api_key_set: boolean
  signwell_api_key_set: boolean
}

interface FormFields {
  openai_api_key: string; openai_api_base: string
  openai_llm_model: string; openai_embedding_model: string
  stripe_secret_key: string; stripe_publishable_key: string; stripe_webhook_secret: string
  paypal_client_id: string; paypal_client_secret: string; paypal_mode: string; paypal_webhook_id: string
  paypal_plan_search_tier1: string; paypal_plan_search_tier2: string; paypal_plan_provider_profile: string; paypal_plan_advertisement: string
  aws_access_key_id: string; aws_secret_access_key: string; aws_region: string; aws_s3_bucket: string
  resend_api_key: string; resend_from_email: string
  signwell_api_key: string; signwell_template_id: string
}

const EMPTY_FORM: FormFields = {
  openai_api_key: '',
  openai_api_base: '',
  openai_llm_model: '',
  openai_embedding_model: '',
  stripe_secret_key: '',
  stripe_publishable_key: '',
  stripe_webhook_secret: '',
  paypal_client_id: '',
  paypal_client_secret: '',
  paypal_mode: '',
  paypal_webhook_id: '',
  paypal_plan_search_tier1: '',
  paypal_plan_search_tier2: '',
  paypal_plan_provider_profile: '',
  paypal_plan_advertisement: '',
  aws_access_key_id: '',
  aws_secret_access_key: '',
  aws_region: '',
  aws_s3_bucket: '',
  resend_api_key: '',
  resend_from_email: '',
  signwell_api_key: '',
  signwell_template_id: '',
}

function StatusBadge({ isSet }: { isSet: boolean }) {
  if (isSet) return (
    <Badge variant="default" className="bg-green-600 hover:bg-green-600 text-white text-xs px-2 py-0.5">
      <CheckCircle2 className="h-3 w-3 mr-1 inline" />Set
    </Badge>
  )
  return (
    <Badge variant="outline" className="border-gray-300 text-gray-500 text-xs px-2 py-0.5">
      <XCircle className="h-3 w-3 mr-1 inline" />Not Set
    </Badge>
  )
}

interface FieldRowProps {
  label: string; fieldName: keyof FormFields; value: string
  onChange: (name: keyof FormFields, val: string) => void
  isSet: boolean; placeholder?: string; inputType?: string; hint?: string
}

function FieldRow({ label, fieldName, value, onChange, isSet, placeholder, inputType = 'text', hint }: FieldRowProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <Label htmlFor={fieldName} className="text-sm font-medium text-gray-700">{label}</Label>
        <StatusBadge isSet={isSet} />
      </div>
      <Input id={fieldName} name={fieldName} type={inputType} value={value}
        onChange={(e) => onChange(fieldName, e.target.value)}
        placeholder={isSet ? '(leave blank to keep existing value)' : (placeholder ?? `Enter ${label}`)}
        className="font-mono text-sm" autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false}
      />
      {hint && <p className="text-xs text-gray-500 mt-0.5">{hint}</p>}
    </div>
  )
}

function SectionCard({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription></CardHeader>
      <CardContent className="space-y-5">{children}</CardContent>
    </Card>
  )
}

export default function AdminSettingsPage() {
  const { isLoading: authLoading, user } = useRequireAuth(['admin']);
  const [config, setConfig] = useState<ServerConfig | null>(null)
  const [form, setForm] = useState<FormFields>(EMPTY_FORM)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [fetchErrorCode, setFetchErrorCode] = useState<number | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  useEffect(() => {
    if (authLoading || !user) return
    let cancelled = false
    setLoading(true); setFetchError(null); setFetchErrorCode(null)
    api.admin.getConfig()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then((res: any) => { if (!cancelled) { setConfig(res.data as ServerConfig); setLoading(false) } })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .catch((err: any) => {
        if (!cancelled) {
          setFetchErrorCode(err?.response?.status ?? null)
          setFetchError(err?.response?.data?.detail ?? err?.message ?? 'Unknown error')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [authLoading, user])

  const handleChange = (name: keyof FormFields, val: string) => {
    setForm((prev) => ({ ...prev, [name]: val }))
    setSuccessMsg(null); setSaveError(null)
  }

  const handleSave = async () => {
    setSaving(true); setSaveError(null); setSuccessMsg(null)
    const payload: Record<string, string> = {}
    for (const [key, val] of Object.entries(form)) {
      if (typeof val === 'string' && val.trim() !== '') payload[key] = val.trim()
    }
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = (await api.admin.saveConfig(payload)).data
      setSuccessMsg(result?.message ?? 'Configuration saved successfully.')
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const updated: any = (await api.admin.getConfig()).data
      setConfig(updated as ServerConfig); setForm(EMPTY_FORM)
    } catch (err: unknown) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const e = err as any
      setSaveError(e?.response?.data?.detail ?? e?.message ?? 'Save failed')
    } finally { setSaving(false) }
  }

  const isFieldSet = (fieldKey: string): boolean => {
    const map: Record<string, keyof ServerConfig> = {
      openai_api_key: 'openai_api_key_set', openai_api_base: 'openai_api_key_set',
      openai_llm_model: 'openai_api_key_set', openai_embedding_model: 'openai_api_key_set',
      stripe_secret_key: 'stripe_secret_key_set', stripe_publishable_key: 'stripe_secret_key_set',
      stripe_webhook_secret: 'stripe_secret_key_set',
      paypal_client_id: 'paypal_configured', paypal_client_secret: 'paypal_configured',
      paypal_mode: 'paypal_configured', paypal_webhook_id: 'paypal_configured',
      paypal_plan_search_tier1: 'paypal_configured', paypal_plan_search_tier2: 'paypal_configured',
      paypal_plan_provider_profile: 'paypal_configured', paypal_plan_advertisement: 'paypal_configured',
      aws_access_key_id: 'aws_access_key_set', aws_secret_access_key: 'aws_access_key_set',
      aws_region: 'aws_access_key_set', aws_s3_bucket: 'aws_access_key_set',
      resend_api_key: 'resend_api_key_set', resend_from_email: 'resend_api_key_set',
      signwell_api_key: 'signwell_api_key_set', signwell_template_id: 'signwell_api_key_set',
    }
    const k = map[fieldKey]
    return k ? Boolean(config?.[k]) : false
  }

  if (loading) return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
      <Loader2 className="h-10 w-10 animate-spin text-blue-600" />
      <p className="text-gray-500 text-sm">Loading configuration…</p>
    </div>
  )

  if (fetchError && (fetchErrorCode === 401 || fetchErrorCode === 403)) return (
    <div className="max-w-xl mx-auto mt-16 p-6">
      <Alert variant="destructive">
        <AlertCircle className="h-5 w-5" />
        <AlertDescription className="space-y-2">
          <p className="font-semibold">{fetchErrorCode === 401 ? 'Authentication required (401)' : 'Access denied (403)'}</p>
          <p>You do not have permission to view this page. Please check:</p>
          <ul className="list-disc list-inside text-sm space-y-1">
            <li>You are logged in as an admin user.</li>
            <li>Your account has the <code className="bg-red-100 px-1 rounded font-mono text-xs">admin</code> role assigned.</li>
            <li>Try logging out and back in to refresh your session.</li>
            <li>Contact your system administrator if this persists.</li>
          </ul>
          <p className="text-xs text-gray-400 font-mono mt-1">Detail: {fetchError}</p>
        </AlertDescription>
      </Alert>
    </div>
  )

  if (fetchError && !config) return (
    <div className="max-w-xl mx-auto mt-16 p-6">
      <Alert variant="destructive">
        <AlertCircle className="h-5 w-5" />
        <AlertDescription>
          <p className="font-semibold">Failed to load configuration</p>
          <p className="text-sm mt-1 font-mono">{fetchError}</p>
        </AlertDescription>
      </Alert>
    </div>
  )

  const services = [
    { key: "ai", title: "AI / Search", Icon: Brain, isSet: Boolean(config?.openai_api_key_set),
      description: "OpenAI for LLM extraction and vector embeddings",
      color: "text-purple-600", bg: "bg-purple-50", border: "border-purple-200" },
    { key: "payments", title: "Payments", Icon: CreditCard, isSet: Boolean(config?.stripe_secret_key_set),
      description: "Stripe for subscriptions, RFQ unlocks, and NDA fees",
      color: "text-blue-600", bg: "bg-blue-50", border: "border-blue-200" },
    { key: "email", title: "Email", Icon: Mail, isSet: Boolean(config?.resend_api_key_set),
      description: "Resend for transactional email delivery",
      color: "text-green-600", bg: "bg-green-50", border: "border-green-200" },
    { key: "storage", title: "Storage", Icon: HardDrive, isSet: Boolean(config?.aws_access_key_set),
      description: "AWS S3 for file uploads and documents",
      color: "text-orange-600", bg: "bg-orange-50", border: "border-orange-200" },
    { key: "signing", title: "Document Signing", Icon: FileSignature, isSet: Boolean(config?.signwell_api_key_set),
      description: "SignWell for NDA embedded signing flows",
      color: "text-indigo-600", bg: "bg-indigo-50", border: "border-indigo-200" },
  ]

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <LayoutDashboard className="h-7 w-7 text-gray-700" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Server Configuration</h1>
          <p className="text-sm text-gray-500">Manage API keys and service credentials stored in the database.</p>
        </div>
      </div>
      {successMsg && (
        <Alert className="border-green-300 bg-green-50">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-800">{successMsg}</AlertDescription>
        </Alert>
      )}
      {saveError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{saveError}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid grid-cols-6 w-full">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="ai">AI / Search</TabsTrigger>
          <TabsTrigger value="payments">Payments</TabsTrigger>
          <TabsTrigger value="email">Email</TabsTrigger>
          <TabsTrigger value="storage">Storage</TabsTrigger>
          <TabsTrigger value="signing">Doc Signing</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {services.map(({ key, title, Icon, isSet, description, color, bg, border }) => (
              <Card key={key} className={`${border} border-2`}>
                <CardContent className="pt-5 pb-4">
                  <div className="flex items-start justify-between mb-3">
                    <div className={`rounded-lg p-2 ${bg}`}>
                      <Icon className={`h-5 w-5 ${color}`} />
                    </div>
                    <StatusBadge isSet={isSet} />
                  </div>
                  <p className="font-semibold text-gray-900 text-sm">{title}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="ai" className="mt-4">
          <SectionCard title="AI / Search Configuration" description="OpenAI credentials for LLM-powered search and vector embeddings.">
            <FieldRow label="OpenAI API Key" fieldName="openai_api_key" value={form.openai_api_key} onChange={handleChange} isSet={isFieldSet("openai_api_key")} inputType="password" hint="sk-... key from platform.openai.com" />
            <FieldRow label="OpenAI API Base URL" fieldName="openai_api_base" value={form.openai_api_base} onChange={handleChange} isSet={isFieldSet("openai_api_base")} placeholder="https://api.openai.com/v1" hint="Leave blank for default — override for Azure OpenAI or custom proxy" />
            <FieldRow label="LLM Model" fieldName="openai_llm_model" value={form.openai_llm_model} onChange={handleChange} isSet={isFieldSet("openai_llm_model")} placeholder="moonshotai/Kimi-K2.5" hint="Model for structured RFQ extraction" />
            <FieldRow label="Embedding Model" fieldName="openai_embedding_model" value={form.openai_embedding_model} onChange={handleChange} isSet={isFieldSet("openai_embedding_model")} placeholder="text-embedding-3-small" hint="Model for provider and query embeddings" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="payments" className="mt-4">
          <SectionCard title="Payment Configuration" description="Stripe credentials for subscriptions, RFQ unlocks, and NDA fees.">
            <FieldRow label="Stripe Secret Key" fieldName="stripe_secret_key" value={form.stripe_secret_key} onChange={handleChange} isSet={isFieldSet("stripe_secret_key")} inputType="password" hint="sk_live_... or sk_test_... from Stripe Dashboard" />
            <FieldRow label="Stripe Publishable Key" fieldName="stripe_publishable_key" value={form.stripe_publishable_key} onChange={handleChange} isSet={isFieldSet("stripe_publishable_key")} hint="pk_live_... or pk_test_... used on the client side" />
            <FieldRow label="Stripe Webhook Secret" fieldName="stripe_webhook_secret" value={form.stripe_webhook_secret} onChange={handleChange} isSet={isFieldSet("stripe_webhook_secret")} inputType="password" hint="whsec_... from Stripe Webhook endpoint settings" />
          </SectionCard>
          <SectionCard title="PayPal Configuration" description="PayPal credentials for one-time payments and subscriptions alongside Stripe.">
            <FieldRow label="PayPal Client ID" fieldName="paypal_client_id" value={form.paypal_client_id} onChange={handleChange} isSet={isFieldSet("paypal_client_id")} hint="Client ID from PayPal Developer Dashboard (sandbox or live)" />
            <FieldRow label="PayPal Client Secret" fieldName="paypal_client_secret" value={form.paypal_client_secret} onChange={handleChange} isSet={isFieldSet("paypal_client_secret")} inputType="password" hint="Client Secret from PayPal Developer Dashboard" />
            <FieldRow label="PayPal Mode" fieldName="paypal_mode" value={form.paypal_mode} onChange={handleChange} isSet={isFieldSet("paypal_mode")} hint='sandbox or live' />
            <FieldRow label="PayPal Webhook ID" fieldName="paypal_webhook_id" value={form.paypal_webhook_id} onChange={handleChange} isSet={isFieldSet("paypal_webhook_id")} inputType="password" hint="Webhook ID for signature verification" />
            <FieldRow label="Plan ID: Search Tier 1" fieldName="paypal_plan_search_tier1" value={form.paypal_plan_search_tier1} onChange={handleChange} isSet={isFieldSet("paypal_plan_search_tier1")} hint="PayPal plan ID for 100 searches/mo ($10/mo)" />
            <FieldRow label="Plan ID: Search Tier 2" fieldName="paypal_plan_search_tier2" value={form.paypal_plan_search_tier2} onChange={handleChange} isSet={isFieldSet("paypal_plan_search_tier2")} hint="PayPal plan ID for 200 searches/mo ($20/mo)" />
            <FieldRow label="Plan ID: Provider Profile" fieldName="paypal_plan_provider_profile" value={form.paypal_plan_provider_profile} onChange={handleChange} isSet={isFieldSet("paypal_plan_provider_profile")} hint="PayPal plan ID for provider profile subscription ($10/mo)" />
            <FieldRow label="Plan ID: Advertisement" fieldName="paypal_plan_advertisement" value={form.paypal_plan_advertisement} onChange={handleChange} isSet={isFieldSet("paypal_plan_advertisement")} hint="PayPal plan ID for ad slot subscription ($50/mo)" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="email" className="mt-4">
          <SectionCard title="Email Configuration" description="Resend API for all transactional emails — RFQ notifications, quotes, and auth flows.">
            <FieldRow label="Resend API Key" fieldName="resend_api_key" value={form.resend_api_key} onChange={handleChange} isSet={isFieldSet("resend_api_key")} inputType="password" hint="re_... key from the Resend Dashboard" />
            <FieldRow label="From Email Address" fieldName="resend_from_email" value={form.resend_from_email} onChange={handleChange} isSet={isFieldSet("resend_from_email")} placeholder="noreply@yourdomain.com" hint="Must be a verified sender domain in Resend" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="storage" className="mt-4">
          <SectionCard title="Storage Configuration" description="AWS S3 credentials for file uploads, RFQ documents, and signed NDA storage.">
            <FieldRow label="AWS Access Key ID" fieldName="aws_access_key_id" value={form.aws_access_key_id} onChange={handleChange} isSet={isFieldSet("aws_access_key_id")} hint="IAM user access key with S3 read/write permissions" />
            <FieldRow label="AWS Secret Access Key" fieldName="aws_secret_access_key" value={form.aws_secret_access_key} onChange={handleChange} isSet={isFieldSet("aws_secret_access_key")} inputType="password" hint="Keep this secret — never expose in client code" />
            <FieldRow label="AWS Region" fieldName="aws_region" value={form.aws_region} onChange={handleChange} isSet={isFieldSet("aws_region")} placeholder="us-east-1" hint="Region where your S3 bucket is located" />
            <FieldRow label="S3 Bucket Name" fieldName="aws_s3_bucket" value={form.aws_s3_bucket} onChange={handleChange} isSet={isFieldSet("aws_s3_bucket")} placeholder="my-proready-bucket" hint="The S3 bucket name for uploads and document storage" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="signing" className="mt-4">
          <SectionCard title="Document Signing Configuration" description="SignWell credentials for NDA embedded signing workflows.">
            <FieldRow label="SignWell API Key" fieldName="signwell_api_key" value={form.signwell_api_key} onChange={handleChange} isSet={isFieldSet("signwell_api_key")} inputType="password" hint="API key from your SignWell account settings" />
            <FieldRow label="SignWell Template ID" fieldName="signwell_template_id" value={form.signwell_template_id} onChange={handleChange} isSet={isFieldSet("signwell_template_id")} hint="Template ID for the NDA document in SignWell" />
          </SectionCard>
        </TabsContent>

      </Tabs>

      <div className="flex justify-end pt-4 border-t border-gray-200">
        <Button
          onClick={handleSave}
          disabled={saving}
          size="lg"
          className="min-w-[180px]"
        >
          {saving ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</>
          ) : (
            <><CheckCircle2 className="h-4 w-4 mr-2" />Save to Database</>
          )}
        </Button>
      </div>
    </div>
  )
}
