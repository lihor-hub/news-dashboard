import { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
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

interface Props {
  open: boolean;
  onClose: () => void;
}

type Step = 'interests' | 'recommendations' | 'saving';

export function OnboardingWizard({ open, onClose }: Props) {
  const qc = useQueryClient();
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

  const saveMutation = useMutation({
    mutationFn: saveOnboardingInterests,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['sources'] });
      onClose();
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
    saveMutation.mutate({
      interest_ids: [...selectedInterests],
      enabled_slugs: [...selectedSlugs],
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

  const isLoading = step === 'interests' ? loadingInterests : loadingRecs;

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
            {step === 'interests' ? 'What are you interested in?' : 'Recommended sources'}
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
        ) : (
          <RecommendationsStep
            recommendations={recommendations}
            selected={selectedSlugs}
            onToggle={toggleSlug}
            loading={loadingRecs}
          />
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
          ) : (
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
