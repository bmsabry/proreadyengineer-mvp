'use client';

import { useConfig } from '@/contexts/ConfigContext';
import { SetupWizard } from './SetupWizard';

export function SetupWrapper() {
  const { showSetup, setShowSetup, isConfigured } = useConfig();

  // Hide setup wizard when explicitly dismissed
  if (!showSetup) {
    return null;
  }

  return <SetupWizard onClose={() => setShowSetup(false)} />;
}
