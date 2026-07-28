import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import { Rss } from 'lucide-react';
import { createSource, previewSubstackSource } from '@/api';
import type { SubstackPreviewResult } from '@/api';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { sourceActionErrorMessage } from '@/lib/errorPresentation';

interface SubstackSourceWizardProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export function SubstackSourceWizard({ open, onClose, onCreated }: SubstackSourceWizardProps) {
  const { t } = useTranslation();
  const [submittedUrl, setSubmittedUrl] = useState('');
  const [name, setName] = useState('');
  const [preview, setPreview] = useState<SubstackPreviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: () => previewSubstackSource(submittedUrl),
    onSuccess: (result) => {
      setPreview(result);
      setName(result.suggested_name);
      setError(null);
    },
    onError: (err: Error) => {
      setPreview(null);
      setError(sourceActionErrorMessage(err, 'add'));
    },
  });
  const createMutation = useMutation({
    mutationFn: () =>
      createSource({
        name,
        url: preview?.feed_url ?? '',
        category: 'newsletter',
        kind: 'rss_feed',
        high_priority: true,
        provider: 'substack',
      }),
    onSuccess: () => {
      onCreated();
      handleClose();
    },
    onError: (err: Error) => setError(sourceActionErrorMessage(err, 'add')),
  });

  function handleClose() {
    setSubmittedUrl('');
    setName('');
    setPreview(null);
    setError(null);
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && handleClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('substackWizard.title')}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4 pt-1">
          <p className="text-sm text-muted-foreground">{t('substackWizard.description')}</p>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="substack-url" className="text-xs font-medium text-muted-foreground">
              {t('substackWizard.linkLabel')}
            </label>
            <Input
              id="substack-url"
              placeholder={t('substackWizard.linkPlaceholder')}
              value={submittedUrl}
              onChange={(event) => {
                setSubmittedUrl(event.target.value);
                setPreview(null);
                setError(null);
              }}
            />
          </div>
          {!preview && (
            <Button
              onClick={() => previewMutation.mutate()}
              disabled={!submittedUrl.trim() || previewMutation.isPending}
            >
              <Rss className="size-4" />
              {previewMutation.isPending ? t('substackWizard.finding') : t('substackWizard.find')}
            </Button>
          )}
          {preview && (
            <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/25 p-4">
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="substack-name"
                  className="text-xs font-medium text-muted-foreground"
                >
                  {t('substackWizard.nameLabel')}
                </label>
                <Input
                  id="substack-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
                <span className="break-all text-xs text-muted-foreground">{preview.feed_url}</span>
              </div>
              <div>
                <p className="mb-1 text-xs font-medium">
                  {t('substackWizard.latestPosts', { count: preview.entry_count })}
                </p>
                <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
                  {preview.items.map((item) => (
                    <li key={item.url}>{item.title}</li>
                  ))}
                </ul>
              </div>
              <Button
                onClick={() => createMutation.mutate()}
                disabled={!name.trim() || createMutation.isPending}
              >
                {createMutation.isPending
                  ? t('substackWizard.following')
                  : t('substackWizard.follow', { name })}
              </Button>
            </div>
          )}
          {error && <p className="text-sm text-[color:var(--err)]">{error}</p>}
          <Button variant="ghost" onClick={handleClose}>
            {t('substackWizard.cancel')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
