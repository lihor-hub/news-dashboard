import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AutomaticAiEnrichmentSection } from '../components/settings/AutomaticAiEnrichmentSection';

const fetchSettings = vi.fn();
const updateSettings = vi.fn();

vi.mock('../api/settings', () => ({
  fetchAutomaticAiEnrichmentSettings: () => fetchSettings(),
  updateAutomaticAiEnrichmentSettings: (value: unknown) => updateSettings(value),
}));

describe('AutomaticAiEnrichmentSection', () => {
  beforeEach(() => {
    fetchSettings.mockReset().mockResolvedValue({ enabled: false, available: true, limit: 5 });
    updateSettings.mockReset().mockResolvedValue({ enabled: true, available: true, limit: 5 });
  });

  it('explains the cap and persists opt-in', async () => {
    render(<AutomaticAiEnrichmentSection />);
    const toggle = await screen.findByRole('switch', { name: 'Automatic AI article enrichment' });
    expect(toggle).not.toBeChecked();
    expect(screen.getByText(/up to 5 newly ingested articles/i)).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(updateSettings).toHaveBeenCalledWith({ enabled: true });
    await waitFor(() => expect(toggle).toBeChecked());
  });

  it('disables opt-in when credentials are unavailable', async () => {
    fetchSettings.mockResolvedValue({ enabled: false, available: false, limit: 5 });
    render(<AutomaticAiEnrichmentSection />);
    expect(await screen.findByRole('switch')).toBeDisabled();
    expect(screen.getByText(/AI credentials are not configured/i)).toBeInTheDocument();
  });

  it('allows an enabled preference to be disabled without credentials', async () => {
    fetchSettings.mockResolvedValue({ enabled: true, available: false, limit: 5 });
    updateSettings.mockResolvedValue({ enabled: false, available: false, limit: 5 });
    render(<AutomaticAiEnrichmentSection />);
    const toggle = await screen.findByRole('switch');
    expect(toggle).toBeEnabled();
    await userEvent.click(toggle);
    expect(updateSettings).toHaveBeenCalledWith({ enabled: false });
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it('allows an enabled preference to be disabled when the cap is zero', async () => {
    fetchSettings.mockResolvedValue({ enabled: true, available: true, limit: 0 });
    updateSettings.mockResolvedValue({ enabled: false, available: true, limit: 0 });
    render(<AutomaticAiEnrichmentSection />);
    const toggle = await screen.findByRole('switch');
    expect(toggle).toBeEnabled();
    await userEvent.click(toggle);
    expect(updateSettings).toHaveBeenCalledWith({ enabled: false });
  });

  it('rolls back after a save failure', async () => {
    updateSettings.mockRejectedValue(new Error('save failed'));
    render(<AutomaticAiEnrichmentSection />);
    const toggle = await screen.findByRole('switch');
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).not.toBeChecked());
    expect(screen.getByText(/could not save/i)).toBeInTheDocument();
  });
});
