export function renderMarkdown(md: string): string {
  const escape = (s: string) =>
    s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
  const decodeEscapedMarkdown = (s: string) =>
    s
      .replace(/&quot;/g, '"')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&');
  const safeHref = (rawHref: string): string | null => {
    const href = decodeEscapedMarkdown(rawHref).trim();
    if (!href || /[\s\p{Cc}]/u.test(href)) return null;

    try {
      const url = new URL(href);
      return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
    } catch {
      return null;
    }
  };
  const lines = md.split('\n');
  let html = '';
  let inCode = false;
  let inList = false;
  const para: string[] = [];

  const flushPara = () => {
    if (para.length) {
      html += `<p>${inline(para.join(' '))}</p>`;
      para.length = 0;
    }
  };

  const inline = (s: string) =>
    s
      .replace(/`([^`]+)`/g, (_, t: string) => `<code>${escape(t)}</code>`)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\[([^\]]+)\]\((.+)\)/g, (_, label: string, rawHref: string) => {
        const href = safeHref(rawHref);
        return href
          ? `<a href="${escape(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`
          : label;
      });

  for (const raw of lines) {
    if (raw.startsWith('```')) {
      if (inCode) {
        html += '</code></pre>';
        inCode = false;
      } else {
        flushPara();
        html += '<pre><code>';
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      html += escape(raw) + '\n';
      continue;
    }
    if (raw.startsWith('## ')) {
      flushPara();
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      html += `<h2>${inline(escape(raw.slice(3)))}</h2>`;
      continue;
    }
    if (raw.startsWith('- ')) {
      flushPara();
      if (!inList) {
        html += '<ul>';
        inList = true;
      }
      html += `<li>${inline(escape(raw.slice(2)))}</li>`;
      continue;
    }
    if (raw.trim() === '') {
      flushPara();
      if (inList) {
        html += '</ul>';
        inList = false;
      }
      continue;
    }
    para.push(escape(raw));
  }
  flushPara();
  if (inList) html += '</ul>';
  if (inCode) html += '</code></pre>';
  return html;
}
