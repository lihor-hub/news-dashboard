// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Switch } from '../components/ui/switch';
import {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
} from '../components/ui/table';

describe('Badge', () => {
  it('renders children with the default variant', () => {
    render(<Badge>New</Badge>);
    expect(screen.getByText('New')).toBeTruthy();
  });

  it('applies a variant and extra className', () => {
    render(
      <Badge variant="destructive" className="extra">
        Bad
      </Badge>
    );
    const el = screen.getByText('Bad');
    expect(el.className).toContain('extra');
    expect(el.className).toContain('bg-destructive');
  });
});

describe('Input', () => {
  it('forwards type and other props', () => {
    render(<Input type="email" placeholder="email" />);
    const el = screen.getByPlaceholderText('email');
    expect(el.getAttribute('type')).toBe('email');
  });
});

describe('Switch', () => {
  it('reflects the checked state via aria', () => {
    render(<Switch checked aria-label="toggle" onCheckedChange={vi.fn()} />);
    const el = screen.getByLabelText('toggle');
    expect(el.getAttribute('aria-checked')).toBe('true');
  });
});

describe('Table', () => {
  it('renders all table subcomponents', () => {
    render(
      <Table>
        <TableCaption>Cap</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Head</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Cell</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell>Foot</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    );
    expect(screen.getByText('Cap')).toBeTruthy();
    expect(screen.getByText('Head')).toBeTruthy();
    expect(screen.getByText('Cell')).toBeTruthy();
    expect(screen.getByText('Foot')).toBeTruthy();
  });
});
