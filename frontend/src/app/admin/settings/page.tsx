'use client'
export const dynamic = 'force-dynamic'

import { useState, useEffect, useCallback } from 'react'
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
  doc_llm_api_key: string
  doc_llm_api_base: string
  doc_llm_model: string
  openai_embedding_model_set: boolean
  doc_llm_api_key_set: boolean
  doc_llm_api_base: string
  doc_llm_api_base_set: boolean
  doc_llm_model: string
  doc_llm_model_set: boolean
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
  stripe_secret_key: string
  stripe_publishable_key: string
  stripe_webhook_secret: string
  paypal_client_id: string
  paypal_client_secret: string
  paypal_mode: string
  paypal_webhook_id: string
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
  signwell_api_key: string
  signwell_template_id: string
  rfq_batch_size: string
  rfq_batch_interval_hours: string
  rfq_closed_message: string
}

const SECRET_FIELDS: (keyof FormFields)[] = [
  'openai_api_key', 'stripe_secret_key', 'stripe_webhook_secret',
  'paypal_client_id', 'paypal_client_secret', 'paypal_webhook_id',
  'paypal_plan_search_tier1', 'paypal_plan_search_tier2',
  'paypal_plan_provider_profile', 'paypal_plan_advertisement',
  'aws_access_key_id', 'aws_secret_access_key',
  'resend_api_key', 'signwell_api_key',
  'doc_llm_api_key',
]

const EMPTY_FORM: FormFields = {
  openai_api_key: '',
  openai_api_base: '',
  openai_llm_model: '',
  openai_embedding_model: '',
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
  rfq_batch_size: '',
  rfq_batch_interval_hours: '',
  rfq_closed_message: '',
}

function populateFormFromConfig(cfg: ServerConfig): Partial<FormFields> {
  return {
    openai_api_base: cfg.openai_api_base || '',
    openai_llm_model: cfg.openai_llm_model || '',
    openai_embedding_model: cfg.openai_embedding_model || '',
    doc_llm_api_base: cfg.doc_llm_api_base || '',
    doc_llm_model: cfg.doc_llm_model || '',
    stripe_publishable_key: cfg.stripe_publishable_key || '',
    paypal_mode: cfg.paypal_mode || '',
    aws_region: cfg.aws_region || '',
    aws_s3_bucket: cfg.aws_s3_bucket || '',
    resend_from_email: cfg.resend_from_email || '',
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

  function isFieldSet(fieldKey: keyof FormFields): boolean {
    if (!config) return false
    const boolMap: Record<string, string> = {
      openai_api_key: 'openai_api_key_set',
      openai_api_base: 'openai_api_base_set',
      openai_llm_model: 'openai_llm_model_set',
      openai_embedding_model: 'openai_embedding_model_set',
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
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
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
                label='OpenAI API Key'
                fieldName='openai_api_key'
                value={form.openai_api_key}
                onChange={handleChange}
                isSet={isFieldSet('openai_api_key')}
                isSecret
                hint='Shared key used for both embeddings (LLM 1) and firm ranking (LLM 2).'
              />
              <FieldRow
                label='Embedding Model'
                fieldName='openai_embedding_model'
                value={form.openai_embedding_model}
                onChange={handleChange}
                isSet={isFieldSet('openai_embedding_model')}
                placeholder='text-embedding-3-small'
                hint='Model used to generate vector embeddings for provider and query matching.'
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
                LLM used for the Pass 1 &amp; Pass 2 firm ranking pipeline — structured extraction from customer queries, specialty inference, and provider scoring. Uses the same API key as LLM 1.
              </CardDescription>
            </CardHeader>
            <CardContent className='space-y-4'>
              <FieldRow
                label='API Base URL'
                fieldName='openai_api_base'
                value={form.openai_api_base}
                onChange={handleChange}
                isSet={isFieldSet('openai_api_base')}
                placeholder='https://api.openai.com/v1'
                hint='Leave blank to use the default OpenAI endpoint.'
              />
              <FieldRow
                label='LLM Model'
                fieldName='openai_llm_model'
                value={form.openai_llm_model}
                onChange={handleChange}
                isSet={isFieldSet('openai_llm_model')}
                placeholder='gpt-4o'
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
