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
