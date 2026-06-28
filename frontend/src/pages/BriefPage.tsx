import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Newspaper, RefreshCw, AlertCircle, Inbox, History, Wand2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchLatestBriefing, createBriefing } from '@/api';
import { BriefingView, BriefSkeleton } from '@/components/BriefingView';
import { BriefingChat } from '@/components/BriefingChat';
import { trackFeature } from '@/lib/analytics';

// ── Main page ─────────────────────────────────────────────────────────────────

interface GenerateError {
  kind: 'no_ai' | 'failed';
  message: string;
}
interface NoCandidates {
  shown: boolean;
}

export function BriefPage() {
  const navigate = useNavigate();
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<GenerateError | null>(null);
  const [noCandidates, setNoCandidates] = useState<NoCandidates>({ shown: false });
  const [focusInput, setFocusInput] = useState('');

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['briefings', 'latest'],
    queryFn: fetchLatestBriefing,
  });

  function generate(focusPrompt?: string) {
    void handleGenerate(focusPrompt);
  }

  function generateDefault() {
    void handleGenerate();
  }

  async function handleGenerate(focusPrompt?: string) {
    trackFeature('generate_briefing');
    setIsGenerating(true);
    setGenerateError(null);
    setNoCandidates({ shown: false });
    try {
      const result = await createBriefing(focusPrompt);
      if ('status' in result && result.status === 'no_candidates') {
        setNoCandidates({ shown: true });
      } else {
        await refetch();
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        if (err.message.startsWith('503')) {
          setGenerateError({ kind: 'no_ai', message: err.message });
        } else {
          setGenerateError({ kind: 'failed', message: err.message });
        }
      } else {
        setGenerateError({ kind: 'failed', message: 'Unexpected error' });
      }
    } finally {
      setIsGenerating(false);
    }
  }

  if (isLoading) {
    return <BriefSkeleton />;
  }

  // Error states (after attempted generation)
  if (generateError) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/30 bg-destructive/5 mb-4">
          <AlertCircle className="size-4 text-destructive mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-foreground">
              {generateError.kind === 'no_ai' ? 'AI not configured' : 'Generation failed'}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {generateError.kind === 'no_ai'
                ? 'FREE_LLM_API_KEY (or OPENAI_API_KEY) is not set. Configure it in the app environment to enable briefings.'
                : 'The AI returned an unexpected response. Try again or review the raw feed.'}
            </div>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {generateError.kind === 'failed' && (
            <Button size="sm" onClick={generateDefault} disabled={isGenerating}>
              <RefreshCw className={isGenerating ? 'animate-spin' : ''} />
              {isGenerating ? 'Retrying…' : 'Retry'}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => navigate('/today')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  // No candidates after generation attempt
  if (noCandidates.shown) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex flex-col items-center justify-center text-center py-16 text-muted-foreground">
          <Newspaper className="size-10 text-subtle mb-3" strokeWidth={1.25} />
          <div className="text-sm font-medium text-foreground">No articles to brief</div>
          <div className="text-xs mt-1 max-w-xs">
            No articles were discovered in the current-day window. Check back after your next
            ingest.
          </div>
        </div>
        <div className="flex justify-center">
          <Button size="sm" variant="outline" onClick={() => navigate('/today')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  // Empty state — no briefings yet
  if (!data || ('status' in data && data.status === 'empty')) {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex flex-col items-center justify-center text-center py-16 text-muted-foreground">
          <Newspaper className="size-10 text-subtle mb-3" strokeWidth={1.25} />
          <div className="text-sm font-medium text-foreground">No briefing yet</div>
          <div className="text-xs mt-1 max-w-xs">
            Generate your first briefing to see a summary of today's news.
          </div>
        </div>
        <div className="flex gap-2 justify-center flex-wrap">
          <Button size="sm" onClick={generateDefault} disabled={isGenerating}>
            <RefreshCw className={isGenerating ? 'animate-spin' : ''} />
            {isGenerating ? 'Generating…' : 'Generate briefing'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate('/today')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  // Failed briefing state (last briefing itself failed)
  if (data.status === 'failed') {
    return (
      <div className="px-4 md:px-5 pt-4 pb-6">
        <div className="flex items-start gap-3 p-4 rounded-lg border border-destructive/30 bg-destructive/5 mb-4">
          <AlertCircle className="size-4 text-destructive mt-0.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-foreground">Last briefing failed</div>
            {data.error && (
              <div className="text-xs text-muted-foreground mt-1 font-mono">{data.error}</div>
            )}
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button size="sm" onClick={generateDefault} disabled={isGenerating}>
            <RefreshCw className={isGenerating ? 'animate-spin' : ''} />
            {isGenerating ? 'Retrying…' : 'Retry'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate('/today')}>
            <Inbox />
            Review Today feed
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-2">
        <div className="flex gap-2 items-center">
          <Input
            placeholder="Focus on… (e.g. AI safety, tech policy)"
            value={focusInput}
            onChange={(e) => setFocusInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && focusInput.trim()) generate(focusInput.trim());
            }}
            className="h-8 text-sm"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={isGenerating || !focusInput.trim()}
            onClick={() => generate(focusInput.trim())}
          >
            <Wand2 className="size-3.5 mr-1" />
            Generate
          </Button>
        </div>
      </div>
      <BriefingView
        briefing={data}
        onGenerate={generateDefault}
        isGenerating={isGenerating}
        onRefreshBriefing={() => {
          void refetch();
        }}
        afterMeta={
          <div className="flex items-center gap-2 mt-1">
            <Link
              to="/briefs"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <History className="size-3" />
              View history
            </Link>
            <BriefingChat briefingId={data.id} />
          </div>
        }
      />
    </div>
  );
}
