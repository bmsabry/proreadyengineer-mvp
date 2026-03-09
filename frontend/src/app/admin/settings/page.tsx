'use client';

export const dynamic = 'force-dynamic';

import { useConfig } from '@/contexts/ConfigContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Key, CreditCard, Mail, Database, PenTool, Settings, Check, X, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { SetupWizard } from '@/components/setup/SetupWizard';

export default function AdminSettingsPage() {
  const { config, updateConfig, isConfigured, missingServices, validateConfig } = useConfig();
  const [showSetup, setShowSetup] = useState(false);
  const [saved, setSaved] = useState(false);
  const [localConfig, setLocalConfig] = useState(config);

  const handleSave = () => {
    updateConfig(localConfig);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const updateField = (field: keyof typeof localConfig, value: string) => {
    setLocalConfig(prev => ({ ...prev, [field]: value }));
  };

  const { valid, errors } = validateConfig();

  const maskKey = (key: string) => {
    if (!key) return 'Not set';
    if (key.length < 8) return '••••••••';
    return key.slice(0, 4) + '••••••••••••••••' + key.slice(-4);
  };

  return (
    <div className="container mx-auto py-8 px-4">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold">System Settings</h1>
          <p className="text-muted-foreground">Configure API keys and service integrations</p>
        </div>
        <div className="flex items-center gap-4">
          {isConfigured ? (
            <Badge className="bg-green-100 text-green-800">
              <Check className="h-3 w-3 mr-1" />
              Fully Configured
            </Badge>
          ) : (
            <Badge variant="destructive">
              <X className="h-3 w-3 mr-1" />
              {missingServices.length} services missing
            </Badge>
          )}
          <Button onClick={() => setShowSetup(true)}>
            <Key className="h-4 w-4 mr-2" />
            Configure APIs
          </Button>
        </div>
      </div>

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="ai">AI Search</TabsTrigger>
          <TabsTrigger value="payments">Payments</TabsTrigger>
          <TabsTrigger value="email">Email</TabsTrigger>
          <TabsTrigger value="storage">Storage</TabsTrigger>
          <TabsTrigger value="signing">Document Signing</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <ServiceCard
              title="AI Search"
              icon={Key}
              configured={!!config.deepinfraApiKey}
              description="DeepInfra API for embeddings and completions"
              details={[
                { label: 'API Key', value: maskKey(config.deepinfraApiKey) },
                { label: 'Base URL', value: config.openaiBaseUrl },
                { label: 'Model', value: config.completionModel },
              ]}
            />
            <ServiceCard
              title="Payments"
              icon={CreditCard}
              configured={!!config.stripeSecretKey}
              description="Stripe for payment processing"
              details={[
                { label: 'Secret Key', value: maskKey(config.stripeSecretKey) },
                { label: 'Publishable Key', value: maskKey(config.stripePublishableKey) },
                { label: 'Webhook Secret', value: config.stripeWebhookSecret ? 'Set' : 'Not set' },
              ]}
            />
            <ServiceCard
              title="Email"
              icon={Mail}
              configured={!!config.resendApiKey}
              description="Resend for transactional emails"
              details={[
                { label: 'API Key', value: maskKey(config.resendApiKey) },
              ]}
            />
            <ServiceCard
              title="File Storage"
              icon={Database}
              configured={!!config.awsAccessKey}
              description="AWS S3 for file uploads"
              details={[
                { label: 'Access Key', value: maskKey(config.awsAccessKey) },
                { label: 'Region', value: config.awsRegion },
                { label: 'Bucket', value: config.awsS3Bucket || 'Not set' },
              ]}
            />
            <ServiceCard
              title="Document Signing"
              icon={PenTool}
              configured={!!config.signrequestApiKey}
              description="SignRequest for NDAs"
              details={[
                { label: 'API Key', value: maskKey(config.signrequestApiKey) },
              ]}
            />
          </div>
        </TabsContent>

        <TabsContent value="ai" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                DeepInfra AI Configuration
              </CardTitle>
              <CardDescription>
                Configure AI search and embeddings using DeepInfra
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="deepinfra-key">DeepInfra API Key</Label>
                <Input
                  id="deepinfra-key"
                  type="password"
                  value={localConfig.deepinfraApiKey}
                  onChange={(e) => updateField('deepinfraApiKey', e.target.value)}
                  placeholder="sk-..."
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="base-url">API Base URL</Label>
                <Input
                  id="base-url"
                  value={localConfig.openaiBaseUrl}
                  onChange={(e) => updateField('openaiBaseUrl', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="completion-model">Completion Model</Label>
                <Input
                  id="completion-model"
                  value={localConfig.completionModel}
                  onChange={(e) => updateField('completionModel', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="embedding-model">Embedding Model</Label>
                <Input
                  id="embedding-model"
                  value={localConfig.embeddingModel}
                  onChange={(e) => updateField('embeddingModel', e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="payments" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CreditCard className="h-5 w-5" />
                Stripe Payment Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="stripe-secret">Stripe Secret Key</Label>
                <Input
                  id="stripe-secret"
                  type="password"
                  value={localConfig.stripeSecretKey}
                  onChange={(e) => updateField('stripeSecretKey', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="stripe-publishable">Stripe Publishable Key</Label>
                <Input
                  id="stripe-publishable"
                  value={localConfig.stripePublishableKey}
                  onChange={(e) => updateField('stripePublishableKey', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="stripe-webhook">Stripe Webhook Secret</Label>
                <Input
                  id="stripe-webhook"
                  type="password"
                  value={localConfig.stripeWebhookSecret}
                  onChange={(e) => updateField('stripeWebhookSecret', e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="email" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-5 w-5" />
                Resend Email Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="resend-key">Resend API Key</Label>
                <Input
                  id="resend-key"
                  type="password"
                  value={localConfig.resendApiKey}
                  onChange={(e) => updateField('resendApiKey', e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="storage" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5" />
                AWS S3 Storage Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="aws-key">AWS Access Key ID</Label>
                <Input
                  id="aws-key"
                  value={localConfig.awsAccessKey}
                  onChange={(e) => updateField('awsAccessKey', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="aws-secret">AWS Secret Access Key</Label>
                <Input
                  id="aws-secret"
                  type="password"
                  value={localConfig.awsSecretKey}
                  onChange={(e) => updateField('awsSecretKey', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="aws-region">AWS Region</Label>
                <Input
                  id="aws-region"
                  value={localConfig.awsRegion}
                  onChange={(e) => updateField('awsRegion', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="aws-bucket">S3 Bucket Name</Label>
                <Input
                  id="aws-bucket"
                  value={localConfig.awsS3Bucket}
                  onChange={(e) => updateField('awsS3Bucket', e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="signing" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PenTool className="h-5 w-5" />
                SignRequest Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="signrequest-key">SignRequest API Key</Label>
                <Input
                  id="signrequest-key"
                  type="password"
                  value={localConfig.signrequestApiKey}
                  onChange={(e) => updateField('signrequestApiKey', e.target.value)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {errors.length > 0 && (
        <Card className="mt-6 border-red-200">
          <CardHeader>
            <CardTitle className="text-red-600">Configuration Errors</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc list-inside text-red-600">
              {errors.map((error, i) => (
                <li key={i}>{error}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="mt-6 flex justify-end gap-2">
        {saved && (
          <span className="flex items-center gap-1 text-green-600">
            <Check className="h-4 w-4" />
            Saved successfully
          </span>
        )}
        <Button onClick={handleSave} size="lg">
          <RefreshCw className="h-4 w-4 mr-2" />
          Save All Changes
        </Button>
      </div>

      {showSetup && (
        <SetupWizard onClose={() => setShowSetup(false)} />
      )}
    </div>
  );
}

function ServiceCard({
  title,
  icon: Icon,
  configured,
  description,
  details,
}: {
  title: string;
  icon: React.ElementType;
  configured: boolean;
  description: string;
  details: { label: string; value: string }[];
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Icon className="h-5 w-5" />
            {title}
          </CardTitle>
          {configured ? (
            <Badge className="bg-green-100 text-green-800">Active</Badge>
          ) : (
            <Badge variant="secondary">Not Configured</Badge>
          )}
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="space-y-1">
          {details.map((detail, i) => (
            <div key={i} className="flex justify-between text-sm">
              <dt className="text-muted-foreground">{detail.label}:</dt>
              <dd className="font-mono">{detail.value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
