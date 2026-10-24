// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import { CategoryFilter } from '../components/CategoryFilter';
import english from '../locales/en/translation.json';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === 'articleList.filterByCategory' ? english.articleList.filterByCategory : key,
  }),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderFilter(initial = '/today') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <CategoryFilter />
      <LocationProbe />
    </MemoryRouter>
  );
}

describe('CategoryFilter — pill chips', () => {
  it('renders a sticky, horizontally scrollable chip group', () => {
    renderFilter();
    const group = screen.getByRole('group', { name: 'Filter by category' });
    expect(group.className).toContain('sticky');
    expect(group.className).toContain('top-12');
    expect(group.querySelector('div')?.className).toContain('overflow-x-auto');
  });

  it('marks the active chip with aria-pressed and switches category on click', () => {
    renderFilter();
    expect(screen.getByRole('button', { name: 'All' }).getAttribute('aria-pressed')).toBe('true');
    const python = screen.getByRole('button', { name: 'Python' });
    expect(python.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(python);
    expect(screen.getByTestId('location').textContent).toBe('?category=python');
    expect(screen.getByRole('button', { name: 'Python' }).getAttribute('aria-pressed')).toBe(
      'true'
    );
  });

  it('uses ≥44px tap targets on mobile and ≥12px chip text', () => {
    renderFilter('/today?category=agents');
    const chip = screen.getByRole('button', { name: 'Agents' });
    expect(chip.className).toContain('min-h-11');
    expect(chip.className).toContain('text-xs');
    expect(chip.className).not.toMatch(/text-\[(9|10|11)px\]/);
  });
});
