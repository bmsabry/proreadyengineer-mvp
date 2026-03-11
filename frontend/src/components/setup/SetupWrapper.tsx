'use client';

import { useConfig } from '@/contexts/ConfigContext';
import { useAuth } from '@/contexts/AuthContext';
import { SetupWizard } from './SetupWizard';

export function SetupWrapper() {
  const { showSetup, setShowSetup } = useConfig();
  const { hasRole, isLoading } = useAuth();

  // SECURITY: Only show setup wizard to authenticated admin users
  if (isLoading || !hasRole('admin')) {
    return null;
  }

  // Hide setup wizard when explicitly dismissed
  if (!showSetup) {
    return null;
  }

  return <SetupWizard onClose={() => setShowSetup(false)} />;
}
