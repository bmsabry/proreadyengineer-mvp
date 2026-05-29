'use client'
export const dynamic = 'force-dynamic'

import { useState, useEffect, useCallback, useRef } from 'react'
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
  openai_api_base: string
  openai_api_base_set: boolean
  openai_llm_model: string
  openai_llm_model_set: boolean
  openai_embedding_model: string
  openai_embedding_model_set: boolean
  embedding_api_key_set: boolean
  embedding_api_base: string
  embedding_api_base_set: boolean
  doc_llm_api_key_set: boolean
  doc_llm_api_base: string
  doc_llm_api_base_set: boolean
  doc_llm_model: string
  doc_llm_model_set: boolean
  render_api_key_set: boolean
  render_monthly_budget_set: boolean
  stripe_secret_key_set: boolean
  stripe_webhook_secret_set: boolean
  stripe_publishable_key: string
  stripe_publishable_key_set: boolean
  paypal_configured: boolean
  paypal_mode: string
  paypal_mode_set: boolean
  aws_access_key_set: boolean
  aws_secret_access_key_set: boolean
  aws_region: string
  aws_region_set: boolean
  aws_s3_bucket: string
  aws_s3_bucket_set: boolean
  resend_api_key_set: boolean
  resend_from_email: string
  resend_from_email_set: boolean
  smtp_host: string
  smtp_host_set: boolean
  smtp_port: string
  smtp_user: string
  smtp_user_set: boolean
  smtp_password_set: boolean
  smtp_tls: string
  smtp_ssl: string
  signwell_api_key_set: boolean
  signwell_template_id: string
  signwell_template_id_set: boolean
  rfq_batch_size: string
  rfq_batch_size_set: boolean
  rfq_batch_interval_hours: string
  rfq_batch_interval_hours_set: boolean
  rfq_closed_message: string
  rfq_closed_message_set: boolean
}

interface FormFields {
  openai_api_key: string
  openai_api_base: string
  openai_llm_model: string
  openai_embedding_model: string
  embedding_api_key: string
  embedding_api_base: string
  doc_llm_api_key: string
  doc_llm_api_base: string
  doc_llm_model: string
  stripe_secret_key: string
  stripe_publishable_key: string
  stripe_webhook_secret: string
  paypal_client_id: string
  paypal_client_secret: string
  paypal_mode: string
  paypal_webhook_id: string
  render_api_key: string
  render_monthly_budget: string
  paypal_plan_search_tier1: string
  paypal_plan_search_tier2: string
  paypal_plan_provider_profile: string
  paypal_plan_advertisement: string
  aws_access_key_id: string
  aws_secret_access_key: string
  aws_region: string
  aws_s3_bucket: string
  resend_api_key: string
  resend_from_email: string
  smtp_host: string
  smtp_port: string
  smtp_user: string
  smtp_password: string
  smtp_tls: string
  smtp_ssl: string
  signwell_api_key: string
  signwell_template_id: string
  rfq_batch_size: string
  rfq_batch_interval_hours: string
  rfq_closed_message: string
}

const SECRET_FIELDS: (keyof FormFields)[] = [
  'openai_api_key', 'stripe_secret_key', 'stripe_webhook_secret',
  'paypal_client_id', 'paypal_client_secret', 'paypal_webhook_id', 'render_api_key',
  'paypal_plan_search_tier1', 'paypal_plan_search_tier2',
  'paypal_plan_provider_profile', 'paypal_plan_advertisement',
  'aws_access_key_id', 'aws_secret_access_key',
  'resend_api_key', 'smtp_password', 'signwell_api_key',
  'doc_llm_api_key',
  'embedding_api_key',
]

const EMPTY_FORM: FormFields = {
  openai_api_key: '',
  openai_api_base: '',
  openai_llm_model: '',
  openai_embedding_model: '',
  embedding_api_key: '',
  embedding_api_base: '',
  doc_llm_api_key: '',
  doc_llm_api_base: '',
  doc_llm_model: '',
  stripe_secret_key: '',
  stripe_publishable_key: '',
  stripe_webhook_secret: '',
  paypal_client_id: '',
  paypal_client_secret: '',
  paypal_mode: '',
  paypal_webhook_id: '',
  render_api_key: '',
  render_monthly_budget: '',
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
  smtp_host: '',
  smtp_port: '587',
  smtp_user: '',
  smtp_password: '',
  smtp_tls: 'true',
  smtp_ssl: 'false',
  signwell_api_key: '',
  signwell_template_id: '',
  rfq_batch_size: '',
  rfq_batch_interval_hours: '',
  rfq_closed_message: '',
}

