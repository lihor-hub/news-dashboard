import { useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { askLessonQuestion, HttpError, type LessonChatMessage } from '@/api';

const PROMPT_PRESET_KEYS = [
  'explain_simpler',
  'give_example',
  'challenge_argument',
  'apply_to_work',
] as const;

function MessageBubble({ msg }: { msg: LessonChatMessage }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
        }`}
      >
        {msg.content}
      </div>
    </div>
  );
}

export function LessonChat({ lessonId }: { lessonId: number }) {
  const { t } = useTranslation();
  const [history, setHistory] = useState<LessonChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history]);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const priorHistory = history;
    const userMsg: LessonChatMessage = { role: 'user', content: trimmed };
    setHistory([...priorHistory, userMsg]);
    setInput('');
    setError(null);
    setLoading(true);

    try {
      const { reply } = await askLessonQuestion(lessonId, trimmed, priorHistory);
      setHistory([...priorHistory, userMsg, { role: 'assistant', content: reply }]);
    } catch (err) {
      // Roll back the optimistic message and restore the input so the question isn't lost.
      setHistory(priorHistory);
      setInput(trimmed);
      if (err instanceof HttpError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : t('learn.chat.error'));
      }
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void sendMessage(input);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-background p-4">
      <div>
        <h3 className="text-sm font-semibold text-foreground">{t('learn.chat.title')}</h3>
        <p className="text-xs text-muted-foreground">{t('learn.chat.description')}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {PROMPT_PRESET_KEYS.map((key) => (
          <Button
            key={key}
            type="button"
            size="sm"
            variant="outline"
            disabled={loading}
            onClick={() => void sendMessage(t(`learn.chat.presets.${key}`))}
          >
            {t(`learn.chat.presets.${key}`)}
          </Button>
        ))}
      </div>

      {history.length > 0 ? (
        <div className="max-h-80 space-y-2 overflow-y-auto rounded-md border border-border bg-muted/10 p-3">
          {history.map((msg, index) => (
            <MessageBubble key={index} msg={msg} />
          ))}
          {loading ? (
            <div className="flex justify-start">
              <div className="animate-pulse rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                {t('learn.chat.thinking')}
              </div>
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-foreground">
          {error}
        </div>
      ) : null}

      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('learn.chat.placeholder')}
          disabled={loading}
          maxLength={4000}
          aria-label={t('learn.chat.input_label')}
          className="flex-1"
        />
        <Button
          type="button"
          size="icon"
          onClick={() => void sendMessage(input)}
          disabled={loading || !input.trim()}
          aria-label={t('learn.chat.send')}
        >
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  );
}
