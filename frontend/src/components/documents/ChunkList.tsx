import { useMemo, useState } from 'react';
import { FileText, Search, X } from 'lucide-react';
import type { ChunkData } from '../../services/api';
import { Badge, EmptyState, IconButton, Input, Tabs } from '../../ui';

type Filter = 'all' | 'edited' | 'original';

export const chunkTitle = (chunk: ChunkData) => chunk.title || chunk.section_title || `Chunk ${chunk.chunk_index + 1}`;

/** Searchable list of a document's chunks; selecting one opens it. */
export default function ChunkList({ chunks, onOpen }: { chunks: ChunkData[]; onOpen: (chunk: ChunkData) => void }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');

  const edited = chunks.filter((c) => c.is_edited).length;
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return chunks.filter((c) => {
      if (filter === 'edited' && !c.is_edited) return false;
      if (filter === 'original' && c.is_edited) return false;
      return !q || c.content.toLowerCase().includes(q) || chunkTitle(c).toLowerCase().includes(q);
    });
  }, [chunks, query, filter]);

  return (
    <section aria-labelledby="chunks-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <h2 id="chunks-heading" className="text-heading-sm font-heavy">Chunks</h2>
        <div className="relative sm:w-80">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" aria-hidden />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search chunk text" aria-label="Search chunks" className="pl-11 pr-11" />
          {query && (
            <IconButton label="Clear search" size="sm" onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
              <X className="h-4 w-4" />
            </IconButton>
          )}
        </div>
      </div>
      <div className="mt-4">
        <Tabs
          label="Chunk filter"
          value={filter}
          onChange={setFilter}
          items={[
            { id: 'all', label: 'All', count: chunks.length },
            { id: 'edited', label: 'Edited', count: edited },
            { id: 'original', label: 'Original', count: chunks.length - edited },
          ]}
        />
      </div>

      {visible.length === 0 ? (
        <EmptyState className="mt-4" icon={<FileText className="h-8 w-8" />} title={query ? 'No matching chunks' : 'Nothing here'}>
          {query ? 'Try different words.' : filter === 'edited' ? 'No chunk has been edited yet.' : 'This document has no chunks.'}
        </EmptyState>
      ) : (
        <ol className="mt-4 divide-y divide-hairline rounded-md border border-hairline bg-canvas">
          {visible.map((chunk) => (
            <li key={chunk.id}>
              <button
                type="button"
                onClick={() => onOpen(chunk)}
                className="block w-full px-4 py-4 text-left transition-colors hover:bg-canvas-soft focus-visible:bg-canvas-soft"
              >
                <span className="flex items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate font-semibold text-ink">{chunkTitle(chunk)}</span>
                    <span className="mt-0.5 block text-caption text-ink-muted">
                      #{chunk.chunk_index + 1}
                      {chunk.page_numbers.length > 0 && <> · page {chunk.page_numbers.join(', ')}</>}
                      {' · '}{chunk.chunk_type} · {chunk.token_count} tokens
                    </span>
                  </span>
                  {chunk.is_edited && <Badge tone="warning" className="shrink-0">Edited{chunk.edit_count > 1 ? ` ×${chunk.edit_count}` : ''}</Badge>}
                </span>
                <span className="mt-2 line-clamp-2 block text-small text-ink-muted">{chunk.content}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
