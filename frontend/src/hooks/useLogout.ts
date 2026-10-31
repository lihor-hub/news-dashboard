import { useNavigate } from 'react-router';
import { logoutUser } from '@/api';
import { useAuth } from '@/contexts/auth';
import { toast } from 'sonner';
import { stopActivity } from '@/lib/activity';

export function useLogout() {
  const navigate = useNavigate();
  const { resetAuth } = useAuth();

  return async function handleLogout() {
    stopActivity();
    resetAuth('sign-out');
    try {
      await logoutUser();
    } catch {
      toast.error('Signed out locally. Server sign-out could not be confirmed.');
    } finally {
      void navigate('/login', { replace: true });
    }
  };
}
