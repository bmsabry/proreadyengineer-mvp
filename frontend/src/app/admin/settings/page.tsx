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
  openai_embedding_model_set: boolean
  stripe_secret_key_set: boolean
  stripe_webhook_secret_set: boolean
  stripe_publishable_key: string
  stripe_publishable_key_set: boolean
  paypal_configured: boolean
  paypal_mode: string
  paypal_mode_set: boolean
  aws_access_key_set: boolean
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
]

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
  rfq_batch_size: '',
  rfq_batch_interval_hours: '',
  rfq_closed_message: '',
}

function populateFormFromConfig(cfg: ServerConfig): Partial<FormFields> {
  return {
    openai_api_base: cfg.openai_api_base || '',
    openai_llm_model: cfg.openai_llm_model || '',
    openai_embedding_model: cfg.openai_embedding_model || '',
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
      aws_secret_access_key: 'aws_access_key_set',
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
        <TabsContent value='ai'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Brain className='w-5 h-5' />
                AI / Search Configuration
              </CardTitle>
              <CardDescription>
                OpenAI API credentials for search embedding and LLM extraction.
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
                hint='Used for embeddings and LLM extraction.'
              />
              <FieldRow
                label='OpenAI API Base URL'
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
                hint='Model used for structured extraction from customer queries.'
              />
              <FieldRow
                label='Embedding Model'
                fieldName='openai_embedding_model'
                value={form.openai_embedding_model}
                onChange={handleChange}
                isSet={isFieldSet('openai_embedding_model')}
                placeholder='text-embedding-3-small'
                hint='Model used for provider and query embeddings.'
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
                label='PayPal Plan — Search Tier 2'
                fieldName='paypal_plan_search_tier2'
                value={form.paypal_plan_search_tier2}
                onChange={handleChange}
                isSet={isFieldSet('paypal_plan_search_tier2')}
                isSecret
                hint='Plan ID for 200 searches/month ($20/month).'
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
        </TabsContent>

        {/* ── Email ── */}
        <TabsContent value='email'>
          <Card>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <Mail className='w-5 h-5' />
                Email Configuration
              </CardTitle>
              <CardDescription>
                Resend API credentials for transactional email delivery.
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
                hint='API key for sending transactional emails via Resend.'
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
