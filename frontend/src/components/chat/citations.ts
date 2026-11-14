/** Citation markers ([1], [1, 2]) in grounded answers. */

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
export const CITE_PREFIX = '#cite-';

/**
 * Rewrite citation markers as markdown links (`[1](#cite-1)`) so the
 * renderer can turn them into interactive chips. Fenced and inline code are
 * left untouched, so a literal "[1]" in code stays literal.
 */
export function linkCitations(markdown: string): string {
  return markdown
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part, index) =>
      index % 2 === 1
        ? part
        : part.replace(CITATION, (_, group: string) =>
            group
              .split(',')
              .map((n) => `[${n.trim()}](${CITE_PREFIX}${n.trim()})`)
              .join('')
          )
    )
    .join('');
}

/** Citation numbers used in an answer, ascending and unique. */
export function citedNumbers(markdown: string): number[] {
  const numbers = new Set<number>();
  for (const match of markdown.matchAll(CITATION)) {
    match[1].split(',').forEach((n) => numbers.add(Number(n.trim())));
  }
  return [...numbers].sort((a, b) => a - b);
}