function populateFormFromConfig(cfg: ServerConfig): Partial<FormFields> {
  return {
    openai_api_base: cfg.openai_api_base || '',
    openai_llm_model: cfg.openai_llm_model || '',
    openai_embedding_model: cfg.openai_embedding_model || '',
    embedding_api_base: cfg.embedding_api_base || '',
    doc_llm_api_base: cfg.doc_llm_api_base || '',
    doc_llm_model: cfg.doc_llm_model || '',
    stripe_publishable_key: cfg.stripe_publishable_key || '',
    paypal_mode: cfg.paypal_mode || '',
    aws_region: cfg.aws_region || '',
    aws_s3_bucket: cfg.aws_s3_bucket || '',
    resend_from_email: cfg.resend_from_email || '',
    smtp_host: cfg.smtp_host || '',
    smtp_port: cfg.smtp_port || '587',
    smtp_user: cfg.smtp_user || '',
    smtp_tls: cfg.smtp_tls || 'true',
    smtp_ssl: cfg.smtp_ssl || 'false',
    signwell_template_id: cfg.signwell_template_id || '',
    rfq_batch_size: cfg.rfq_batch_size || '',
    rfq_batch_interval_hours: cfg.rfq_batch_interval_hours || '',
    rfq_closed_message: cfg.rfq_closed_message || '',
  }
}

function StatusBadge({ isSet }: { isSet: boolean }) {
  if (isSet) {
    return (
      <Badge className='bg-green-100 text-green-800 border-green-300 flex items-center gap-1'>
        <CheckCircle2 className='w-3 h-3' />
        Set
      </Badge>
    )
  }
  return (
    <Badge variant='outline' className='text-gray-500 border-gray-300 flex items-center gap-1'>
      <XCircle className='w-3 h-3' />
      Not Set
    </Badge>
  )
}

interface FieldRowProps {
  label: string
  fieldName: keyof FormFields
  value: string
  onChange: (field: keyof FormFields, value: string) => void
  isSet: boolean
  isSecret?: boolean
  placeholder?: string
  inputType?: string
  hint?: string
}

function FieldRow({
  label,
  fieldName,
  value,
  onChange,
  isSet,
  isSecret = false,
  placeholder,
  inputType,
  hint,
}: FieldRowProps) {
  const effectivePlaceholder =
    isSecret && isSet ? '(leave blank to keep existing value)' : placeholder || ''
  const effectiveType = isSecret ? inputType || 'password' : inputType || 'text'
  return (
    <div className='space-y-1.5'>
      <div className='flex items-center justify-between'>
        <Label htmlFor={fieldName} className='text-sm font-medium'>
          {label}
        </Label>
        <StatusBadge isSet={isSet} />
      </div>
      <Input
        id={fieldName}
        type={effectiveType}
        value={value}
        onChange={(e) => onChange(fieldName, e.target.value)}
        placeholder={effectivePlaceholder}
        autoComplete='off'
      />
      {hint && <p className='text-xs text-muted-foreground'>{hint}</p>}
    </div>
  )
}

