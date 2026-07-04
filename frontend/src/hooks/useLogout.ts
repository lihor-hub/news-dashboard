import { useNavigate } from 'react-router-dom';
import { logoutUser } from '@/api';
import { useAuth } from '@/contexts/auth';

export function useLogout() {
  const navigate = useNavigate();
  const { setUser } = useAuth();

  return async function handleLogout() {
    await logoutUser();
    setUser(null);
    void navigate('/login', { replace: true });
  };
}
