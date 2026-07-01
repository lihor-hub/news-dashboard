import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { MessageCircle, Send, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { chatWithBriefing, type ChatMessage } from '@/api';

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
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

export function BriefingChat({ briefingId }: { briefingId: number }) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [briefingUnavailable, setBriefingUnavailable] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [history, open]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = { role: 'user', content: text };
    const nextHistory = [...history, userMsg];
    setHistory(nextHistory);
    setInput('');
    setLoading(true);

    try {
      const { reply } = await chatWithBriefing(briefingId, text, history);
      setHistory([...nextHistory, { role: 'assistant', content: reply }]);
    } catch (err) {
      if (err instanceof Error && err.message === 'briefing not found') {
        setBriefingUnavailable(true);
      } else {
        setHistory([
          ...nextHistory,
          { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' },
        ]);
      }
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="sm" variant="outline" className="shrink-0 mt-1" aria-label="Ask assistant">
          <MessageCircle className="size-4" />
          Ask Assistant
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="flex flex-col p-0 w-full sm:max-w-md">
        <SheetHeader className="px-4 py-3 border-b shrink-0">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-sm font-semibold">Briefing Q&A Assistant</SheetTitle>
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              onClick={() => setOpen(false)}
              aria-label="Close"
            >
              <X className="size-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Ask follow-up questions about this briefing.
          </p>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-4 py-3 min-h-0">
          {history.length === 0 && !briefingUnavailable && (
            <p className="text-xs text-muted-foreground text-center mt-8">
              Ask anything about today&apos;s briefing or the articles it covers.
            </p>
          )}
          {history.map((msg, i) => (
            <MessageBubble key={i} msg={msg} />
          ))}
          {loading && (
            <div className="flex justify-start mb-3">
              <div className="bg-muted rounded-lg px-3 py-2 text-sm text-muted-foreground animate-pulse">
                Thinking…
              </div>
            </div>
          )}
          {briefingUnavailable && (
            <div
              className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
              data-testid="briefing-unavailable"
            >
              <p className="font-medium text-foreground">This briefing is no longer available.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Refresh the briefing or open it from history.
              </p>
              <div className="flex gap-2 mt-3 flex-wrap">
                <Link to="/brief">
                  <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
                    Latest briefing
                  </Button>
                </Link>
                <Link to="/briefs">
                  <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
                    Briefing history
                  </Button>
                </Link>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="px-4 py-3 border-t shrink-0 flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question…"
            disabled={loading || briefingUnavailable}
            maxLength={4000}
            className="flex-1"
            aria-label="Chat input"
          />
          <Button
            size="icon"
            onClick={() => void sendMessage()}
            disabled={loading || !input.trim() || briefingUnavailable}
            aria-label="Send"
          >
            <Send className="size-4" />
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
