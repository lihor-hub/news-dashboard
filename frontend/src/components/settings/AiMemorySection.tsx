import { useEffect, useState } from 'react';
import { RefreshCw, Sparkles, Brain, Pencil, Trash2 } from 'lucide-react';
import {
  createAiMemory,
  deactivateAiMemory,
  fetchAiMemories,
  learnAiMemoriesFromReading,
  updateAiMemory,
} from '@/api';
import type { AiMemory } from '@/types';

type MemoryState = 'idle' | 'loading' | 'saving' | 'learning' | 'error';

export function AiMemorySection() {
  const [memories, setMemories] = useState<AiMemory[]>([]);
  const [newContent, setNewContent] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [state, setState] = useState<MemoryState>('loading');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setState('loading');
      try {
        const loaded = await fetchAiMemories();
        if (!cancelled) {
          setMemories(loaded);
          setState('idle');
        }
      } catch {
        if (!cancelled) setState('error');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const activeMemories = memories.filter((memory) => memory.active);

  const create = async () => {
    const content = newContent.trim();
    if (!content) return;
    setState('saving');
    try {
      const memory = await createAiMemory(content);
      setMemories((current) => [memory, ...current]);
      setNewContent('');
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const learn = async () => {
    setState('learning');
    try {
      const learned = await learnAiMemoriesFromReading();
      setMemories((current) => [...learned, ...current]);
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const saveEdit = async (memoryId: number) => {
    const content = editingContent.trim();
    if (!content) return;
    setState('saving');
    try {
      const updated = await updateAiMemory(memoryId, { content });
      setMemories((current) =>
        current.map((memory) => (memory.id === memoryId ? updated : memory))
      );
      setEditingId(null);
      setEditingContent('');
      setState('idle');
    } catch {
      setState('error');
    }
  };

  const deactivate = async (memoryId: number) => {
    setState('saving');
    try {
      const updated = await deactivateAiMemory(memoryId);
      setMemories((current) =>
        current.map((memory) => (memory.id === memoryId ? updated : memory))
      );
      setState('idle');
    } catch {
      setState('error');
    }
  };

  return (
    <section>
      <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">
        AI Memory
      </div>
      <div className="rounded-lg border border-border bg-card p-4 space-y-4">
        <div className="flex gap-2">
          <input
            value={newContent}
            onChange={(event) => setNewContent(event.target.value)}
            placeholder="Remember a preference or goal"
            aria-label="New AI memory"
            className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            onClick={() => void create()}
            disabled={state === 'saving' || !newContent.trim()}
            className="flex shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
          >
            {state === 'saving' ? (
              <RefreshCw className="size-3 animate-spin" />
            ) : (
              <Brain className="size-3" />
            )}
            Add
          </button>
        </div>

        <button
          onClick={() => void learn()}
          disabled={state === 'learning'}
          className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-surface transition-colors disabled:opacity-60"
        >
          {state === 'learning' ? (
            <RefreshCw className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3" />
          )}
          Learn from recent reading
        </button>

        {state === 'loading' && (
          <p className="text-xs text-muted-foreground">Loading memories...</p>
        )}
        {state === 'error' && (
          <p className="text-xs text-destructive" role="alert">
            Could not update AI memory.
          </p>
        )}

        <div className="space-y-2">
          {activeMemories.map((memory) => (
            <div key={memory.id} className="rounded-md border border-border bg-surface p-3">
              {editingId === memory.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editingContent}
                    onChange={(event) => setEditingContent(event.target.value)}
                    aria-label="AI memory content"
                    className="min-h-20 w-full rounded-md border border-border bg-card px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => void saveEdit(memory.id)}
                      className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <p className="break-words text-sm text-foreground">{memory.content}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {memory.memory_type} / {memory.source} / {Math.round(memory.confidence * 100)}
                      %
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      onClick={() => {
                        setEditingId(memory.id);
                        setEditingContent(memory.content);
                      }}
                      aria-label="Edit AI memory"
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-card hover:text-foreground"
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <button
                      onClick={() => void deactivate(memory.id)}
                      aria-label="Deactivate AI memory"
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-card hover:text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
          {state !== 'loading' && activeMemories.length === 0 && (
            <p className="text-xs text-muted-foreground">No active memories yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}
