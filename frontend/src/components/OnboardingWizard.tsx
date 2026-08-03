import { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Brain, Lightbulb, Loader2, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  fetchOnboardingInterests,
  fetchOnboardingSourceRecommendations,
  saveOnboardingInterests,
} from '@/api';
import type { OnboardingSourceRecommendation } from '@/types';
import { trackFeature } from '@/lib/analytics';

interface Props {
  open: boolean;
  onClose: () => void;
}

type Step = 'interests' | 'recommendations' | 'workflow';

export function OnboardingWizard({ open, onClose }: Props) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>('interests');
  const [selectedInterests, setSelectedInterests] = useState<Set<string>>(new Set());
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(new Set());
  const didPreselect = useRef(false);

  const { data: interests, isLoading: loadingInterests } = useQuery({
    queryKey: ['onboarding-interests'],
    queryFn: fetchOnboardingInterests,
    enabled: open,
    staleTime: Infinity,
  });

  const { data: recommendations = [], isLoading: loadingRecs } = useQuery({
    queryKey: ['onboarding-recommendations', [...selectedInterests].sort().join(',')],
    queryFn: () => fetchOnboardingSourceRecommendations([...selectedInterests]),
    enabled: step === 'recommendations' && selectedInterests.size > 0,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (step === 'recommendations' && !didPreselect.current && recommendations.length > 0) {
      didPreselect.current = true;
      setSelectedSlugs(new Set(recommendations.filter((r) => r.recommended).map((r) => r.slug)));
    }
  }, [step, recommendations]);

  useEffect(() => {
    if (step === 'workflow') {
      trackFeature('onboarding_ai_workflow_impression');
    }
  }, [step]);

  const saveMutation = useMutation({
    mutationFn: saveOnboardingInterests,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['sources'] });
      setStep('workflow');
    },
  });

  function toggleInterest(id: string) {
    setSelectedInterests((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSlug(slug: string) {
    setSelectedSlugs((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  function handleApply() {
    const disabledSlugs = recommendations
      .map((rec) => rec.slug)
      .filter((slug) => !selectedSlugs.has(slug));
    saveMutation.mutate({
      interests: [...selectedInterests],
      enabled_source_slugs: [...selectedSlugs],
      disabled_source_slugs: disabledSlugs,
    });
  }

  function handleSkip() {
    onClose();
  }

  function handleBack() {
    setStep('interests');
  }

  function handleGoToRecommendations() {
    didPreselect.current = false;
    setStep('recommendations');
  }

  function handleWorkflowAction(route: '/today' | '/brief', event: string) {
    trackFeature(event);
    onClose();
    void navigate(route);
  }

  const isLoading =
    step === 'interests' ? loadingInterests : step === 'recommendations' && loadingRecs;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) onClose();
      }}
    >
      <DialogContent className="max-w-lg w-full">
        <DialogHeader>
          <DialogTitle>
            {step === 'interests'
              ? 'What are you interested in?'
              : step === 'recommendations'
                ? 'Recommended sources'
                : t('onboarding.workflow.title')}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-12" data-testid="onboarding-loading">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : step === 'interests' ? (
          <InterestStep
            interests={interests ?? []}
            selected={selectedInterests}
            onToggle={toggleInterest}
          />
        ) : step === 'recommendations' ? (
          <RecommendationsStep
            recommendations={recommendations}
            selected={selectedSlugs}
            onToggle={toggleSlug}
            loading={loadingRecs}
          />
        ) : (
          <WorkflowStep />
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          {step === 'interests' ? (
            <>
              <Button variant="ghost" size="sm" onClick={handleSkip}>
                Skip for now
              </Button>
              <Button
                size="sm"
                disabled={selectedInterests.size === 0 || loadingInterests}
                onClick={handleGoToRecommendations}
              >
                Next
              </Button>
            </>
          ) : step === 'recommendations' ? (
            <>
              <Button variant="ghost" size="sm" onClick={handleBack}>
                Back
              </Button>
              <Button
                size="sm"
                disabled={saveMutation.isPending || loadingRecs}
                onClick={handleApply}
              >
                {saveMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : 'Apply'}
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleWorkflowAction('/brief', 'onboarding_ai_workflow_brief')}
              >
                {t('onboarding.workflow.briefAction')}
              </Button>
              <Button
                size="sm"
                autoFocus
                onClick={() => handleWorkflowAction('/today', 'onboarding_ai_workflow_today')}
              >
                {t('onboarding.workflow.todayAction')}
              </Button>
            </>
          )}
        </DialogFooter>

        {saveMutation.isError && (
          <p className="text-xs text-destructive text-center -mt-2">
            Failed to save. Please try again.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}

function WorkflowStep() {
  const { t } = useTranslation();
  const outcomes = [
    { key: 'find', icon: Search },
    { key: 'understand', icon: Lightbulb },
    { key: 'remember', icon: Brain },
  ] as const;

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t('onboarding.workflow.promise')}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        {outcomes.map(({ key, icon: Icon }) => (
          <section key={key} className="rounded-md border bg-surface/50 p-3">
            <Icon className="mb-2 size-4 text-primary" aria-hidden="true" />
            <h3 className="text-sm font-medium">{t(`onboarding.workflow.${key}.title`)}</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {t(`onboarding.workflow.${key}.description`)}
            </p>
          </section>
        ))}
      </div>
      <p className="rounded-md bg-surface-2 px-3 py-2 text-xs text-muted-foreground">
        {t('onboarding.workflow.configuration')}
      </p>
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

interface InterestStepProps {
  interests: { id: string; label: string; description: string }[];
  selected: Set<string>;
  onToggle: (id: string) => void;
}

function InterestStep({ interests, selected, onToggle }: InterestStepProps) {
  if (interests.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No interest categories available.
      </p>
    );
  }
  return (
    <div className="grid gap-2 max-h-72 overflow-y-auto pr-1">
      {interests.map((interest) => {
        const isSelected = selected.has(interest.id);
        return (
          <button
            key={interest.id}
            onClick={() => onToggle(interest.id)}
            className={cn(
              'flex flex-col gap-0.5 rounded-md border px-3 py-2.5 text-left transition-colors',
              isSelected
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-border bg-background text-foreground hover:bg-surface'
            )}
          >
            <span className="text-sm font-medium">{interest.label}</span>
            {interest.description && (
              <span className="text-xs text-muted-foreground">{interest.description}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

interface RecommendationsStepProps {
  recommendations: OnboardingSourceRecommendation[];
  selected: Set<string>;
  onToggle: (slug: string) => void;
  loading: boolean;
}

function RecommendationsStep({
  recommendations,
  selected,
  onToggle,
  loading,
}: RecommendationsStepProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (recommendations.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No recommendations for your selected interests.
      </p>
    );
  }
  return (
    <div className="grid gap-2 max-h-72 overflow-y-auto pr-1">
      {recommendations.map((rec) => {
        const isSelected = selected.has(rec.slug);
        return (
          <button
            key={rec.slug}
            onClick={() => onToggle(rec.slug)}
            className={cn(
              'flex flex-col gap-0.5 rounded-md border px-3 py-2.5 text-left transition-colors',
              isSelected
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-border bg-background text-foreground hover:bg-surface'
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{rec.name}</span>
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide shrink-0">
                {rec.category}
              </span>
            </div>
            {rec.reason && <span className="text-xs text-muted-foreground">{rec.reason}</span>}
            {rec.matched_interests.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {rec.matched_interests.map((id) => (
                  <span
                    key={id}
                    className="inline-block rounded-sm bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                  >
                    {id}
                  </span>
                ))}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
