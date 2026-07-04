import { describe, it, expect } from 'vitest';
import { renderMarkdown } from '../lib/renderMarkdown';

describe('renderMarkdown', () => {
  it('renders a level-2 header', () => {
    expect(renderMarkdown('## Heading')).toBe('<h2>Heading</h2>');
  });

  it('renders bold text', () => {
    expect(renderMarkdown('this is **bold** text')).toBe(
      '<p>this is <strong>bold</strong> text</p>'
    );
  });

  it('renders a fenced code block', () => {
    expect(renderMarkdown('```\nconst x = 1;\n```')).toBe('<pre><code>const x = 1;\n</code></pre>');
  });

  it('escapes HTML inside code blocks', () => {
    expect(renderMarkdown('```\n<script>\n```')).toBe('<pre><code>&lt;script&gt;\n</code></pre>');
  });

  it('renders an unordered list', () => {
    expect(renderMarkdown('- one\n- two')).toBe('<ul><li>one</li><li>two</li></ul>');
  });

  it('renders inline code', () => {
    expect(renderMarkdown('use `foo()` here')).toBe('<p>use <code>foo()</code> here</p>');
  });

  it('renders a safe http(s) link', () => {
    expect(renderMarkdown('[text](https://example.com)')).toBe(
      '<p><a href="https://example.com/" target="_blank" rel="noopener noreferrer">text</a></p>'
    );
  });

  it('strips a javascript: link and keeps the label as plain text', () => {
    expect(renderMarkdown('[click me](javascript:alert(1))')).toBe('<p>click me</p>');
  });

  it('round-trips an ampersand in a link href without double-escaping', () => {
    expect(renderMarkdown('[text](https://example.com/?a=1&b=2)')).toBe(
      '<p><a href="https://example.com/?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">text</a></p>'
    );
  });

  it('escapes plain paragraph text', () => {
    expect(renderMarkdown('<b>raw</b> & "quoted"')).toBe(
      '<p>&lt;b&gt;raw&lt;/b&gt; &amp; &quot;quoted&quot;</p>'
    );
  });
});
