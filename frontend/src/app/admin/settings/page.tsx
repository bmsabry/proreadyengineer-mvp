'use client';
export const dynamic = 'force-dynamic';
import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Key, CreditCard, Mail, Database, PenTool, Check, X, Loader2, AlertCircle, ExternalLink } from 'lucide-react';

interface ServerConfig {
  openai_api_key: string; openai_api_key_set: boolean;
  openai_api_base: string; openai_llm_model: string; openai_embedding_model: string;
  stripe_secret_key: string; stripe_secret_key_set: boolean; stripe_publishable_key: string;
  aws_access_key_id: string; aws_access_key_set: boolean; aws_region: string; aws_s3_bucket: string;
  resend_api_key: string; resend_api_key_set: boolean; resend_from_email?: string;
  signwell_api_key: string; signwell_api_key_set: boolean;
  signwell_template_id: string;
  source: string;
}
interface FormState {
  openai_api_key: string; openai_api_base: string; openai_llm_model: string; openai_embedding_model: string;
  stripe_secret_key: string; stripe_publishable_key: string; stripe_webhook_secret: string;
  aws_access_key_id: string; aws_secret_access_key: string; aws_region: string; aws_s3_bucket: string;
  resend_api_key: string; resend_from_email: string;
  signwell_api_key: string; signwell_template_id: string;
}
const EMPTY_FORM: FormState = {
  openai_api_key:'',openai_api_base:'',openai_llm_model:'',openai_embedding_model:'',
  stripe_secret_key:'',stripe_publishable_key:'',stripe_webhook_secret:'',
  aws_access_key_id:'',aws_secret_access_key:'',aws_region:'',aws_s3_bucket:'',
  resend_api_key:'',resend_from_email:'',
  signwell_api_key:'',signwell_template_id:'',
};

// Direct backend URL - do NOT use proxy (proxy can't forward auth cookies from backend domain)
const BACKEND_API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchServerConfig(): Promise<ServerConfig> {
  const res = await fetch(`${BACKEND_API}/api/v1/admin/config`, {
    credentials: 'include',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`Failed to load config: ${res.status}`);
  return res.json();
}

async function postServerConfig(data: Partial<FormState>): Promise<{ status: string; keys_saved: string[] }> {
  const payload: Record<string, string> = {};
  for (const [k, v] of Object.entries(data)) {
    if (v && (v as string).trim()) payload[k] = (v as string).trim();
  }
  const res = await fetch(`${BACKEND_API}/api/v1/admin/config`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as any).detail || `Save failed: ${res.status}`);
  }
  return res.json();
}

function SetBadge({ isSet }: { isSet: boolean }) {
  return isSet ? (
    <Badge className="bg-green-100 text-green-800 text-xs">
      <Check className="h-3 w-3 mr-1 inline" />Set
    </Badge>
  ) : (
    <Badge variant="secondary" className="text-xs">
      <X className="h-3 w-3 mr-1 inline" />Not set
    </Badge>
  );
}

