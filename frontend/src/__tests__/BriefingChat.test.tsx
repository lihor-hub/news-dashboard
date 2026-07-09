// @vitest-environment happy-dom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { BriefingChat } from '../components/BriefingChat';
import * as api from '../api';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

function renderChat(briefingId = 42) {
  render(
    <MemoryRouter>
      <BriefingChat briefingId={briefingId} />
    </MemoryRouter>
  );
}

async function openChat() {
  await userEvent.click(screen.getByRole('button', { name: 'Ask assistant' }));
}

async function sendMessage(text: string) {
  await userEvent.type(screen.getByRole('textbox', { name: 'Chat input' }), text);
  await userEvent.click(screen.getByRole('button', { name: 'Send' }));
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('BriefingChat', () => {
  it('appends assistant reply on successful send', async () => {
    vi.spyOn(api, 'chatWithBriefing').mockResolvedValue({ reply: 'AI reply here' });

    renderChat();
    await openChat();
    await sendMessage('What is this about?');

    await waitFor(() => expect(screen.getByText('AI reply here')).toBeTruthy());
    expect(screen.getByText('What is this about?')).toBeTruthy();
  });

  it('shows recovery message and links on 404 briefing not found', async () => {
    vi.spyOn(api, 'chatWithBriefing').mockRejectedValue(new Error('briefing not found'));

    renderChat();
    await openChat();
    await sendMessage('Hello?');

    await waitFor(() => expect(screen.getByTestId('briefing-unavailable')).toBeTruthy());
    expect(screen.getByText('This briefing is no longer available.')).toBeTruthy();

    const latestBriefingLink = screen.getByRole('link', { name: 'Latest briefing' });
    expect(latestBriefingLink.getAttribute('href')).toBe('/');

    const briefingHistoryLink = screen.getByRole('link', { name: 'Briefing history' });
    expect(briefingHistoryLink.getAttribute('href')).toBe('/briefs');
  });

  it('shows generic fallback for non-404 errors', async () => {
    vi.spyOn(api, 'chatWithBriefing').mockRejectedValue(new Error('500 Internal Server Error'));

    renderChat();
    await openChat();
    await sendMessage('Hello?');

    await waitFor(() =>
      expect(screen.getByText('Sorry, something went wrong. Please try again.')).toBeTruthy()
    );
    expect(screen.queryByTestId('briefing-unavailable')).toBeNull();
  });
});
