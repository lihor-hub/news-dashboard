import assert from 'node:assert/strict';
import { test } from 'node:test';
import { checkSources } from './check-rtl-classes.mjs';

const file = 'frontend/src/components/Example.tsx';
const check = (source, exceptions = []) => checkSources(new Map([[file, source]]), exceptions);

test('rejects physical utilities in responsive and arbitrary variants, including negatives', () => {
  const findings = check(
    `<div className="md:ml-2 [&:not(:first-child)]:-mr-1 !text-right border-l-2 rounded-tr-lg" />`
  );
  for (const token of [
    'md:ml-2',
    '[&:not(:first-child)]:-mr-1',
    '!text-right',
    'border-l-2',
    'rounded-tr-lg',
  ]) {
    assert.ok(
      findings.some((finding) => finding.includes(token)),
      token
    );
  }
});

test('checks class helper strings and interpolated template branches', () => {
  const source = "const style = cn('pl-4', active ? `sm:pr-2 ${extra}` : 'text-left');";
  assert.equal(check(source).length, 3);
});

test('accepts logical utilities, JSX prose, API paths and physical animation names', () => {
  assert.deepEqual(
    check(`
    // left-0 is intentional prose in a comment.
    const endpoint = '/api/left-navigation';
    const animation = 'data-[state=open]:slide-in-from-left';
    const body = <p className="ms-2 pe-4 text-start border-s rounded-se-lg">right-to-left reading</p>;
  `),
    []
  );
});

test('splits variants outside arbitrary values and preserves full exception tokens', () => {
  const source = `<div className="[&:nth-child(2)]:left-[calc(50%+var(--gap))]" />`;
  const exception = {
    file,
    token: '[&:nth-child(2)]:left-[calc(50%+var(--gap))]',
    count: 1,
    reason: 'Centered chart marker',
  };
  assert.deepEqual(check(source, [exception]), []);
  assert.ok(check(source, [{ ...exception, token: 'left-[calc(50%+var(--gap))]' }]).length > 0);
});

test('rejects a duplicated occurrence of an allowed centered anchor', () => {
  const exception = { file, token: 'left-1/2', count: 1, reason: 'Centered marker' };
  assert.deepEqual(check('<div className="left-1/2" />', [exception]), []);
  assert.ok(
    check('<div className="left-1/2"><i className="left-1/2" /></div>', [exception]).some(
      (finding) => finding.includes('expected 1, found 2')
    )
  );
});

test('rejects stale, missing-file and duplicate exception definitions', () => {
  const exception = { file, token: 'left-1/2', count: 1, reason: 'Centered marker' };
  assert.ok(
    check('<div />', [exception]).some((finding) => finding.includes('expected 1, found 0'))
  );
  assert.ok(check('<div />', [{ ...exception, file: 'deleted.tsx' }]).length > 0);
  assert.ok(
    check('<div className="left-1/2" />', [exception, exception]).some((finding) =>
      finding.includes('duplicate exception')
    )
  );
});

test('fails closed on invalid TSX', () => {
  assert.throws(() => check('<div className='));
});

test('ignores quoted prose and ordinary JSX attributes', () => {
  assert.deepEqual(
    check(`
    const label = 'Use right-to-left reading';
    const title = 'left-hand navigation';
    const endpoint = '/api/left-navigation';
    const body = <div title={title} aria-label={label} data-url={endpoint} placeholder="right-side label" />;
  `),
    []
  );
});

test('follows local standalone class values and aliases into class use', () => {
  const findings = check(`
    const spacing = 'ml-2';
    const classes = spacing;
    const variant = active ? 'text-right' : 'text-left';
    const body = <div className={cn(classes, variant)} />;
  `);
  assert.equal(findings.length, 3);
});

test('checks cva variants, clsx object keys and DOM class assignments', () => {
  assert.equal(
    check(`
    const style = cva('pl-4', { variants: { side: { physical: 'right-0' } } });
    const classes = clsx({ 'mr-2': active });
    node.className = 'left-0';
    node.classList.add('text-left');
    selection.attr('class', 'rounded-tr-none');
  `).length,
    6
  );
});

test('does not treat comparison operands or conditional tests as class values', () => {
  assert.deepEqual(
    check(`
    const body = <div className={cn(
      label === 'left-hand navigation' && 'ms-2',
      direction === 'right-to-left' ? 'text-start' : 'text-end',
      !'left-hand prose' && 'pe-2'
    )} />;
  `),
    []
  );
  assert.equal(
    check(`
    const body = <div className={cn(active && 'ml-2', active ? 'text-left' : 'text-right')} />;
  `).length,
    3
  );
});

test('follows static reassignment values into identifier class sinks', () => {
  assert.equal(
    check(`
    let classes = '';
    classes = 'ml-2';
    const body = <div className={classes} />;
  `).length,
    1
  );
  assert.deepEqual(
    check(`
    let label = '';
    label = 'left-hand navigation';
    const body = <div title={label} />;
  `),
    []
  );
});
