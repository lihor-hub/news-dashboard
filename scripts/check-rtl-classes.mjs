#!/usr/bin/env node
import { parseSync, traverse } from '@babel/core';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve, relative } from 'node:path';
import { pathToFileURL } from 'node:url';

// These physical anchors describe centered or deliberately physical surfaces.
// Count each full token so copying an exception does not silently expand it.
export const exceptions = [
  ['components/LessonConceptGraph.tsx', 'left-1/2', 'Centered graph label'],
  ['components/aiStats/KnowledgeGraph.tsx', 'left-1/2', 'Centered graph label'],
  ['components/article/ArticleRow.tsx', 'left-1/2', 'Centered tooltip'],
  ['components/article/ArticleSelectionActions.tsx', 'left-1/2', 'Centered selection toolbar'],
  ['components/ui/dialog.tsx', 'left-[50%]', 'Centered dialog'],
  ['components/LessonConceptGraph.tsx', 'left-2', 'Physical graph canvas hint'],
  ['components/aiStats/KnowledgeGraph.tsx', 'left-2', 'Physical graph canvas hint'],
  ['components/article/SwipeableRow.tsx', 'left-0', 'Physical swipe reveal edge'],
  ['components/article/SwipeableRow.tsx', 'right-0', 'Physical swipe reveal edge'],
  ['components/ui/sheet.tsx', 'left-0', 'Explicit left sheet variant'],
  ['components/ui/sheet.tsx', 'border-r', 'Explicit left sheet inner border'],
  ['components/ui/sheet.tsx', 'right-0', 'Explicit right sheet variant'],
  ['components/ui/sheet.tsx', 'border-l', 'Explicit right sheet inner border'],
].map(([file, token, reason]) => ({ file: `frontend/src/${file}`, token, count: 1, reason }));

function utility(token) {
  let depth = 0;
  let start = 0;
  for (let index = 0; index < token.length; index += 1) {
    const character = token[index];
    if (character === '\\') {
      index += 1;
      continue;
    }
    if (character === '[' || character === '(') depth += 1;
    if (character === ']' || character === ')') depth -= 1;
    if (character === ':' && depth === 0) start = index + 1;
  }
  return token.slice(start).replace(/^!|!$/g, '').replace(/^-/, '');
}

function physical(token) {
  const value = utility(token);
  return (
    /^(?:(?:m|p)[lr]|left|right|scroll-[mp][lr])-/.test(value) ||
    /^(?:text|float|clear)-(?:left|right)$/.test(value) ||
    /^(?:border-[lr]|rounded-(?:l|r|tl|tr|bl|br))(?:-|$)/.test(value)
  );
}

// Follow class sinks and local bindings, rather than interpreting prose as CSS.
// This is intentionally file-local: imported values, runtime-generated utility
// names, and custom class-writing APIs need separate review.
function isClassUse(path, seen = new Set()) {
  if (seen.has(path.node)) return false;
  seen.add(path.node);
  for (let current = path; current.parentPath; current = current.parentPath) {
    const parent = current.parentPath;
    const node = parent.node;
    // Conditions consume values as predicates, not as rendered class names.
    if (parent.isBinaryExpression() && node.operator !== '+') return false;
    if (parent.isUnaryExpression()) return false;
    if (parent.isConditionalExpression() && current.key === 'test') return false;
    if (parent.isLogicalExpression() && node.operator === '&&' && current.key === 'left')
      return false;
    if (parent.isJSXAttribute()) return node.name.name === 'className';
    if (parent.isCallExpression()) {
      const callee = node.callee;
      if (callee.type === 'Identifier' && callee.name === 'Boolean') return false;
      if (callee.type === 'Identifier' && ['cn', 'cva', 'clsx', 'twMerge'].includes(callee.name))
        return true;
      if (callee.type === 'MemberExpression') {
        if (callee.property.name === 'attr' && node.arguments[0]?.value === 'class') return true;
        if (
          callee.object.type === 'MemberExpression' &&
          callee.object.property.name === 'classList' &&
          ['add', 'remove', 'toggle', 'replace'].includes(callee.property.name)
        )
          return true;
      }
    }
    if (parent.isAssignmentExpression() && current.key === 'right') {
      if (node.left.type === 'MemberExpression' && node.left.property.name === 'className')
        return true;
      if (node.left.type === 'Identifier') {
        const binding = parent.scope.getBinding(node.left.name);
        return binding?.referencePaths.some((reference) => isClassUse(reference, seen)) ?? false;
      }
    }
    if (parent.isVariableDeclarator() && node.id.type === 'Identifier') {
      const binding = parent.scope.getBinding(node.id.name);
      return binding?.referencePaths.some((reference) => isClassUse(reference, seen)) ?? false;
    }
  }
  return false;
}

export function checkSources(sources, allowed = exceptions) {
  const counts = new Map();
  const findings = [];
  const allowlist = new Map();
  const keyOf = (file, token) => `${file}\0${token}`;
  for (const entry of allowed) {
    const key = keyOf(entry.file, entry.token);
    if (allowlist.has(key)) findings.push(`duplicate exception: ${entry.file} ${entry.token}`);
    if (
      !Number.isInteger(entry.count) ||
      entry.count < 1 ||
      !entry.reason?.trim() ||
      !physical(entry.token)
    ) {
      findings.push(`invalid exception: ${entry.file} ${entry.token}`);
    }
    allowlist.set(key, entry);
  }
  for (const [file, source] of sources) {
    const ast = parseSync(source, {
      filename: file,
      configFile: false,
      babelrc: false,
      presets: [['@babel/preset-typescript', { ignoreExtensions: true }]],
      plugins: ['@babel/plugin-syntax-jsx'],
    });
    const inspect = (value, node) => {
      for (const token of value.split(/\s+/).filter(Boolean)) {
        if (!physical(token)) continue;
        const key = keyOf(file, token);
        counts.set(key, (counts.get(key) ?? 0) + 1);
        if (!allowlist.has(key))
          findings.push(`${file}:${node.loc?.start.line ?? 1}: ${token} — use a logical utility`);
      }
    };
    traverse(ast, {
      StringLiteral(path) {
        if (isClassUse(path)) inspect(path.node.value, path.node);
      },
      TemplateElement(path) {
        if (isClassUse(path)) inspect(path.node.value.cooked ?? path.node.value.raw, path.node);
      },
    });
  }
  for (const [key, entry] of allowlist) {
    const actual = counts.get(key) ?? 0;
    if (actual !== entry.count)
      findings.push(
        `${entry.file}: ${entry.token} exception expected ${entry.count}, found ${actual}`
      );
  }
  return findings;
}

function readSources(root) {
  const sources = new Map();
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory() && entry.name !== '__tests__') visit(path);
      if (
        entry.isFile() &&
        /\.tsx?$/.test(entry.name) &&
        !/\.(test|spec)\.tsx?$/.test(entry.name)
      ) {
        sources.set(relative(root, path).split('\\').join('/'), readFileSync(path, 'utf8'));
      }
    }
  }
  visit(resolve(root, 'frontend/src'));
  return sources;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const findings = checkSources(readSources(process.cwd()));
  if (findings.length) {
    console.error(`RTL class guard failed:\n${findings.join('\n')}`);
    process.exitCode = 1;
  } else console.log('RTL class guard passed (exact physical-layout exceptions verified).');
}
