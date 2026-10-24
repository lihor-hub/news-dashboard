// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '../components/ui/dialog';
import { Sheet, SheetContent, SheetTitle } from '../components/ui/sheet';
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

describe('Button touch sizing', () => {
  it('grows default and icon buttons to 44px on coarse pointers', () => {
    render(
      <>
        <Button>Go</Button>
        <Button size="icon" aria-label="icon" />
      </>
    );
    expect(screen.getByText('Go').className).toContain('pointer-coarse:h-touch');
    expect(screen.getByLabelText('icon').className).toContain('pointer-coarse:size-touch');
  });

  it('offers always-44px touch sizes', () => {
    render(
      <>
        <Button size="touch">Tap</Button>
        <Button size="icon-touch" aria-label="tap icon" />
      </>
    );
    expect(screen.getByText('Tap').className).toContain('h-touch');
    expect(screen.getByLabelText('tap icon').className).toContain('size-touch');
  });

  it('uses the 8px control radius', () => {
    render(<Button>R</Button>);
    expect(screen.getByText('R').className).toContain('rounded-md');
  });
});

describe('Input touch sizing', () => {
  it('reaches 44px on coarse pointers', () => {
    render(<Input placeholder="name" />);
    expect(screen.getByPlaceholderText('name').className).toContain('pointer-coarse:h-touch');
  });
});

describe('Switch hit area', () => {
  it('extends its hit area to at least 44px without growing the visual track', () => {
    render(<Switch aria-label="hit" />);
    const el = screen.getByLabelText('hit');
    expect(el.className).toContain('after:-inset-3');
    expect(el.className).toContain('h-5');
  });
});

describe('Sheet bottom variant', () => {
  it('renders a rounded bottom sheet with a grab handle and safe-area padding', () => {
    render(
      <Sheet open>
        <SheetContent side="bottom">
          <SheetTitle>Options</SheetTitle>
        </SheetContent>
      </Sheet>
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog.className).toContain('rounded-t-2xl');
    expect(dialog.className).toContain('safe-area-inset-bottom');
    expect(dialog.className).toContain('ease-spring');
    const handle = dialog.querySelector('[data-slot="sheet-handle"]');
    expect(handle).not.toBeNull();
    expect(handle?.getAttribute('aria-hidden')).toBe('true');
  });

  it('omits the grab handle on side sheets', () => {
    render(
      <Sheet open>
        <SheetContent side="right">
          <SheetTitle>Nav</SheetTitle>
        </SheetContent>
      </Sheet>
    );
    expect(screen.getByRole('dialog').querySelector('[data-slot="sheet-handle"]')).toBeNull();
  });
});

describe('Dialog small-screen layout', () => {
  it('is an inset, scrollable, 16px-rounded card with an elevation token', () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Hi</DialogTitle>
        </DialogContent>
      </Dialog>
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog.className).toContain('w-[calc(100%-1.5rem)]');
    expect(dialog.className).toContain('max-h-[calc(100dvh-1.5rem)]');
    expect(dialog.className).toContain('overflow-y-auto');
    expect(dialog.className).toContain('rounded-2xl');
    expect(dialog.className).toContain('shadow-elevation-3');
  });
});
