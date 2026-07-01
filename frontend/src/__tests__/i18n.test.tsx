// @vitest-environment happy-dom
/**
 * Tests for i18n functionality.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import { AuthProvider } from '@/contexts/auth';
import userEvent from '@testing-library/user-event';
import i18n from '@/lib/i18n';
import { LoginPage } from '@/pages/LoginPage';
import * as api from '@/api';

function renderWithI18n(ui: React.ReactNode) {
  return render(
    <I18nextProvider i18n={i18n}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/login']}>{ui}</MemoryRouter>
      </AuthProvider>
    </I18nextProvider>
  );
}

describe('i18n integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders LoginPage with translated English strings', async () => {
    renderWithI18n(<LoginPage />);

    // Check that the app name and tagline are rendered
    expect(await screen.findByText('News Dashboard')).toBeInTheDocument();
    expect(await screen.findByText('Your private news platform')).toBeInTheDocument();

    // Check form labels
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(await screen.findByLabelText('Password')).toBeInTheDocument();

    // Check buttons
    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument();

    // Check alternative login option
    expect(
      await screen.findByRole('button', { name: /use email code instead/i })
    ).toBeInTheDocument();
  });

  it('displays translated error messages', async () => {
    // Mock the loginUser function to return an error
    vi.spyOn(api, 'loginUser').mockRejectedValue(new Error('401 Unauthorized'));

    renderWithI18n(<LoginPage />);

    // Fill in the form and submit
    await userEvent.type(screen.getByLabelText('Username'), 'testuser');
    await userEvent.type(screen.getByLabelText('Password'), 'wrongpass');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    // Wait for and check the error message
    const alertElement = await screen.findByRole('alert');
    expect(alertElement).toHaveTextContent('Invalid username or password.');
  });
});
