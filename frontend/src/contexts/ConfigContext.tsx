'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

export interface ApiConfig {
  openaiApiKey: string;
  openaiBaseUrl: string;
  embeddingModel: string;
  completionModel: string;
  stripeSecretKey: string;
  stripePublishableKey: string;
  stripeWebhookSecret: string;
  awsAccessKey: string;
  awsSecretKey: string;
  awsRegion: string;
  awsS3Bucket: string;
  resendApiKey: string;
  signrequestApiKey: string;
  deepinfraApiKey: string;
}

interface ConfigContextType {
  config: ApiConfig;
  updateConfig: (newConfig: Partial<ApiConfig>) => void;
  isConfigured: boolean;
  missingServices: string[];
  showSetup: boolean;
  setShowSetup: (show: boolean) => void;
  validateConfig: () => { valid: boolean; errors: string[] };
}

const defaultConfig: ApiConfig = {
  openaiApiKey: '',
  openaiBaseUrl: 'https://api.deepinfra.com/v1/openai',
  embeddingModel: 'text-embedding-3-small',
  completionModel: 'moonshotai/kimi-k2.5',
  stripeSecretKey: '',
  stripePublishableKey: '',
  stripeWebhookSecret: '',
  awsAccessKey: '',
  awsSecretKey: '',
  awsRegion: 'us-east-1',
  awsS3Bucket: '',
  resendApiKey: '',
  signrequestApiKey: '',
  deepinfraApiKey: '',
};

const ConfigContext = createContext<ConfigContextType | undefined>(undefined);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<ApiConfig>(defaultConfig);
  const [showSetup, setShowSetup] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    // Load config from localStorage
    const saved = localStorage.getItem('proready_config');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setConfig({ ...defaultConfig, ...parsed });
      } catch (e) {
        console.error('Failed to parse config:', e);
      }
    }
    setIsLoaded(true);
  }, []);

  useEffect(() => {
    if (isLoaded) {
      localStorage.setItem('proready_config', JSON.stringify(config));
    }
  }, [config, isLoaded]);

  const updateConfig = (newConfig: Partial<ApiConfig>) => {
    setConfig(prev => ({ ...prev, ...newConfig }));
  };

  const validateConfig = () => {
    const errors: string[] = [];
    
    // DeepInfra/OpenAI is required for search
    if (!config.deepinfraApiKey && !config.openaiApiKey) {
      errors.push('DeepInfra API Key is required for AI search');
    }
    
    // Stripe keys should all be present or all absent
    const hasStripe = config.stripeSecretKey || config.stripePublishableKey;
    if (hasStripe && (!config.stripeSecretKey || !config.stripePublishableKey)) {
      errors.push('Both Stripe Secret and Publishable keys are required');
    }
    
    return { valid: errors.length === 0, errors };
  };

  const missingServices = [];
  if (!config.deepinfraApiKey && !config.openaiApiKey) {
    missingServices.push('AI Search (DeepInfra)');
  }
  if (!config.stripeSecretKey) {
    missingServices.push('Payments (Stripe)');
  }
  if (!config.resendApiKey) {
    missingServices.push('Email (Resend)');
  }
  if (!config.awsAccessKey) {
    missingServices.push('File Storage (AWS S3)');
  }
  if (!config.signrequestApiKey) {
    missingServices.push('Document Signing (SignRequest)');
  }

  const isConfigured = missingServices.length === 0;

  // Show setup on first load if not fully configured
  useEffect(() => {
    if (isLoaded && !isConfigured && !localStorage.getItem('proready_setup_dismissed')) {
      setShowSetup(true);
    }
  }, [isLoaded, isConfigured]);

  return (
    <ConfigContext.Provider
      value={{
        config,
        updateConfig,
        isConfigured,
        missingServices,
        showSetup,
        setShowSetup,
        validateConfig,
      }}
    >
      {children}
    </ConfigContext.Provider>
  );
}

export function useConfig() {
  const context = useContext(ConfigContext);
  if (context === undefined) {
    throw new Error('useConfig must be used within a ConfigProvider');
  }
  return context;
}
