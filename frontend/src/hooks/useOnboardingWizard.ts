import { useCallback, useEffect, useState } from 'react';
import { fetchOnboardingStatus } from '@/api';

const SESSION_KEY = 'onboarding-skipped';

export interface OnboardingWizardState {
  open: boolean;
  ready: boolean;
  skip: () => void;
  openWizard: () => void;
  close: () => void;
}

export function useOnboardingWizard(): OnboardingWizardState {
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(!!sessionStorage.getItem(SESSION_KEY));

  useEffect(() => {
    if (sessionStorage.getItem(SESSION_KEY)) return;
    let cancelled = false;
    fetchOnboardingStatus()
      .then((status) => {
        if (cancelled) return;
        if (!status.completed) setOpen(true);
      })
      .catch(() => {
        // non-critical, stay closed
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const skip = useCallback(() => {
    sessionStorage.setItem(SESSION_KEY, '1');
    setOpen(false);
  }, []);

  const openWizard = useCallback(() => {
    setOpen(true);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
  }, []);

  return { open, ready, skip, openWizard, close };
}
