#!/usr/bin/env node
/**
 * Fails when source files use colour or shadow utilities outside the design
 * system (docs/Design.md → tailwind.config.js). The palette is replaced, so
 * such classes silently generate no CSS and leave elements unstyled.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = new URL('../src', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const LEGACY_PALETTE =
  'gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black|secondary';
const PATTERNS = [
  // bg-gray-50, text-blue-600/50, border-red-200, from-primary-50 …
  new RegExp(`\\b(?:[a-z-]+:)*(?:bg|text|border|ring|from|via|to|divide|outline|fill|stroke|placeholder|decoration|accent|caret)-(?:${LEGACY_PALETTE})(?:-\\d{2,3})?(?:\\/\\d+)?\\b`, 'g'),
  // numbered primary scale (primary-600) — the token is plain `primary`
  /\b(?:[a-z-]+:)*(?:bg|text|border|ring|from|via|to)-primary-\d{2,3}\b/g,
  // shadows: depth comes from the neutral ladder
  /\b(?:[a-z-]+:)*shadow(?:-(?:sm|md|lg|xl|2xl|inner))?\b(?!-none)/g,
  /\bbg-gradient-to-[a-z]+\b/g,
  /\bdark:/g,
];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(tsx|ts)$/.test(name) ? [path] : [];
  });
}

let total = 0;
const report = [];
for (const file of walk(ROOT)) {
  // Comments may talk about shadows and colours; only code counts.
  const source = readFileSync(file, 'utf8')
    .split(/\r?\n/)
    .filter((line) => !/^\s*(\/\/|\/?\*)/.test(line))
    .join('\n');
  const hits = PATTERNS.flatMap((re) => source.match(re) ?? []);
  if (hits.length) {
    total += hits.length;
    report.push([relative(ROOT, file), hits.length, [...new Set(hits)].slice(0, 4).join(' ')]);
  }
}
report.sort((a, b) => b[1] - a[1]);
for (const [file, count, sample] of report) console.log(`${String(count).padStart(5)}  ${file}  (${sample})`);
console.log(total ? `\n${total} off-system classes in ${report.length} files` : 'Design tokens: clean');
process.exit(total ? 1 : 0);
