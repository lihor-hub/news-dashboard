import { X, VolumeX } from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  applyPersonalizationNudge,
  dismissPersonalizationNudge,
  fetchPersonalizationNudges,
} from '@/api';
import type { PersonalizationNudge } from '@/types';

const NUDGES_KEY = 'personalization-nudges';

export function NudgeCard({ nudge }: { nudge: PersonalizationNudge }) {
  const qc = useQueryClient();

  const applyMutation = useMutation({
    mutationFn: () => applyPersonalizationNudge(nudge.id),
    onSuccess: () => {
      qc.setQueryData<PersonalizationNudge[]>([NUDGES_KEY], []);
    },
  });

  const dismissMutation = useMutation({
    mutationFn: () => dismissPersonalizationNudge(nudge.id, 7),
    onSuccess: () => {
      qc.setQueryData<PersonalizationNudge[]>([NUDGES_KEY], []);
    },
  });

  const actionLabel = nudge.action === 'disable_source' ? 'Unsubscribe' : 'Reduce weight';
  const isPending = applyMutation.isPending || dismissMutation.isPending;

  return (
    <div className="mx-4 my-3 flex items-start gap-3 rounded-xl border border-border bg-muted/50 py-3 ps-4 pe-2 md:mx-5">
      <VolumeX className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="pt-0.5 text-sm font-medium leading-snug">{nudge.title}</p>
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground md:text-xs">
          {nudge.message}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-11 px-4 text-sm md:h-8 md:text-xs"
            onClick={() => applyMutation.mutate()}
            disabled={isPending}
          >
            {actionLabel}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-11 px-4 text-sm text-muted-foreground md:h-8 md:text-xs"
            onClick={() => dismissMutation.mutate()}
            disabled={isPending}
          >
            Not now
          </Button>
        </div>
      </div>
      <button
        className="flex size-11 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground md:size-8"
        onClick={() => dismissMutation.mutate()}
        disabled={isPending}
        aria-label="Dismiss"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}

export function FeedNudgeBanner() {
  const { data: nudges = [] } = useQuery({
    queryKey: [NUDGES_KEY],
    queryFn: fetchPersonalizationNudges,
    staleTime: 5 * 60 * 1000,
  });

  if (nudges.length === 0) return null;
  return <NudgeCard nudge={nudges[0]} />;
}
