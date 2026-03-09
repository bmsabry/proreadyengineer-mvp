'use client';

import { useState } from 'react';
import { useConfig } from '@/contexts/ConfigContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AlertCircle, Check, Key, Mail, CreditCard, Database, PenTool, Settings, X } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface SetupWizardProps {
  onClose?: () => void;
}

export function SetupWizard({ onClose }: SetupWizardProps) {
  const { config, updateConfig, validateConfig, missingServices } = useConfig();
  const [activeTab, setActiveTab] = useState('ai');
  const [saved, setSaved] = useState(false);
  const [localConfig, setLocalConfig] = useState(config);

  const handleSave = () => {
    updateConfig(localConfig);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleDismiss = () => {
    localStorage.setItem('proready_setup_dismissed', 'true');
    if (onClose) onClose();
  };

  const updateField = (field: keyof typeof localConfig, value: string) => {
    setLocalConfig(prev => ({ ...prev, [field]: value }));
  };

  const { valid, errors } = validateConfig();
  const hasMissingAI = missingServices.includes('AI Search (DeepInfra)');
  const hasMissingStripe = missingServices.includes('Payments (Stripe)');
  const hasMissingEmail = missingServices.includes('Email (Resend)');
  const hasMissingStorage = missingServices.includes('File Storage (AWS S3)');
  const hasMissingSign = missingServices.includes('Document Signing (SignRequest)');

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-2xl max-h-[90vh] overflow-auto">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center gap-2">
                <Key className="h-6 w-6" />
                API Configuration Setup
              </CardTitle>
              <CardDescription className="mt-2">
                Configure your API keys to enable all features. You can skip this and configure later in Admin Settings.
              </CardDescription>
            </div>
            {onClose && (
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </CardHeader>
        
        <CardContent>
          {missingServices.length > 0 && (
            <Alert className="mb-4" variant="warning">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Missing configuration for: {missingServices.join(', ')}
              </AlertDescription>
            </Alert>
          )}

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid grid-cols-5 w-full">
              <TabsTrigger value="ai" className={hasMissingAI ? 'text-red-500' : ''}>
                AI
              </TabsTrigger>
              <TabsTrigger value="payments" className={hasMissingStripe ? 'text-red-500' : ''}>
                Payments
              </TabsTrigger>
              <TabsTrigger value="email" className={hasMissingEmail ? 'text-red-500' : ''}>
                Email
              </TabsTrigger>
              <TabsTrigger value="storage" className={hasMissingStorage ? 'text-red-500' : ''}>
                Storage
              </TabsTrigger>
              <TabsTrigger value="signing" className={hasMissingSign ? 'text-red-500' : ''}>
                Signing
              </TabsTrigger>
            </TabsList>

            {/* AI Configuration */}
            <TabsContent value="ai" className="space-y-4">
              <div className="flex items-center gap-2 text-lg font-semibold">
                <Key className="h-5 w-5" />
                DeepInfra AI Configuration
              </div>
              <div className="space-y-2">
                <Label htmlFor="deepinfra-key">
                  DeepInfra API Key {hasMissingAI && <span className="text-red-500">*</span>}
                </Label>
                <Input
                  id="deepinfra-key"
                  type="password"
                  placeholder="sk-..."
                  value={localConfig.deepinfraApiKey}
                  onChange={(e) => updateField('deepinfraApiKey', e.target.value)}
                />
                <p className="text-sm text-muted-foreground">
                  Get your key from <a href="https://deepinfra.com/dash/api_keys" target="_blank" className="underline">deepinfra.com/dash/api_keys</a>
                </p>
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
                <p className="text-sm text-muted-foreground">
                  Recommended: moonshotai/kimi-k2.5
                </p>
              </div>
            </TabsContent>

            {/* Payments Configuration */}
            <TabsContent value="payments" className="space-y-4">
              <div className="flex items-center gap-2 text-lg font-semibold">
                <CreditCard className="h-5 w-5" />
                Stripe Payment Configuration
              </div>
              <div className="space-y-2">
                <Label htmlFor="stripe-secret">Stripe Secret Key</Label>
                <Input
                  id="stripe-secret"
                  type="password"
                  placeholder="sk_test_... or sk_live_..."
                  value={localConfig.stripeSecretKey}
                  onChange={(e) => updateField('stripeSecretKey', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="stripe-publishable">Stripe Publishable Key</Label>
                <Input
                  id="stripe-publishable"
                  placeholder="pk_test_... or pk_live_..."
                  value={localConfig.stripePublishableKey}
                  onChange={(e) => updateField('stripePublishableKey', e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="stripe-webhook">Stripe Webhook Secret</Label>
                <Input
                  id="stripe-webhook"
                  type="password"
                  placeholder="whsec_..."
                  value={localConfig.stripeWebhookSecret}
                  onChange={(e) => updateField('stripeWebhookSecret', e.target.value)}
                />
              </div>
            </TabsContent>

            {/* Email Configuration */}
            <TabsContent value="email" className="space-y-4">
              <div className="flex items-center gap-2 text-lg font-semibold">
                <Mail className="h-5 w-5" />
                Resend Email Configuration
              </div>
              <div className="space-y-2">
                <Label htmlFor="resend-key">Resend API Key</Label>
                <Input
                  id="resend-key"
                  type="password"
                  placeholder="re_..."
                  value={localConfig.resendApiKey}
                  onChange={(e) => updateField('resendApiKey', e.target.value)}
                />
                <p className="text-sm text-muted-foreground">
                  Get your key from <a href="https://resend.com/api-keys" target="_blank" className="underline">resend.com</a>
                </p>
              </div>
            </TabsContent>

            {/* Storage Configuration */}
            <TabsContent value="storage" className="space-y-4">
              <div className="flex items-center gap-2 text-lg font-semibold">
                <Database className="h-5 w-5" />
                AWS S3 Storage Configuration
              </div>
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
            </TabsContent>

            {/* Document Signing Configuration */}
            <TabsContent value="signing" className="space-y-4">
              <div className="flex items-center gap-2 text-lg font-semibold">
                <PenTool className="h-5 w-5" />
                SignRequest Configuration
              </div>
              <div className="space-y-2">
                <Label htmlFor="signrequest-key">SignRequest API Key</Label>
                <Input
                  id="signrequest-key"
                  type="password"
                  value={localConfig.signrequestApiKey}
                  onChange={(e) => updateField('signrequestApiKey', e.target.value)}
                />
                <p className="text-sm text-muted-foreground">
                  Get your key from <a href="https://signrequest.com/api/" target="_blank" className="underline">signrequest.com</a>
                </p>
              </div>
            </TabsContent>
          </Tabs>

          {errors.length > 0 && (
            <Alert variant="destructive" className="mt-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <ul className="list-disc list-inside">
                  {errors.map((error, i) => (
                    <li key={i}>{error}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}
        </CardContent>

        <CardFooter className="flex justify-between">
          <Button variant="outline" onClick={handleDismiss}>
            Skip for Now
          </Button>
          <div className="flex gap-2">
            {saved && (
              <span className="flex items-center gap-1 text-green-600 text-sm">
                <Check className="h-4 w-4" />
                Saved
              </span>
            )}
            <Button onClick={handleSave}>
              Save Configuration
            </Button>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