export default function AdminSettingsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin'])
  const [config, setConfig] = useState<ServerConfig | null>(null)
  const [form, setForm] = useState<FormFields>(EMPTY_FORM)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [cronStatus, setCronStatus] = useState<{
    last_run: string | null;
    minutes_ago: number | null;
    last_result: string | null;
    status: string;
  } | null>(null)
  const [cronTriggerLoading, setCronTriggerLoading] = useState(false)
  const [cronTriggerResult, setCronTriggerResult] = useState<string | null>(null)
  const cronFetchedRef = useRef(false)

  const loadConfig = useCallback(async () => {
    try {
      setLoading(true)
      const response = await api.admin.getConfig()
      const cfg = ((response as any).data ?? response) as unknown as ServerConfig
      setConfig(cfg)
      // Pre-populate non-secret fields; keep secret fields empty
      setForm((prev) => ({
        ...prev,
        ...populateFormFromConfig(cfg),
      }))
    } catch {
      setErrorMsg('Failed to load configuration')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!authLoading) {
      loadConfig()
    }
  }, [authLoading, loadConfig])
  const loadCronStatus = useCallback(async () => {
    try {
      const res = await api.internal.getCronStatus()
      setCronStatus(res.data)
    } catch (e) {
      console.error('[CronStatus] failed to load', e)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && !cronFetchedRef.current) {
      cronFetchedRef.current = true
      loadCronStatus()
    }
  }, [authLoading, loadCronStatus])

  const handleTriggerDispatch = async () => {
    setCronTriggerLoading(true)
    setCronTriggerResult(null)
    try {
      const res = await api.internal.triggerDispatch()
      const d = res.data
      setCronTriggerResult(`Done: found ${d.open_rfqs_found} RFQ(s). Dispatched: ${d.dispatched.length}. Skipped: ${d.skipped.length}. Interval: ${d.interval_hours}h`)
      await loadCronStatus()
    } catch (e: unknown) {
      setCronTriggerResult('Error: ' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setCronTriggerLoading(false)
    }
  }

  function isFieldSet(fieldKey: keyof FormFields): boolean {
    if (!config) return false
    const boolMap: Record<string, string> = {
      openai_api_key: 'openai_api_key_set',
      openai_api_base: 'openai_api_base_set',
      openai_llm_model: 'openai_llm_model_set',
      openai_embedding_model: 'openai_embedding_model_set',
      embedding_api_key: 'embedding_api_key_set',
      embedding_api_base: 'embedding_api_base_set',
      doc_llm_api_key: 'doc_llm_api_key_set',
      doc_llm_api_base: 'doc_llm_api_base_set',
      doc_llm_model: 'doc_llm_model_set',
      stripe_secret_key: 'stripe_secret_key_set',
      stripe_webhook_secret: 'stripe_webhook_secret_set',
      stripe_publishable_key: 'stripe_publishable_key_set',
      paypal_client_id: 'paypal_configured',
      paypal_client_secret: 'paypal_configured',
      paypal_mode: 'paypal_mode_set',
      paypal_webhook_id: 'paypal_configured',
      render_api_key: 'render_api_key_set',
      render_monthly_budget: 'render_monthly_budget_set',
      paypal_plan_search_tier1: 'paypal_configured',
      paypal_plan_search_tier2: 'paypal_configured',
      paypal_plan_provider_profile: 'paypal_configured',
      paypal_plan_advertisement: 'paypal_configured',
      aws_access_key_id: 'aws_access_key_set',
      aws_secret_access_key: 'aws_secret_access_key_set',
      aws_region: 'aws_region_set',
      aws_s3_bucket: 'aws_s3_bucket_set',
      resend_api_key: 'resend_api_key_set',
      resend_from_email: 'resend_from_email_set',
      smtp_host: 'smtp_host_set',
      smtp_user: 'smtp_user_set',
      smtp_password: 'smtp_password_set',
      signwell_api_key: 'signwell_api_key_set',
      signwell_template_id: 'signwell_template_id_set',
      rfq_batch_size: 'rfq_batch_size_set',
      rfq_batch_interval_hours: 'rfq_batch_interval_hours_set',
      rfq_closed_message: 'rfq_closed_message_set',
    }
    const boolKey = boolMap[fieldKey]
    return boolKey ? Boolean(config[boolKey]) : false
  }

  function handleChange(field: keyof FormFields, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  const [s3TestStatus, setS3TestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle')
  const [s3TestResult, setS3TestResult] = useState<{
    error?: string
    bucket_name?: string
    download_url?: string
    aws_access_key_configured?: boolean
    aws_secret_key_configured?: boolean
    bucket_configured?: boolean
    upload_success?: boolean
    download_url_success?: boolean
  } | null>(null)

  const testS3Connection = async () => {
    setS3TestStatus('testing')
    setS3TestResult(null)
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/admin/debug/test-s3`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      })
      const data = await res.json()
      setS3TestResult(data)
      setS3TestStatus(data.upload_success && data.download_url_success ? 'success' : 'error')
    } catch (err: unknown) {
      setS3TestResult({ error: err instanceof Error ? err.message : 'Network error connecting to backend' })
      setS3TestStatus('error')
    }
  }

  async function handleSave() {
    setSaving(true)
    setSuccessMsg(null)
    setErrorMsg(null)
    try {
      const payload: Partial<FormFields> = {}
      for (const key of Object.keys(form) as (keyof FormFields)[]) {
        if (form[key] !== '') {
          payload[key] = form[key]
        }
      }
      await api.admin.saveConfig(payload)
      setSuccessMsg('Configuration saved successfully.')
      // Clear secret field inputs after save
      setForm((prev) => {
        const updated = { ...prev }
        for (const secretField of SECRET_FIELDS) {
          updated[secretField] = ''
        }
        return updated
      })
      // Re-fetch config: updates Set/Not Set indicators and repopulates non-secret fields
      await loadConfig()
  } catch (err: any) {
    // Extract detailed validation error from response if available
    const detail = err?.response?.data?.detail
    let message: string
    if (Array.isArray(detail)) {
      message = detail.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join('; ')
    } else if (typeof detail === 'string') {
      message = detail
    } else if (detail) {
      message = JSON.stringify(detail)
    } else {
      message = err instanceof Error ? err.message : String(err)
    }
    setErrorMsg(`Failed to save configuration: ${message}`)
  } finally {
    setSaving(false)
  }
  }

  if (authLoading) {
    return (
      <div className='flex items-center justify-center min-h-screen'>
        <Loader2 className='w-8 h-8 animate-spin text-gray-400' />
      </div>
    )
  }

  if (loading) {
    return (
      <div className='flex items-center justify-center min-h-screen'>
        <Loader2 className='w-8 h-8 animate-spin text-gray-400' />
      </div>
    )
  }

  return (
    <div className='max-w-4xl mx-auto p-6 space-y-6'>
      <div>
        <h1 className='text-2xl font-bold tracking-tight'>System Configuration</h1>
        <p className='text-sm text-muted-foreground mt-1'>
          Manage API keys, integrations, and platform settings.
        </p>
      </div>

      {successMsg && (
        <Alert className='border-green-300 bg-green-50'>
          <CheckCircle2 className='w-4 h-4 text-green-600' />
          <AlertDescription className='text-green-800'>{successMsg}</AlertDescription>
        </Alert>
      )}

      {errorMsg && (
        <Alert variant='destructive'>
          <AlertCircle className='w-4 h-4' />
          <AlertDescription>{errorMsg}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue='ai'>
        <TabsList className='grid grid-cols-6 w-full'>
          <TabsTrigger value='ai' className='flex items-center gap-1.5'>
            <Brain className='w-4 h-4' />
            <span className='hidden sm:inline'>AI / Search</span>
          </TabsTrigger>
          <TabsTrigger value='payments' className='flex items-center gap-1.5'>
            <CreditCard className='w-4 h-4' />
            <span className='hidden sm:inline'>Payments</span>
          </TabsTrigger>
          <TabsTrigger value='email' className='flex items-center gap-1.5'>
            <Mail className='w-4 h-4' />
            <span className='hidden sm:inline'>Email</span>
          </TabsTrigger>
          <TabsTrigger value='storage' className='flex items-center gap-1.5'>
            <HardDrive className='w-4 h-4' />
            <span className='hidden sm:inline'>Storage</span>
          </TabsTrigger>
          <TabsTrigger value='signing' className='flex items-center gap-1.5'>
            <FileSignature className='w-4 h-4' />
            <span className='hidden sm:inline'>Doc Signing</span>
          </TabsTrigger>
          <TabsTrigger value='rfq' className='flex items-center gap-1.5'>
            <LayoutDashboard className='w-4 h-4' />
            <span className='hidden sm:inline'>RFQ</span>
          </TabsTrigger>
        </TabsList>

        {/* ── AI / Search ── */}
        <TabsContent value='ai' className='space-y-4'>
          {/* Sub-section 1: Embeddings (LLM 1) */}
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Brain className='w-5 h-5' />
                Embeddings — LLM 1
              </CardTitle>
              <CardDescription>
                API credentials used to generate vector embeddings for provider and query search matching.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='API Key'
                fieldName='embedding_api_key'
                value={form.embedding_api_key}
                onChange={handleChange}
                isSet={isFieldSet('embedding_api_key')}
                isSecret
                hint='API key for the embeddings service (separate from LLM 2 key). Run generate_embeddings.py from shell with this key.'
              />
              <FieldRow
                label='API Base URL'
                fieldName='embedding_api_base'
                value={form.embedding_api_base}
                onChange={handleChange}
                isSet={isFieldSet('embedding_api_base')}
                placeholder='https://api.deepinfra.com/v1/openai'
                hint='Base URL for the embeddings API endpoint (e.g. DeepInfra, OpenAI).'
              />
              <FieldRow
                label='Embedding Model'
                fieldName='openai_embedding_model'
                value={form.openai_embedding_model}
                onChange={handleChange}
                isSet={isFieldSet('openai_embedding_model')}
                placeholder='BAAI/bge-large-en-v1.5'
                hint='Model name passed to the embeddings API.'
              />
            </CardContent>
          </Card>

          {/* Sub-section 2: Firm Ranking LLM (LLM 2) */}
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Brain className='w-5 h-5' />
                Firm Ranking — LLM 2
              </CardTitle>
              <CardDescription>
                LLM used for the Pass 1 &amp; Pass 2 firm ranking pipeline — structured extraction from customer queries, specialty inference, and provider scoring.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='API Key'
                fieldName='openai_api_key'
                value={form.openai_api_key}
                onChange={handleChange}
                isSet={isFieldSet('openai_api_key')}
                isSecret
                hint='API key for the firm ranking LLM (separate from LLM 1 embeddings key).'
              />
              <FieldRow
                label='API Base URL'
                fieldName='openai_api_base'
                value={form.openai_api_base}
                onChange={handleChange}
                isSet={isFieldSet('openai_api_base')}
                placeholder='https://api.deepinfra.com/v1/openai'
                hint='Base URL for the firm ranking LLM API endpoint.'
              />
              <FieldRow
                label='LLM Model'
                fieldName='openai_llm_model'
                value={form.openai_llm_model}
                onChange={handleChange}
                isSet={isFieldSet('openai_llm_model')}
                placeholder='moonshotai/kimi-k2.5'
                hint='Model used for Pass 1 query extraction and Pass 2 firm ranking scoring.'
              />
            </CardContent>
          </Card>

          {/* Sub-section 3: Document Collapse LLM (LLM 3) */}
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Brain className='w-5 h-5' />
                Document Collapse — LLM 3
              </CardTitle>
              <CardDescription>
                Separate LLM used exclusively for summarising and collapsing RFQ documents uploaded by customers before they are processed by the ranking pipeline.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='API Key'
                fieldName='doc_llm_api_key'
                value={form.doc_llm_api_key}
                onChange={handleChange}
                isSet={isFieldSet('doc_llm_api_key')}
                isSecret
                hint='API key for the document collapse LLM (can differ from LLM 1/2 key).'
              />
              <FieldRow
                label='API Base URL'
                fieldName='doc_llm_api_base'
                value={form.doc_llm_api_base}
                onChange={handleChange}
                isSet={isFieldSet('doc_llm_api_base')}
                placeholder='https://api.openai.com/v1'
                hint='Leave blank to use the default OpenAI endpoint.'
              />
              <FieldRow
                label='LLM Model'
                fieldName='doc_llm_model'
                value={form.doc_llm_model}
                onChange={handleChange}
                isSet={isFieldSet('doc_llm_model')}
                placeholder='gpt-4o-mini'
                hint='Model used to summarise RFQ documents before ranking.'
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Payments ── */}
        <TabsContent value='payments' className='space-y-4'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <CreditCard className='w-5 h-5' />
                Stripe
              </CardTitle>
              <CardDescription>
                Stripe keys for card payments, subscriptions, and billing portal.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='Stripe Secret Key'
                fieldName='stripe_secret_key'
                value={form.stripe_secret_key}
                onChange={handleChange}
                isSet={isFieldSet('stripe_secret_key')}
                isSecret
              />
              <FieldRow
                label='Stripe Publishable Key'
                fieldName='stripe_publishable_key'
                value={form.stripe_publishable_key}
                onChange={handleChange}
                isSet={isFieldSet('stripe_publishable_key')}
                placeholder='pk_live_...'
              />
              <FieldRow
                label='Stripe Webhook Secret'
                fieldName='stripe_webhook_secret'
                value={form.stripe_webhook_secret}
                onChange={handleChange}
                isSet={isFieldSet('stripe_webhook_secret')}
                isSecret
                hint='Signing secret for verifying Stripe webhook events.'
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>PayPal / Braintree</CardTitle>
              <CardDescription>
                PayPal credentials for PayPal and Venmo payment support.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='PayPal Client ID'
                fieldName='paypal_client_id'
                value={form.paypal_client_id}
                onChange={handleChange}
                isSet={isFieldSet('paypal_client_id')}
                isSecret
              />
              <FieldRow
                label='PayPal Client Secret'
                fieldName='paypal_client_secret'
                value={form.paypal_client_secret}
                onChange={handleChange}
                isSet={isFieldSet('paypal_client_secret')}
                isSecret
              />
              <FieldRow
                label='PayPal Mode'
                fieldName='paypal_mode'
                value={form.paypal_mode}
                onChange={handleChange}
                isSet={isFieldSet('paypal_mode')}
                placeholder='sandbox or live'
              />
              <FieldRow
                label='PayPal Webhook ID'
                fieldName='paypal_webhook_id'
                value={form.paypal_webhook_id}
                onChange={handleChange}
                isSet={isFieldSet('paypal_webhook_id')}
                isSecret
              />
              <FieldRow
                label='PayPal Plan — Search Tier 1'
                fieldName='paypal_plan_search_tier1'
                value={form.paypal_plan_search_tier1}
                onChange={handleChange}
                isSet={isFieldSet('paypal_plan_search_tier1')}
                isSecret
                hint='Plan ID for 100 searches/month ($10/month).'
              />
              <FieldRow
                label='PayPal Plan — Provider Profile'
                fieldName='paypal_plan_provider_profile'
                value={form.paypal_plan_provider_profile}
                onChange={handleChange}
                isSet={isFieldSet('paypal_plan_provider_profile')}
                isSecret
                hint='Plan ID for provider profile subscription ($10/month).'
              />
              <FieldRow
                label='PayPal Plan — Advertisement'
                fieldName='paypal_plan_advertisement'
                value={form.paypal_plan_advertisement}
                onChange={handleChange}
                isSet={isFieldSet('paypal_plan_advertisement')}
                isSecret
                hint='Plan ID for ad slot subscription ($50/month).'
              />
            </CardContent>
          </Card>
        <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                Render
              </CardTitle>
              <CardDescription>
                Render API credentials for service monitoring in the Payment Dashboard.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='Render API Key'
                fieldName='render_api_key'
                value={form.render_api_key}
                onChange={handleChange}
                isSet={isFieldSet('render_api_key')}
                isSecret
                hint='Get from Render dashboard → Account Settings → API Keys. Enables service status monitoring.'
              />
              <FieldRow
                label='Monthly Budget (USD)'
                fieldName='render_monthly_budget'
                value={form.render_monthly_budget}
                onChange={handleChange}
                isSet={isFieldSet('render_monthly_budget')}
                placeholder='e.g. 50'
                hint='Optional manual budget figure. Shown as a progress bar in Payment Monitoring.'
              />
            </CardContent>
          </Card>

        </TabsContent>

        {/* ── Email ── */}
        <TabsContent value='email'>
          <div className='space-y-4'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Mail className='w-5 h-5' />
                Resend (Transactional Email)
              </CardTitle>
              <CardDescription>
                Resend API credentials for transactional email delivery (recommended).
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='Resend API Key'
                fieldName='resend_api_key'
                value={form.resend_api_key}
                onChange={handleChange}
                isSet={isFieldSet('resend_api_key')}
                isSecret
                hint='API key from resend.com for sending transactional emails.'
              />
              <FieldRow
                label='From Email Address'
                fieldName='resend_from_email'
                value={form.resend_from_email}
                onChange={handleChange}
                isSet={isFieldSet('resend_from_email')}
                placeholder='noreply@yourdomain.com'
                hint='The sender address shown on outbound system emails.'
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Mail className='w-5 h-5' />
                SMTP (Alternative Email)
              </CardTitle>
              <CardDescription>
                SMTP server settings as an alternative to Resend. Used if Resend is not configured.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='SMTP Host'
                fieldName='smtp_host'
                value={form.smtp_host}
                onChange={handleChange}
                isSet={isFieldSet('smtp_host')}
                placeholder='smtp.gmail.com'
                hint='SMTP server hostname (e.g. smtp.gmail.com, smtp.sendgrid.net).'
              />
              <FieldRow
                label='SMTP Port'
                fieldName='smtp_port'
                value={form.smtp_port}
                onChange={handleChange}
                isSet={isFieldSet('smtp_port')}
                placeholder='587'
                hint='SMTP port: 587 for STARTTLS, 465 for SSL, 25 for plain.'
              />
              <FieldRow
                label='SMTP Username'
                fieldName='smtp_user'
                value={form.smtp_user}
                onChange={handleChange}
                isSet={isFieldSet('smtp_user')}
                placeholder='user@example.com'
                hint='SMTP login username.'
              />
              <FieldRow
                label='SMTP Password'
                fieldName='smtp_password'
                value={form.smtp_password}
                onChange={handleChange}
                isSet={isFieldSet('smtp_password')}
                isSecret
                hint='SMTP login password or app-specific password.'
              />
              <FieldRow
                label='Use STARTTLS'
                fieldName='smtp_tls'
                value={form.smtp_tls}
                onChange={handleChange}
                isSet={isFieldSet('smtp_tls')}
                placeholder='true'
                hint='Set to true for STARTTLS (port 587). Set to false for plain or SSL.'
              />
              <FieldRow
                label='Use SSL'
                fieldName='smtp_ssl'
                value={form.smtp_ssl}
                onChange={handleChange}
                isSet={isFieldSet('smtp_ssl')}
                placeholder='false'
                hint='Set to true for implicit SSL (port 465). Overrides STARTTLS.'
              />
            </CardContent>
          </Card>
          </div>
        </TabsContent>

        {/* ── Storage ── */}
        <TabsContent value='storage'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <HardDrive className='w-5 h-5' />
                AWS S3 Storage
              </CardTitle>
              <CardDescription>
                AWS credentials for S3 file storage (RFQ files, NDAs, ad assets).
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='AWS Access Key ID'
                fieldName='aws_access_key_id'
                value={form.aws_access_key_id}
                onChange={handleChange}
                isSet={isFieldSet('aws_access_key_id')}
                isSecret
              />
              <FieldRow
                label='AWS Secret Access Key'
                fieldName='aws_secret_access_key'
                value={form.aws_secret_access_key}
                onChange={handleChange}
                isSet={isFieldSet('aws_secret_access_key')}
                isSecret
              />
              <FieldRow
                label='AWS Region'
                fieldName='aws_region'
                value={form.aws_region}
                onChange={handleChange}
                isSet={isFieldSet('aws_region')}
                placeholder='us-east-1'
              />
              <FieldRow
                label='S3 Bucket Name'
                fieldName='aws_s3_bucket'
                value={form.aws_s3_bucket}
                onChange={handleChange}
                isSet={isFieldSet('aws_s3_bucket')}
                placeholder='my-proready-bucket'
              />
              {/* S3 Test Button */}
              <div className='pt-2'>
                <Button
                  variant='outline'
                  size='sm'
                  onClick={testS3Connection}
                  disabled={s3TestStatus === 'testing'}
                  className='flex items-center gap-2'
                >
                  {s3TestStatus === 'testing' ? (
                    <><Loader2 className='w-4 h-4 animate-spin' /> Testing S3...</>
                  ) : s3TestStatus === 'success' ? (
                    <><CheckCircle2 className='w-4 h-4 text-green-500' /> S3 Working✓</>
                  ) : s3TestStatus === 'error' ? (
                    <><XCircle className='w-4 h-4 text-red-500' /> S3 Test Failed</>
                  ) : (
                    <><HardDrive className='w-4 h-4' /> Test S3 Connection</>
                  )}
                </Button>
                {s3TestResult && (
                  <div className={`mt-3 p-3 rounded text-sm ${s3TestStatus === 'success' ? 'bg-green-50 border border-green-200 text-green-800' : 'bg-red-50 border border-red-200 text-red-800'}`}>
                    {s3TestStatus === 'success' ? (
                      <div>
                        <p className='font-semibold'>✓ S3 is configured and working!</p>
                        <p className='text-xs mt-1'>Bucket: {s3TestResult.bucket_name}</p>
                        <p className='text-xs'>Upload: ✓ | Presigned URL: ✓ | Delete: ✓</p>
                      </div>
                    ) : (
                      <div>
                        <p className='font-semibold'>S3 configuration issue:</p>
                        <p className='text-xs mt-1 font-mono break-all'>{s3TestResult.error}</p>
                        <div className='text-xs mt-1'>
                          <span>Access Key: {s3TestResult.aws_access_key_configured ? '✓' : '✗ Not set'} | </span>
                          <span>Secret Key: {s3TestResult.aws_secret_key_configured ? '✓' : '✗ Not set'} | </span>
                          <span>Bucket: {s3TestResult.bucket_configured ? '✓' : '✗ Not set'}</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

                

        {/* ── Doc Signing ── */}
        <TabsContent value='signing'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <FileSignature className='w-5 h-5' />
                Document Signing
              </CardTitle>
              <CardDescription>
                SignWell API credentials for embedded NDA signing flows.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='SignWell API Key'
                fieldName='signwell_api_key'
                value={form.signwell_api_key}
                onChange={handleChange}
                isSet={isFieldSet('signwell_api_key')}
                isSecret
              />
              <FieldRow
                label='SignWell Template ID'
                fieldName='signwell_template_id'
                value={form.signwell_template_id}
                onChange={handleChange}
                isSet={isFieldSet('signwell_template_id')}
                placeholder='template_...'
                hint='ID of the NDA template in SignWell.'
              />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── RFQ ── */}
        <TabsContent value='rfq'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <LayoutDashboard className='w-5 h-5' />
                RFQ Settings
              </CardTitle>
              <CardDescription>
                Configure RFQ dispatch batching and messaging behaviour.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='Batch Size'
                fieldName='rfq_batch_size'
                value={form.rfq_batch_size}
                onChange={handleChange}
                isSet={isFieldSet('rfq_batch_size')}
                placeholder='5'
                inputType='number'
                hint='Number of providers emailed per dispatch batch.'
              />
              <FieldRow
                label='Batch Interval (hours)'
                fieldName='rfq_batch_interval_hours'
                value={form.rfq_batch_interval_hours}
                onChange={handleChange}
                isSet={isFieldSet('rfq_batch_interval_hours')}
                placeholder='24'
                inputType='number'
                hint='Hours between each dispatch batch.'
              />
              {/* ── Cron Status Panel ── */}
              <div className='mt-6 border rounded-lg p-4 bg-muted/30 space-y-3'>
                <div className='flex items-center justify-between flex-wrap gap-2'>
                  <div className='flex items-center gap-2'>
                    <LayoutDashboard className='w-4 h-4 text-muted-foreground' />
                    <span className='text-sm font-semibold'>Dispatch Cron Status</span>
                    {cronStatus && (
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        cronStatus.status === 'healthy' ? 'bg-green-100 text-green-700'
                        : cronStatus.last_run ? 'bg-yellow-100 text-yellow-700'
                        : 'bg-red-100 text-red-700'
                      }`}>
                        {cronStatus.status === 'healthy' ? '● Healthy' : cronStatus.last_run ? '⚠ Overdue' : '✕ Never run'}
                      </span>
                    )}
                  </div>
                  <div className='flex gap-2'>
                    <button onClick={loadCronStatus}
                      className='text-xs border rounded px-2 py-1 hover:bg-muted'>
                      Refresh
                    </button>
                    <button onClick={handleTriggerDispatch} disabled={cronTriggerLoading}
                      className='text-xs bg-primary text-primary-foreground rounded px-3 py-1 disabled:opacity-50 flex items-center gap-1'>
                      {cronTriggerLoading && <Loader2 className='w-3 h-3 animate-spin' />}
                      Trigger Now
                    </button>
                  </div>
                </div>
                {cronStatus ? (
                  <div className='text-xs space-y-1 text-muted-foreground'>
                    <div><span className='font-medium text-foreground'>Last run:</span>{' '}
                      {cronStatus.last_run
                        ? `${cronStatus.minutes_ago} min ago — ${new Date(cronStatus.last_run).toLocaleString()}`
                        : 'Never ran'}
                    </div>
                    {cronStatus.last_result && (() => {
                      try {
                        const r = JSON.parse(cronStatus.last_result)
                        return (
                          <div className='space-y-0.5'>
                            <div><span className='font-medium text-foreground'>Interval used:</span> {r.interval_hours}h</div>
                            <div><span className='font-medium text-foreground'>Open RFQs found:</span> {r.open_rfqs_found ?? 0}</div>
                            <div><span className='font-medium text-foreground'>Dispatched:</span> {r.dispatched?.length ?? 0}</div>
                            <div><span className='font-medium text-foreground'>Skipped:</span>{' '}
                              {(r.skipped?.length ?? 0) > 0
                                ? r.skipped.map((s: {rfq_id: string; reason: string}) =>
                                    `${s.rfq_id.slice(0,8)}: ${s.reason}`).join(' | ')
                                : '0'}
                            </div>
                          </div>
                        )
                      } catch { return <div className='truncate'>{cronStatus.last_result?.slice(0,300)}</div> }
                    })()}
                  </div>
                ) : (
                  <p className='text-xs text-muted-foreground'>Loading…</p>
                )}
                {cronTriggerResult && (
                  <p className={`text-xs font-medium ${
                    cronTriggerResult.startsWith('Error') ? 'text-red-600' : 'text-green-600'
                  }`}>{cronTriggerResult}</p>
                )}
              </div>

              <FieldRow
                label='RFQ Closed Message'
                fieldName='rfq_closed_message'
                value={form.rfq_closed_message}
                onChange={handleChange}
                isSet={isFieldSet('rfq_closed_message')}
                placeholder='This RFQ is no longer accepting quotes.'
                hint='Message shown to providers when an RFQ is closed.'
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Save Button ── */}
      <div className='flex justify-end pt-2'>
        <Button onClick={handleSave} disabled={saving} className='min-w-[140px]'>
          {saving ? (
            <>
              <Loader2 className='w-4 h-4 animate-spin mr-2' />
              Saving...
            </>
          ) : (
            'Save Configuration'
          )}
        </Button>
      </div>
    </div>
  )
}
