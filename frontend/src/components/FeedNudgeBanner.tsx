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

function NudgeCard({ nudge }: { nudge: PersonalizationNudge }) {
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
    <div className="mx-4 md:mx-5 my-2 flex items-start gap-3 rounded-lg border border-border bg-muted/50 px-4 py-3">
      <VolumeX className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-snug">{nudge.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{nudge.message}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => applyMutation.mutate()}
            disabled={isPending}
          >
            {actionLabel}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-muted-foreground"
            onClick={() => dismissMutation.mutate()}
            disabled={isPending}
          >
            Not now
          </Button>
        </div>
      </div>
      <button
        className="shrink-0 text-muted-foreground hover:text-foreground"
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
