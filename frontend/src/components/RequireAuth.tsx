import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { fetchAuthConfig, fetchMe } from '@/api';
import { useAuth } from '@/contexts/auth';

interface Props {
  children: ReactNode;
}

export function RequireAuth({ children }: Props) {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    fetchMe()
      .then((user) => {
        setUser(user);
        setChecked(true);
      })
      .catch(async () => {
        const config = await fetchAuthConfig().catch(() => null);
        if (config?.provider === 'keycloak') {
          window.location.assign(config.login_url ?? '/auth/login');
          return;
        }
        navigate('/login', { state: { from: location.pathname }, replace: true });
      });
    // Run once on mount only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!checked) return null;
  return <>{children}</>;
}
