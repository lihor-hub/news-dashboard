import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/auth';
import { startActivity } from '@/lib/activity';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useWhatsNew } from '@/hooks/useWhatsNew';
import { useOnboardingWizard } from '@/hooks/useOnboardingWizard';
import {
  claimDailyWelcome,
  fetchDailyStreak,
  fetchProgressPreferences,
  recordDailyVisit,
  type DailyStreak,
} from '@/api/progress';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';

const WhatsNewDialog = lazy(() =>
  import('./WhatsNewDialog').then((m) => ({ default: m.WhatsNewDialog }))
);
const OnboardingWizard = lazy(() =>
  import('./OnboardingWizard').then((m) => ({ default: m.OnboardingWizard }))
);

export function SevenDayStrip({ daily }: { daily: DailyStreak }) {
  return (
    <ol className="grid grid-cols-7 gap-1" aria-label={`Seven days in ${daily.timezone}`}>
      {daily.seven_days.map((day) => (
        <li key={day.date} className="rounded border p-1 text-center text-xs">
          <time dateTime={day.date}>{day.date.slice(5)}</time>
          <span
            className="block"
            aria-label={
              day.credited
                ? 'Credited visit'
                : day.visited
                  ? 'Visited; timezone credit guard'
                  : 'No visit'
            }
          >
            {day.credited ? '✓' : day.visited ? '○' : '–'}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** One protected host covers shell and standalone readers; server owns dates and claims. */
export function DailyProgress({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const accountId = user!.id;
  const location = useLocation();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const { data: daily } = useQuery({
    queryKey: ['daily-streak', accountId],
    queryFn: fetchDailyStreak,
    enabled: false, // Observe POSTs and home refreshes without creating a second recorder.
  });
  const [welcome, setWelcome] = useState<DailyStreak | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const [otherDialog, setOtherDialog] = useState(false);
  const indicator = useRef<HTMLAnchorElement>(null);
  const continueButton = useRef<HTMLButtonElement>(null);
  const priorFocus = useRef<HTMLElement | null>(null);
  const viewProgress = useRef(false);
  const claimed = useRef(new Set<string>());
  const desktop = useMediaQuery('(min-width: 640px)');
  const whatsNew = useWhatsNew();
  const onboarding = useOnboardingWizard();
  const pref = useQuery({
    queryKey: ['progress-preferences', accountId],
    queryFn: fetchProgressPreferences,
  });

  useEffect(
    () =>
      startActivity(() => {
        void cache.invalidateQueries({ queryKey: ['activity', accountId] });
        void cache.invalidateQueries({ queryKey: ['progress-rewards', accountId] });
      }),
    [accountId, cache]
  );

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setOtherDialog(!!document.querySelector('[role="dialog"]:not([data-daily-welcome])'));
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['role'],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const resume = () => {
      if (document.visibilityState === 'visible') setRevision((v) => v + 1);
    };
    document.addEventListener('visibilitychange', resume);
    window.addEventListener('focus', resume);
    window.addEventListener('pageshow', resume);
    window.addEventListener('online', resume);
    return () => {
      document.removeEventListener('visibilitychange', resume);
      window.removeEventListener('focus', resume);
      window.removeEventListener('pageshow', resume);
      window.removeEventListener('online', resume);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function visit(retry = true) {
      if (document.visibilityState !== 'visible') return;
      try {
        const result = await recordDailyVisit();
        if (cancelled) return;
        setFailed(false);
        cache.setQueryData(['daily-streak', accountId], result);
        void cache.invalidateQueries({ queryKey: ['progress-rewards', accountId] });
      } catch {
        if (cancelled) return;
        setFailed(true);
        if (retry) timer = setTimeout(() => void visit(false), 5000);
      }
    }
    void visit();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [accountId, location.pathname, location.search, location.hash, revision, cache]);

  useEffect(() => {
    if (!daily?.available) return;
    const delay = Math.max(
      100,
      Date.parse(daily.next_local_boundary_at) - Date.parse(daily.server_now) + 50
    );
    const timer = setTimeout(
      () => {
        if (document.visibilityState === 'visible') setRevision((v) => v + 1);
      },
      Math.min(delay, 2147483647)
    );
    return () => clearTimeout(timer);
  }, [daily]);

  useEffect(() => {
    if (pref.data?.daily_welcome_enabled === false || otherDialog) setWelcome(null);
  }, [pref.data?.daily_welcome_enabled, otherDialog]);

  useEffect(() => {
    const target = daily?.welcome_target?.expected_visit_date;
    if (
      !target ||
      !pref.data?.daily_welcome_enabled ||
      !onboarding.ready ||
      onboarding.open ||
      !whatsNew.ready ||
      whatsNew.open ||
      otherDialog ||
      welcome ||
      claimed.current.has(target) ||
      document.visibilityState !== 'visible'
    )
      return;
    let cancelled = false;
    claimed.current.add(target);
    void claimDailyWelcome(target)
      .then((envelope) => {
        if (
          cancelled ||
          !envelope.show ||
          !envelope.authorization.welcome ||
          !envelope.welcome ||
          document.visibilityState !== 'visible' ||
          document.querySelector('[role="dialog"]')
        )
          return;
        priorFocus.current =
          document.activeElement instanceof HTMLElement && document.activeElement !== document.body
            ? document.activeElement
            : null;
        viewProgress.current = false;
        setWelcome(envelope.welcome);
      })
      .catch(() => {
        /* Consume-on-claim: a lost response must never re-authorize display. */
      });
    return () => {
      cancelled = true;
    };
  }, [
    daily,
    pref.data,
    onboarding.ready,
    onboarding.open,
    whatsNew.ready,
    whatsNew.open,
    otherDialog,
    welcome,
    revision,
  ]);

  const Root = desktop ? Dialog : Sheet;
  const Title = desktop ? DialogTitle : SheetTitle;
  const Description = desktop ? DialogDescription : SheetDescription;
  const Content = desktop ? DialogContent : SheetContent;
  const animated = pref.data?.reward_animations_enabled !== false;
  const modalProps = {
    'data-daily-welcome': '',
    className: `daily-welcome space-y-4 ${animated ? '' : 'progress-static'}`,
    onOpenAutoFocus: (event: Event) => {
      event.preventDefault();
      continueButton.current?.focus();
    },
    onCloseAutoFocus: (event: Event) => {
      event.preventDefault();
      if (
        !viewProgress.current &&
        !document.querySelector('[role="dialog"]:not([data-daily-welcome])')
      )
        (priorFocus.current?.isConnected ? priorFocus.current : indicator.current)?.focus();
    },
  };
  return (
    <>
      {children}
      {daily?.available && (
        <Link
          ref={indicator}
          to="/reading-dna#progress"
          aria-label={`Daily streak: ${daily.current_streak_days} days. View my progress`}
          className="fixed bottom-[max(5rem,env(safe-area-inset-bottom))] end-4 z-40 rounded-full border bg-background px-3 py-2 text-sm shadow-sm md:bottom-4"
        >
          Daily streak · {daily.current_streak_days}
          {failed ? ' · reconnecting' : ''}
        </Link>
      )}
      {!daily && failed && (
        <Link
          to="/reading-dna#progress"
          className="fixed bottom-20 end-4 z-40 rounded border bg-background p-2 text-sm"
        >
          Progress unavailable
        </Link>
      )}
      <Suspense fallback={null}>
        <OnboardingWizard open={onboarding.open} onClose={onboarding.skip} />
        <WhatsNewDialog
          state={{ ...whatsNew, open: onboarding.ready && !onboarding.open && whatsNew.open }}
        />
      </Suspense>
      <Root
        open={!!welcome}
        onOpenChange={(open) => {
          if (!open) setWelcome(null);
        }}
      >
        <Content {...modalProps} {...(!desktop ? { side: 'bottom' as const } : {})}>
          <Title>
            {welcome?.visit_kind === 'first'
              ? 'Welcome! A new streak starts here.'
              : welcome?.visit_kind === 'restart'
                ? 'Welcome back. A fresh start.'
                : 'Welcome back. Another day of curiosity.'}
          </Title>
          <Description>
            Your daily visits, not your reading total. Saved timezone: {welcome?.timezone}.
          </Description>
          {welcome && (
            <>
              <p>
                Daily streak: <strong>{welcome.current_streak_days} days</strong> · Personal best:{' '}
                {welcome.best_streak_days} days
              </p>
              <SevenDayStrip daily={welcome} />
            </>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => {
                viewProgress.current = true;
                setWelcome(null);
                void navigate('/reading-dna#progress');
              }}
            >
              View my progress
            </Button>
            <Button ref={continueButton} variant="outline" onClick={() => setWelcome(null)}>
              Continue reading
            </Button>
          </div>
        </Content>
      </Root>
    </>
  );
}