function Field({ id, label, type = 'text', value, onChange, placeholder, hint }: {
  id: string; label: string; type?: string;
  value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string; hint?: string;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} value={value} onChange={onChange}
        placeholder={placeholder ?? ''} autoComplete="off" className="font-mono text-sm" />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

interface StatusDetail { label: string; value: string; }
function StatusCard({ title, icon: Icon, configured, description, details }: {
  title: string; icon: React.ElementType; configured: boolean;
  description: string; details: StatusDetail[];
}) {
  return (
    <Card className={configured ? 'border-green-200' : 'border-amber-200'}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4" />
            <CardTitle className="text-sm font-medium">{title}</CardTitle>
          </div>
          <SetBadge isSet={configured} />
        </div>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent className="pt-0 space-y-1">
        {details.map((d) => (
          <div key={d.label} className="flex justify-between text-xs gap-2">
            <span className="text-muted-foreground shrink-0">{d.label}:</span>
            <span className="font-mono truncate max-w-[180px] text-right">{d.value}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function AdminSettingsPage() {
  const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [savedKeys, setSavedKeys] = useState<string[]>([]);
  const [loadError, setLoadError] = useState('');

  const loadConfig = () => {
    setLoading(true);
    fetchServerConfig()
      .then((cfg) => {
        setServerConfig(cfg);
        setForm((f) => ({
          ...f,
          openai_api_base: cfg.openai_api_base || '',
          openai_llm_model: cfg.openai_llm_model || '',
          openai_embedding_model: cfg.openai_embedding_model || '',
          stripe_publishable_key: cfg.stripe_publishable_key || '',
          aws_region: cfg.aws_region || '',
          aws_s3_bucket: cfg.aws_s3_bucket || '',
          resend_from_email: cfg.resend_from_email || '',
          signwell_template_id: cfg.signwell_template_id || '',
        }));
        setLoadError('');
      })
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadConfig(); }, []);

  const set = (field: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSave = async () => {
    setSaving(true); setSaveError(''); setSavedKeys([]);
    try {
      const result = await postServerConfig(form);
      setSavedKeys(result.keys_saved);
      const updated = await fetchServerConfig();
      setServerConfig(updated);
      setForm((f) => ({
        ...f,
        openai_api_key: '', stripe_secret_key: '', stripe_webhook_secret: '',
        aws_access_key_id: '', aws_secret_access_key: '',
        resend_api_key: '',
        signwell_api_key: '',
      }));
    } catch (e: any) {
      setSaveError(e.message);
    } finally { setSaving(false); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading configuration...</span>
      </div>
    );
  }

  const aiConfigured     = serverConfig?.openai_api_key_set      ?? false;
  const stripeConfigured = serverConfig?.stripe_secret_key_set   ?? false;
  const awsConfigured    = serverConfig?.aws_access_key_set      ?? false;
  const resendConfigured = serverConfig?.resend_api_key_set      ?? false;
  const signConfigured   = serverConfig?.signwell_api_key_set    ?? false;
  const allConfigured    = aiConfigured && stripeConfigured && awsConfigured && resendConfigured;
  const missingCount     = [aiConfigured,stripeConfigured,awsConfigured,resendConfigured,signConfigured].filter(x=>!x).length;

  return (
    <div className="container mx-auto py-8 px-4 max-w-5xl">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-3xl font-bold">System Settings</h1>
          <p className="text-muted-foreground mt-1">Keys stored in DB — no restart needed.</p>
        </div>
        <div className="mt-1">
          {allConfigured
            ? <Badge className="bg-green-100 text-green-800"><Check className="h-3 w-3 mr-1" />Fully Configured</Badge>
            : <Badge variant="destructive"><X className="h-3 w-3 mr-1" />{missingCount} service{missingCount !== 1 ? 's' : ''} missing</Badge>
          }
        </div>
      </div>

      {loadError && (
        <div className="mb-4 flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded p-3 text-sm">
          <AlertCircle className="h-4 w-4 shrink-0" />Could not load config from server: {loadError}
        </div>
      )}
      {savedKeys.length > 0 && (
        <div className="mb-4 flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded p-3 text-sm">
          <Check className="h-4 w-4 shrink-0" />Saved to database: <span className="font-mono ml-1">{savedKeys.join(', ')}</span>
        </div>
      )}
      {saveError && (
        <div className="mb-4 flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded p-3 text-sm">
          <AlertCircle className="h-4 w-4 shrink-0" />Save failed: {saveError}
        </div>
      )}

      <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
        <strong>How this works:</strong> Enter new values and click <strong>Save to Database</strong>.
        Keys are stored in PostgreSQL and read by the backend at request time — no environment
        variable changes or server restarts required. Leave a field blank to keep its current value.
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="ai">AI / Search{!aiConfigured && <span className="ml-1 text-red-500">●</span>}</TabsTrigger>
          <TabsTrigger value="payments">Payments{!stripeConfigured && <span className="ml-1 text-red-500">●</span>}</TabsTrigger>
          <TabsTrigger value="email">Email{!resendConfigured && <span className="ml-1 text-red-500">●</span>}</TabsTrigger>
          <TabsTrigger value="storage">Storage{!awsConfigured && <span className="ml-1 text-red-500">●</span>}</TabsTrigger>
          <TabsTrigger value="signing">Document Signing{!signConfigured && <span className="ml-1 text-amber-500">●</span>}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <StatusCard title="AI / Search" icon={Key} configured={aiConfigured}
              description="OpenAI-compatible API for embeddings & completions"
              details={[
                { label: 'API Key', value: serverConfig?.openai_api_key || 'Not set' },
                { label: 'Base URL', value: serverConfig?.openai_api_base || '—' },
                { label: 'LLM Model', value: serverConfig?.openai_llm_model || '—' },
                { label: 'Embed Model', value: serverConfig?.openai_embedding_model || '—' },
              ]} />
            <StatusCard title="Payments" icon={CreditCard} configured={stripeConfigured}
              description="Stripe for subscriptions and one-time payments"
              details={[
                { label: 'Secret Key', value: serverConfig?.stripe_secret_key || 'Not set' },
                { label: 'Publishable Key', value: serverConfig?.stripe_publishable_key ? serverConfig.stripe_publishable_key.slice(0,20)+'...' : 'Not set' },
              ]} />
            <StatusCard title="Email" icon={Mail} configured={resendConfigured}
              description="Resend for transactional emails"
              details={[{ label: 'API Key', value: serverConfig?.resend_api_key || 'Not set' }]} />
            <StatusCard title="File Storage" icon={Database} configured={awsConfigured}
              description="AWS S3 for document uploads"
              details={[
                { label: 'Access Key', value: serverConfig?.aws_access_key_id || 'Not set' },
                { label: 'Region', value: serverConfig?.aws_region || '—' },
                { label: 'Bucket', value: serverConfig?.aws_s3_bucket || '—' },
              ]} />
            <StatusCard title="Document Signing" icon={PenTool} configured={signConfigured}
              description="Signwell for NDA embedded signing workflows"
              details={[
                { label: 'API Key', value: serverConfig?.signwell_api_key || 'Not set' },
                { label: 'Template ID', value: serverConfig?.signwell_template_id || '—' },
                { label: 'Callback URL', value: 'Configured in Signwell workspace' },
              ]} />
          </div>
        </TabsContent>

        <TabsContent value="ai" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Key className="h-5 w-5" />AI / Search Configuration</CardTitle>
              <CardDescription>OpenAI-compatible endpoint for intent extraction and vector embeddings.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Current status:</span>
                <SetBadge isSet={aiConfigured} />
              </div>
              <Field id="openai_api_key" label="API Key" type="password" value={form.openai_api_key}
                onChange={set('openai_api_key')} placeholder="sk-… or leave blank to keep existing"
                hint="Used for both LLM completions and vector embeddings." />
              <Field id="openai_api_base" label="API Base URL" value={form.openai_api_base}
                onChange={set('openai_api_base')} placeholder="https://api.deepinfra.com/v1/openai"
                hint="Leave blank for official OpenAI. Set to DeepInfra/other compatible endpoint." />
              <Field id="openai_llm_model" label="LLM Model" value={form.openai_llm_model}
                onChange={set('openai_llm_model')} placeholder="moonshotai/kimi-k2.5"
                hint="Used for structured intent extraction from search queries." />
              <Field id="openai_embedding_model" label="Embedding Model" value={form.openai_embedding_model}
                onChange={set('openai_embedding_model')} placeholder="BAAI/bge-large-en-v1.5"
                hint="Used for provider profile and query vector embeddings." />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="payments" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><CreditCard className="h-5 w-5" />Stripe Configuration</CardTitle>
              <CardDescription>Required for subscriptions, RFQ unlock fees, and NDA charges.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Current status:</span>
                <SetBadge isSet={stripeConfigured} />
              </div>
              <Field id="stripe_secret_key" label="Secret Key" type="password" value={form.stripe_secret_key}
                onChange={set('stripe_secret_key')} placeholder="sk_live_… or sk_test_…" />
              <Field id="stripe_publishable_key" label="Publishable Key" value={form.stripe_publishable_key}
                onChange={set('stripe_publishable_key')} placeholder="pk_live_… or pk_test_…" />
              <Field id="stripe_webhook_secret" label="Webhook Secret" type="password" value={form.stripe_webhook_secret}
                onChange={set('stripe_webhook_secret')} placeholder="whsec_…"
                hint="From Stripe webhook dashboard. Required for verified payment events." />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="email" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Mail className="h-5 w-5" />Email Configuration</CardTitle>
              <CardDescription>Resend API for transactional emails (RFQ notifications, account emails).</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Current status:</span>
                <SetBadge isSet={resendConfigured} />
              </div>
              <Field id="resend_api_key" label="Resend API Key" type="password" value={form.resend_api_key}
                onChange={set('resend_api_key')} placeholder="re_… or leave blank to keep existing" />
              <Field id="resend_from_email" label="From Email Address" value={form.resend_from_email ?? ''}
                onChange={set('resend_from_email')} placeholder="ProMechDirectory <info@ProMechDirectory.com>" />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="storage" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Database className="h-5 w-5" />AWS S3 Storage</CardTitle>
              <CardDescription>Required for RFQ document uploads and signed NDA storage.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Current status:</span>
                <SetBadge isSet={awsConfigured} />
              </div>
              <Field id="aws_access_key_id" label="Access Key ID" type="password" value={form.aws_access_key_id}
                onChange={set('aws_access_key_id')} placeholder="AKIA… or leave blank to keep existing" />
              <Field id="aws_secret_access_key" label="Secret Access Key" type="password" value={form.aws_secret_access_key}
                onChange={set('aws_secret_access_key')} placeholder="Leave blank to keep existing" />
              <Field id="aws_region" label="Region" value={form.aws_region}
                onChange={set('aws_region')} placeholder="us-east-1" />
              <Field id="aws_s3_bucket" label="S3 Bucket Name" value={form.aws_s3_bucket}
                onChange={set('aws_s3_bucket')} placeholder="proreadyengineer-uploads" />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="signing" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><PenTool className="h-5 w-5" />Signwell — Document Signing</CardTitle>
              <CardDescription>Signwell API for NDA embedded signing workflows. Used when customers require an NDA before RFQ dispatch.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Current status:</span>
                <SetBadge isSet={signConfigured} />
              </div>
              <div className="bg-blue-50 border border-blue-200 rounded p-3 text-xs text-blue-800">
                <strong>Setup:</strong> Create a free account at{' '}
                <a href="https://www.signwell.com" target="_blank" rel="noopener noreferrer"
                   className="underline inline-flex items-center gap-1">
                  signwell.com <ExternalLink className="h-3 w-3" />
                </a>
                , upload your NDA template, and copy the API key and Template ID here.
              </div>
              <Field id="signwell_api_key" label="Signwell API Key" type="password" value={form.signwell_api_key}
                onChange={set('signwell_api_key')} placeholder="Leave blank to keep existing"
                hint="Found in Signwell dashboard → Account → API Keys." />
              <Field id="signwell_template_id" label="NDA Template ID" value={form.signwell_template_id}
                onChange={set('signwell_template_id')} placeholder="e.g. abc123def456"
                hint="The Template ID of your uploaded NDA document in Signwell." />
              <div className="space-y-1">
                <label className="text-sm font-medium">Workspace Callback URL</label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-muted px-3 py-2 text-xs font-mono break-all">
                    {`${process.env.NEXT_PUBLIC_API_BASE_URL || ''}/api/v1/webhooks/signwell`}
                  </code>
                </div>
                <p className="text-xs text-muted-foreground">Add this URL to your Signwell workspace settings under &ldquo;Workspace Callback URL&rdquo;. Listens for <code>document_completed</code> and <code>document_signer_completed</code> events.</p>
              </div>
              <div className="grid grid-cols-3 gap-3 pt-2 text-xs">
                <div className="bg-gray-50 rounded p-2 text-center">
                  <div className="font-medium">API Key</div>
                  <div className="mt-1"><SetBadge isSet={signConfigured} /></div>
                </div>
                <div className="bg-gray-50 rounded p-2 text-center">
                  <div className="font-medium">Template ID</div>
                  <div className="mt-1">
                    {serverConfig?.signwell_template_id
                      ? <Badge className="bg-green-100 text-green-800 text-xs"><Check className="h-3 w-3 mr-1 inline" />Set</Badge>
                      : <Badge variant="secondary" className="text-xs"><X className="h-3 w-3 mr-1 inline" />Not set</Badge>
                    }
                  </div>
                </div>
                <div className="bg-gray-50 rounded p-2 text-center">
                  <div className="font-medium">Webhook</div>
                  <div className="mt-1 text-xs text-muted-foreground">See Callback URL above</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="mt-8 flex items-center justify-between border-t pt-6">
        <p className="text-sm text-muted-foreground">Only filled fields will be updated. Blank fields keep their current values.</p>
        <Button onClick={handleSave} disabled={saving} size="lg">
          {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving...</> : <><Check className="h-4 w-4 mr-2" />Save to Database</>}
        </Button>
      </div>
    </div>
  );
}
