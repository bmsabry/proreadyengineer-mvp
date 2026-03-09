'use client';

import { useConfig } from '@/contexts/ConfigContext';
import { SetupWizard } from './SetupWizard';

export function SetupWrapper() {
  const { showSetup, setShowSetup, isConfigured } = useConfig();

  // Only show setup wizard if it's explicitly shown or not fully configured
  if (!showSetup && isConfigured) {
    return null;
  }

  return <SetupWizard onClose={() => setShowSetup(false)} />;
}
