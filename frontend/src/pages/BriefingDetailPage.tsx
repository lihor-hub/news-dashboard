import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, AlertCircle, Newspaper } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchBriefing } from '@/api';
import { BriefingView, BriefSkeleton } from '@/components/BriefingView';
import { BriefingChat } from '@/components/BriefingChat';

function BackLink() {
  return (
    <Link
      to="/briefs"
      className="inline-flex items-center gap-1.5 px-4 md:px-5 pt-3 pb-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
    >
      <ArrowLeft className="size-3.5" />
      Briefing history
    </Link>
  );
}

export function BriefingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const briefingId = id ? parseInt(id, 10) : NaN;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['briefings', briefingId],
    queryFn: () => fetchBriefing(briefingId),
    enabled: !isNaN(briefingId),
    retry: false,
  });

  if (isNaN(briefingId)) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <BackLink />
        <div className="text-sm text-muted-foreground mt-4">Invalid briefing ID.</div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <>
        <BackLink />
        <BriefSkeleton />
      </>
    );
  }

  if (isError || !data) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <BackLink />
        <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/30 bg-destructive/5 mt-4 mb-4">
          <AlertCircle className="size-4 text-destructive mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-foreground">Briefing not found</div>
            <div className="text-xs text-muted-foreground mt-1">
              This briefing may have been deleted or the ID is invalid.
            </div>
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => void navigate('/briefs')}>
          <Newspaper />
          View all briefings
        </Button>
      </div>
    );
  }

  if (data.status === 'failed') {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <BackLink />
        <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/30 bg-destructive/5 mt-4 mb-4">
          <AlertCircle className="size-4 text-destructive mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-foreground">This briefing failed</div>
            {data.error && (
              <div className="text-xs text-muted-foreground mt-1 font-mono">{data.error}</div>
            )}
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => void navigate('/briefs')}>
          <Newspaper />
          View all briefings
        </Button>
      </div>
    );
  }

  return (
    <>
      <BackLink />
      <BriefingView
        briefing={data}
        afterMeta={<BriefingChat briefingId={data.id} />}
        onRefreshBriefing={() => {
          void refetch();
        }}
      />
    </>
  );
}
