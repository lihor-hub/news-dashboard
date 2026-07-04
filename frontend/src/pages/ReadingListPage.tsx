import { useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  BookmarkPlus,
  Check,
  ExternalLink,
  GripVertical,
  Loader2,
  MonitorPlay,
  Newspaper,
  RotateCcw,
  Sparkles,
  Trash2,
  TriangleAlert,
  Upload,
  Users,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  addReadingListItem,
  deleteReadingListItem,
  fetchReadingList,
  importReadingList,
  reorderReadingList,
  updateReadingListItem,
  type ReadingListImportResult,
  type ReadingListImportSource,
  type ReadingListItem,
  type ReadingListKind,
  type ReadingListStatus,
} from '@/api/readingListApi';
import { EmptyState } from '@/components/EmptyState';

const IMPORT_SOURCES: { value: ReadingListImportSource; label: string }[] = [
  { value: 'pocket', label: 'Pocket (CSV)' },
  { value: 'instapaper', label: 'Instapaper (CSV)' },
  { value: 'omnivore', label: 'Omnivore (JSON)' },
];

const KIND_META: Record<ReadingListKind, { label: string; Icon: typeof Newspaper }> = {
  article: { label: 'Article', Icon: Newspaper },
  video: { label: 'Video', Icon: MonitorPlay },
  channel: { label: 'Channel', Icon: Users },
  link: { label: 'Link', Icon: ExternalLink },
};

