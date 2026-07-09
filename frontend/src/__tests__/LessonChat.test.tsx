// @vitest-environment happy-dom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LessonChat } from '../components/LessonChat';
import { HttpError } from '../api';
import * as api from '../api';

const { translationSpy } = vi.hoisted(() => ({
  translationSpy: vi.fn((key: string) => {
    const translations: Record<string, string> = {
      'learn.chat.title': 'Ask a follow-up question',
      'learn.chat.description': 'Ask clarifying, critical, or applied questions.',
      'learn.chat.presets.explain_simpler': 'Explain simpler',
      'learn.chat.presets.give_example': 'Give an example',
      'learn.chat.presets.challenge_argument': 'Challenge the argument',
      'learn.chat.presets.apply_to_work': 'Apply this to my work',
      'learn.chat.placeholder': 'Ask a question...',
      'learn.chat.input_label': 'Lesson chat input',
      'learn.chat.send': 'Send',
      'learn.chat.thinking': 'Thinking...',
      'learn.chat.error': 'Failed to get an answer. Please try again.',
    };
    return translations[key] ?? key;
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: translationSpy,
    i18n: { changeLanguage: () => Promise.resolve() },
  }),
}));

vi.spyOn(console, 'error').mockImplementation(() => undefined);

function renderChat(lessonId = 7) {
  render(<LessonChat lessonId={lessonId} />);
}

async function sendMessage(text: string) {
  await userEvent.type(screen.getByRole('textbox', { name: 'Lesson chat input' }), text);
  await userEvent.click(screen.getByRole('button', { name: 'Send' }));
}

beforeEach(() => {
  vi.restoreAllMocks();
  translationSpy.mockClear();
});

describe('LessonChat', () => {
  it('appends the assistant reply on a successful send', async () => {
    vi.spyOn(api, 'askLessonQuestion').mockResolvedValue({ reply: 'Here is a simpler take.' });

    renderChat();
    await sendMessage('Explain this to me.');

    await waitFor(() => expect(screen.getByText('Here is a simpler take.')).toBeTruthy());
    expect(screen.getByText('Explain this to me.')).toBeTruthy();
    expect(api.askLessonQuestion).toHaveBeenCalledWith(7, 'Explain this to me.', []);
  });

  it('sends a preset prompt when a preset button is clicked', async () => {
    vi.spyOn(api, 'askLessonQuestion').mockResolvedValue({ reply: 'Sure, an example: ...' });

    renderChat();
    await userEvent.click(screen.getByRole('button', { name: 'Give an example' }));

    await waitFor(() => expect(screen.getByText('Sure, an example: ...')).toBeTruthy());
    expect(api.askLessonQuestion).toHaveBeenCalledWith(7, 'Give an example', []);
  });

  it('keeps the question in the input and shows an error message on failure', async () => {
    vi.spyOn(api, 'askLessonQuestion').mockRejectedValue(
      new HttpError(503, 'AI is not configured')
    );

    renderChat();
    await sendMessage('What is this about?');

    await waitFor(() => expect(screen.getByText('AI is not configured')).toBeTruthy());
    expect(screen.queryByText('What is this about?')).toBeNull();
    expect(screen.getByRole('textbox', { name: 'Lesson chat input' })).toHaveValue(
      'What is this about?'
    );
  });

  it('shows a generic fallback message for non-HttpError failures', async () => {
    vi.spyOn(api, 'askLessonQuestion').mockRejectedValue(new Error('network down'));

    renderChat();
    await sendMessage('Hello?');

    await waitFor(() => expect(screen.getByText('network down')).toBeTruthy());
  });
});
