// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { Home } from 'lucide-react';
import { NavLink } from '../components/NavLink';

function renderNavLink(props: Partial<React.ComponentProps<typeof NavLink>> = {}) {
  return render(
    <MemoryRouter>
      <NavLink to="/today" label="Today" icon={Home} isActive={false} variant="rail" {...props} />
    </MemoryRouter>
  );
}

describe('NavLink', () => {
  it('applies the active class when isActive is true', () => {
    renderNavLink({ isActive: true });
    const link = screen.getByText('Today').closest('a');
    expect(link?.className).toContain('bg-surface-2');
  });

  it('does not apply the active class when isActive is false', () => {
    renderNavLink({ isActive: false });
    const link = screen.getByText('Today').closest('a');
    expect(link?.className).not.toContain('bg-surface-2');
  });

  it('shows the count badge when count is positive', () => {
    renderNavLink({ count: 5 });
    expect(screen.getByText('5')).toBeTruthy();
  });

  it('does not render a count badge when count is 0', () => {
    renderNavLink({ count: 0 });
    expect(screen.queryByText('0')).toBeNull();
  });
});

describe('NavLink accessibility and sizing', () => {
  it('marks the active tab as the current page', () => {
    renderNavLink({ variant: 'tab', isActive: true });
    expect(screen.getByRole('link', { name: 'Today' }).getAttribute('aria-current')).toBe('page');
  });

  it('does not mark inactive links as current', () => {
    renderNavLink({ variant: 'sheet', isActive: false });
    expect(screen.getByRole('link', { name: 'Today' }).getAttribute('aria-current')).toBeNull();
  });

  it('keeps every variant at least 44px tall on touch screens', () => {
    for (const variant of ['rail', 'sheet', 'tab'] as const) {
      const { unmount } = renderNavLink({ variant });
      expect(screen.getByRole('link', { name: 'Today' }).className).toContain('min-h-touch');
      unmount();
    }
  });

  it('includes the count in the accessible name of the rail link', () => {
    renderNavLink({ variant: 'rail', count: 7 });
    expect(screen.getByRole('link').textContent).toContain('7');
  });
});