function ItemCard({
  item,
  isFirst,
  isLast,
  onMove,
  onToggleDone,
  onDelete,
}: {
  item: ReadingListItem;
  isFirst: boolean;
  isLast: boolean;
  onMove: (id: number, direction: -1 | 1) => void;
  onToggleDone: (item: ReadingListItem) => void;
  onDelete: (id: number) => void;
}) {
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const pending = item.fetch_status === 'pending';
  const { label: kindLabel, Icon: KindIcon } = KIND_META[item.kind];
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-start gap-3 px-4 md:px-5 py-3 hover:bg-surface"
    >
      <button
        type="button"
        aria-label="Drag to reorder"
        className="mt-4 shrink-0 cursor-grab touch-none rounded-sm p-1 text-muted-foreground hover:text-foreground active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" strokeWidth={1.75} />
      </button>
      {item.image_url ? (
        <img
          src={item.image_url}
          alt=""
          className="h-16 w-24 shrink-0 rounded-md object-cover border border-border"
          loading="lazy"
        />
      ) : (
        <div className="flex h-16 w-24 shrink-0 items-center justify-center rounded-md border border-border bg-surface">
          <KindIcon className="size-5 text-muted-foreground" strokeWidth={1.5} />
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1 rounded-sm border border-border px-1.5 py-0.5">
            <KindIcon className="size-3" strokeWidth={1.75} />
            {kindLabel}
          </span>
          {item.site_name ? <span className="truncate">{item.site_name}</span> : null}
          {pending ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="size-3 animate-spin" />
              Fetching preview…
            </span>
          ) : null}
          {item.fetch_status === 'error' ? (
            <span
              className="inline-flex items-center gap-1 text-muted-foreground"
              title={item.fetch_error ?? undefined}
            >
              <TriangleAlert className="size-3" />
              Preview unavailable
            </span>
          ) : null}
        </div>
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className={`mt-0.5 block truncate text-sm font-medium hover:underline ${
            item.status === 'done' ? 'text-muted-foreground line-through' : ''
          }`}
        >
          {item.title ?? item.url}
        </a>
        {item.description ? (
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{item.description}</p>
        ) : null}
        {item.summary ? (
          <div className="mt-1">
            <button
              type="button"
              onClick={() => setSummaryExpanded((expanded) => !expanded)}
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <Sparkles className="size-3" strokeWidth={1.75} />
              {summaryExpanded ? 'Hide AI summary' : 'AI summary'}
            </button>
            {summaryExpanded ? (
              <p className="mt-0.5 text-xs text-muted-foreground">{item.summary}</p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-1 text-muted-foreground">
        <button
          type="button"
          aria-label="Move up"
          disabled={isFirst}
          onClick={() => onMove(item.id, -1)}
          className="rounded-sm p-1 hover:text-foreground disabled:opacity-30"
        >
          <ArrowUp className="size-4" strokeWidth={1.75} />
        </button>
        <button
          type="button"
          aria-label="Move down"
          disabled={isLast}
          onClick={() => onMove(item.id, 1)}
          className="rounded-sm p-1 hover:text-foreground disabled:opacity-30"
        >
          <ArrowDown className="size-4" strokeWidth={1.75} />
        </button>
        <button
          type="button"
          aria-label={item.status === 'done' ? 'Mark as unread' : 'Mark as done'}
          onClick={() => onToggleDone(item)}
          className="rounded-sm p-1 hover:text-foreground"
        >
          {item.status === 'done' ? (
            <RotateCcw className="size-4" strokeWidth={1.75} />
          ) : (
            <Check className="size-4" strokeWidth={1.75} />
          )}
        </button>
        <button
          type="button"
          aria-label="Delete"
          onClick={() => onDelete(item.id)}
          className="rounded-sm p-1 hover:text-destructive"
        >
          <Trash2 className="size-4" strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}

export function ReadingListPage() {
  const queryClient = useQueryClient();
  const [newUrl, setNewUrl] = useState('');
  const [filter, setFilter] = useState<ReadingListStatus>('unread');
  const [importSource, setImportSource] = useState<ReadingListImportSource>('pocket');
  const [importResult, setImportResult] = useState<ReadingListImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['reading-list', filter],
    queryFn: () => fetchReadingList(filter),
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.fetch_status === 'pending') ? 2000 : false,
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['reading-list'] });

  const addMutation = useMutation({
    mutationFn: (url: string) => addReadingListItem(url),
    onSuccess: () => {
      invalidate();
      setNewUrl('');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ReadingListStatus }) =>
      updateReadingListItem(id, { status }),
    onSuccess: invalidate,
  });

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: number[]) => reorderReadingList(orderedIds),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteReadingListItem(id),
    onSuccess: invalidate,
  });

  const importMutation = useMutation({
    mutationFn: ({ file, source }: { file: File; source: ReadingListImportSource }) =>
      importReadingList(file, source),
    onSuccess: (result) => {
      setImportResult(result);
      setImportError(null);
      invalidate();
    },
    onError: (err) => {
      setImportResult(null);
      setImportError(err instanceof Error ? err.message : 'Import failed');
    },
  });

  function handleAdd() {
    const url = newUrl.trim();
    if (!url) return;
    addMutation.mutate(url);
  }

  function handleMove(id: number, direction: -1 | 1) {
    const ids = items.map((item) => item.id);
    const index = ids.indexOf(id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorderMutation.mutate(ids);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = items.map((item) => item.id);
    const oldIndex = ids.indexOf(Number(active.id));
    const newIndex = ids.indexOf(Number(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    reorderMutation.mutate(arrayMove(ids, oldIndex, newIndex));
  }

  function handleToggleDone(item: ReadingListItem) {
    updateMutation.mutate({
      id: item.id,
      status: item.status === 'done' ? 'unread' : 'done',
    });
  }

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Reading List</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Save links from anywhere — videos, posts, channels — and work through them later.
        </p>
      </div>

      <div className="px-4 md:px-5 pb-3 flex items-center gap-2">
        <input
          value={newUrl}
          onChange={(e) => setNewUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleAdd();
          }}
          placeholder="Paste a link to read later…"
          className="h-9 flex-1 max-w-xl rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-border-strong"
        />
        <button
          type="button"
          onClick={handleAdd}
          disabled={!newUrl.trim() || addMutation.isPending}
          className="h-9 px-3 rounded-md bg-foreground text-background text-sm font-medium disabled:opacity-50"
        >
          Add
        </button>
      </div>
      {addMutation.isError ? (
        <p className="px-4 md:px-5 pb-2 text-xs text-destructive">
          Could not save that link — check that it is a valid http(s) URL.
        </p>
      ) : null}

      <div className="px-4 md:px-5 pb-3 flex items-center gap-2">
        <select
          value={importSource}
          onChange={(e) => setImportSource(e.target.value as ReadingListImportSource)}
          className="h-9 rounded-md border border-border bg-surface px-2 text-sm outline-none focus:border-border-strong"
        >
          {IMPORT_SOURCES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => document.getElementById('reading-list-import-input')?.click()}
          disabled={importMutation.isPending}
          className="h-9 px-3 rounded-md border border-border text-sm font-medium hover:bg-surface disabled:opacity-50 inline-flex items-center gap-1.5"
        >
          <Upload className="size-4" />
          {importMutation.isPending ? 'Importing…' : 'Import export file'}
        </button>
        <input
          id="reading-list-import-input"
          aria-label="Import reading list export"
          type="file"
          accept=".csv,.json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            const input = e.target;
            importMutation.mutate(
              { file, source: importSource },
              { onSettled: () => (input.value = '') }
            );
          }}
        />
      </div>
      {(importResult ?? importError) && (
        <div className="px-4 md:px-5 pb-3 text-xs">
          {importError ? (
            <p className="text-destructive">Import failed: {importError}</p>
          ) : (
            importResult && (
              <p className="text-muted-foreground">
                <span className="text-foreground font-medium">{importResult.added} added</span>
                {' · '}
                {importResult.skipped} skipped · {importResult.failed} failed
              </p>
            )
          )}
        </div>
      )}

      <div className="px-4 md:px-5 pb-3 flex items-center gap-1">
        {(['unread', 'done'] as const).map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => setFilter(status)}
            className={`h-8 rounded-md px-3 text-sm capitalize ${
              filter === status
                ? 'bg-foreground text-background font-medium'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {status}
          </button>
        ))}
      </div>

      {isLoading ? null : items.length === 0 ? (
        <EmptyState
          icon={BookmarkPlus}
          title={filter === 'done' ? 'Nothing finished yet' : 'Your reading list is empty'}
          subtitle={
            filter === 'done'
              ? 'Items you mark as done will show up here.'
              : 'Paste a link above to save it for later.'
          }
        />
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext
            items={items.map((item) => item.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="divide-y divide-border border-t border-border">
              {items.map((item, index) => (
                <ItemCard
                  key={item.id}
                  item={item}
                  isFirst={index === 0}
                  isLast={index === items.length - 1}
                  onMove={handleMove}
                  onToggleDone={handleToggleDone}
                  onDelete={(id) => deleteMutation.mutate(id)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}
