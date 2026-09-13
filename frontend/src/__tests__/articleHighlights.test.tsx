// @vitest-environment happy-dom
import { expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ArticleHighlights } from '@/components/article/ArticleHighlights';

it('keeps highlight text, notes, and the correct delete action available in RTL', async () => {
  const onDelete = vi.fn();
  render(
    <div dir="rtl">
      <ArticleHighlights
        highlights={[
          {
            id: 1,
            user_id: 1,
            article_id: 42,
            highlighted_text: 'First highlight',
            offset_chars: 0,
            note: null,
            created_at: '2026-07-02T12:00:00Z',
          },
          {
            id: 2,
            user_id: 1,
            article_id: 42,
            highlighted_text: 'Second highlight',
            offset_chars: 20,
            note: 'Remember this',
            created_at: '2026-07-02T12:00:00Z',
          },
        ]}
        onDelete={onDelete}
      />
    </div>
  );
  const highlights = screen.getAllByRole('listitem');
  expect(within(highlights[0]).getByText('First highlight')).toBeVisible();
  expect(within(highlights[1]).getByText('Remember this')).toBeVisible();
  await userEvent.click(within(highlights[1]).getByRole('button', { name: 'Delete highlight' }));
  expect(onDelete).toHaveBeenCalledExactlyOnceWith(2);
});
