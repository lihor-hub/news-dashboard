// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const apiMock = vi.hoisted(() => ({
  fetchAdminUsers: vi.fn(),
  generateAdminUser: vi.fn(),
  deleteAdminUser: vi.fn(),
  fetchAuthConfig: vi.fn(),
}));
vi.mock('@/api', () => apiMock);

import { AdminPage } from '../pages/AdminPage';
import { AuthProvider, useAuth } from '../contexts/auth';
import type { User } from '../types';

function SetUser({ user, children }: { user: User | null; children: ReactNode }) {
  const { setUser } = useAuth();
  useEffect(() => {
    void setUser(user);
  }, [user, setUser]);
  return <>{children}</>;
}

function renderWithUser(user: User | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <SetUser user={user}>
          <AdminPage />
        </SetUser>
      </AuthProvider>
    </QueryClientProvider>
  );
}

const admin: User = { id: 1, username: 'joaquim', is_admin: true };

beforeEach(() => {
  apiMock.fetchAdminUsers.mockResolvedValue([admin]);
  apiMock.fetchAuthConfig.mockResolvedValue({ provider: 'password' });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('AdminPage', () => {
  it('blocks non-admin users', () => {
    renderWithUser({ id: 2, username: 'bob', is_admin: false });
    expect(screen.getByText('Admins only')).toBeTruthy();
    expect(apiMock.fetchAdminUsers).not.toHaveBeenCalled();
  });

  it('creates a user and shows the generated credentials', async () => {
    apiMock.generateAdminUser.mockResolvedValue({
      id: 3,
      username: 'maria',
      is_admin: false,
      password: 'sup3r-secret-pw',
      provider: 'password',
    });
    renderWithUser(admin);

    await userEvent.type(screen.getByLabelText('Username'), 'maria');
    await userEvent.click(screen.getByRole('button', { name: /create user/i }));

    await waitFor(() =>
      expect(apiMock.generateAdminUser).toHaveBeenCalledWith('maria', { is_admin: false })
    );
    expect(await screen.findByText('sup3r-secret-pw')).toBeTruthy();
  });

  it('hides the admin checkbox under Keycloak and notes the temporary password', async () => {
    apiMock.fetchAuthConfig.mockResolvedValue({ provider: 'keycloak' });
    apiMock.generateAdminUser.mockResolvedValue({
      id: 'kc-1',
      username: 'maria',
      password: 'temp-pw-123456',
      provider: 'keycloak',
      temporary: true,
    });
    renderWithUser(admin);

    await waitFor(() => expect(screen.queryByText('Grant administrator access')).toBeNull());

    await userEvent.type(screen.getByLabelText('Username'), 'maria');
    await userEvent.click(screen.getByRole('button', { name: /create user/i }));

    expect(await screen.findByText('temp-pw-123456')).toBeTruthy();
    expect(screen.getByText(/set a new password the first time/i)).toBeTruthy();
  });
});
