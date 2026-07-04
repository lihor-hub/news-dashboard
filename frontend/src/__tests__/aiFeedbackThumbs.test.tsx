// @vitest-environment happy-dom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AiFeedbackThumbs } from '../components/AiFeedbackThumbs';
import * as api from '../api';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('AiFeedbackThumbs', () => {
  it('renders unselected when no prior feedback exists', async () => {
    vi.spyOn(api, 'fetchAiFeedback').mockResolvedValue({});

    render(<AiFeedbackThumbs subjectType="briefing" subjectId={7} />);

    await waitFor(() => expect(api.fetchAiFeedback).toHaveBeenCalledWith('briefing', [7]));
    expect(screen.getByLabelText('Thumbs up').getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByLabelText('Thumbs down').getAttribute('aria-pressed')).toBe('false');
  });

  it('preselects the persisted verdict on mount', async () => {
    vi.spyOn(api, 'fetchAiFeedback').mockResolvedValue({ '7:': 1 });

    render(<AiFeedbackThumbs subjectType="briefing" subjectId={7} />);

    await waitFor(() =>
      expect(screen.getByLabelText('Thumbs up').getAttribute('aria-pressed')).toBe('true')
    );
  });

  it('optimistically selects thumbs up and posts feedback', async () => {
    vi.spyOn(api, 'fetchAiFeedback').mockResolvedValue({});
    const post = vi.spyOn(api, 'postAiFeedback').mockResolvedValue({
      id: 1,
      user_id: 1,
      subject_type: 'briefing',
      subject_id: 7,
      article_id: null,
      verdict: 1,
      comment: null,
      created_at: '2026-01-01T00:00:00Z',
    });

    render(<AiFeedbackThumbs subjectType="briefing" subjectId={7} />);
    await userEvent.click(screen.getByLabelText('Thumbs up'));

    expect(screen.getByLabelText('Thumbs up').getAttribute('aria-pressed')).toBe('true');
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('briefing', 7, 1, { articleId: undefined })
    );
  });

  it('clicking the selected verdict again retracts it', async () => {
    vi.spyOn(api, 'fetchAiFeedback').mockResolvedValue({ '7:': 1 });
    const del = vi.spyOn(api, 'deleteAiFeedback').mockResolvedValue({ deleted: true });

    render(<AiFeedbackThumbs subjectType="briefing" subjectId={7} />);
    await waitFor(() =>
      expect(screen.getByLabelText('Thumbs up').getAttribute('aria-pressed')).toBe('true')
    );

    await userEvent.click(screen.getByLabelText('Thumbs up'));

    expect(screen.getByLabelText('Thumbs up').getAttribute('aria-pressed')).toBe('false');
    await waitFor(() => expect(del).toHaveBeenCalledWith('briefing', 7, { articleId: undefined }));
  });

  it('reverts the optimistic update when the request fails', async () => {
    vi.spyOn(api, 'fetchAiFeedback').mockResolvedValue({});
    vi.spyOn(api, 'postAiFeedback').mockRejectedValue(new Error('network error'));

    render(<AiFeedbackThumbs subjectType="briefing" subjectId={7} />);
    await userEvent.click(screen.getByLabelText('Thumbs up'));

    await waitFor(() =>
      expect(screen.getByLabelText('Thumbs up').getAttribute('aria-pressed')).toBe('false')
    );
  });
});
