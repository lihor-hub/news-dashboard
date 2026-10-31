import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import type { ReactNode } from 'react';
import { toast } from 'sonner';
import { logoutUser } from '../api';
import { useLogout } from '../hooks/useLogout';

const resetAuth = vi.hoisted(() => vi.fn());
vi.mock('../contexts/auth', () => ({ useAuth: () => ({ resetAuth }) }));
vi.mock('../api', () => ({ logoutUser: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={['/today']}>{children}</MemoryRouter>;
}

beforeEach(() => vi.clearAllMocks());

describe('useLogout', () => {
  it.each([false, true])(
    'revokes memory before server logout and navigates even on failure=%s',
    async (fail) => {
      let finish!: () => void;
      vi.mocked(logoutUser).mockImplementation(() => {
        expect(resetAuth).toHaveBeenCalledWith('sign-out');
        return new Promise<void>((resolve, reject) => {
          finish = () => (fail ? reject(new Error('offline')) : resolve());
        });
      });
      const { result } = renderHook(() => ({ logout: useLogout(), location: useLocation() }), {
        wrapper,
      });
      let pending!: Promise<void>;
      act(() => {
        pending = result.current.logout();
      });
      expect(result.current.location.pathname).toBe('/today');
      await act(async () => {
        finish();
        await pending;
      });
      expect(result.current.location.pathname).toBe('/login');
      if (fail)
        expect(toast.error).toHaveBeenCalledWith(
          'Signed out locally. Server sign-out could not be confirmed.'
        );
      else expect(toast.error).not.toHaveBeenCalled();
    }
  );
});
