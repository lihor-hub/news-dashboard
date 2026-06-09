import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

const SIDEBAR_KEY = 'sidebar-collapsed';

function getInitialCollapsed(): boolean {
  const stored = localStorage.getItem(SIDEBAR_KEY);
  if (stored !== null) return stored === 'true';
  // Auto-collapse on narrow screens
  return window.innerWidth < 768;
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(getInitialCollapsed);

  function toggle() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_KEY, String(next));
      return next;
    });
  }

  // Collapse sidebar below md breakpoint
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const handler = (e: MediaQueryListEvent) => {
      if (e.matches) setCollapsed(true);
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)]">
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
