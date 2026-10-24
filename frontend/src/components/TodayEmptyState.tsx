import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { CalendarDays, CheckCircle2, Clock, GraduationCap, Plus, Rss, Tags } from 'lucide-react';
import { fetchSources } from '@/api';
import { EmptyState } from '@/components/EmptyState';
import type { Source } from '@/types';

function isFollowed(source: Source): boolean {
  return source.owner_user_id == null ? (source.subscribed ?? !!source.enabled) : !!source.enabled;
}

/** Today's empty view: onboarding nudge with no feeds, otherwise a "caught up" moment. */
export function TodayEmptyState({ category }: { category?: string }) {
  const { t } = useTranslation();
  const { data: sources } = useQuery({ queryKey: ['sources'], queryFn: fetchSources });

  if (sources && !sources.some(isFollowed)) {
    return (
      <EmptyState
        icon={Rss}
        title={t('states.noFeeds.title')}
        subtitle={t('states.noFeeds.body')}
        actions={[{ label: t('states.noFeeds.action'), to: '/feeds', icon: Plus }]}
      />
    );
  }

  if (category) {
    return (
      <EmptyState
        icon={Tags}
        title={t('states.categoryClear.title')}
        subtitle={t('states.categoryClear.body')}
        actions={[{ label: t('states.categoryClear.action'), to: '/today' }]}
      />
    );
  }

  return (
    <EmptyState
      icon={CheckCircle2}
      title={t('states.caughtUp.title')}
      subtitle={t('states.caughtUp.body')}
      actions={[
        { label: t('states.caughtUp.learn'), to: '/learn', icon: GraduationCap },
        { label: t('states.caughtUp.recap'), to: '/recap', icon: CalendarDays },
        { label: t('states.caughtUp.later'), to: '/later', icon: Clock },
      ]}
    />
  );
}
