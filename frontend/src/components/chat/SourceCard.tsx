import { forwardRef } from 'react';
import { FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Source } from '../../services/api';
import { cn } from '../../ui';

/**
 * A retrieved passage the answer relied on (context card). Numbered exactly
 * as the answer cites it, so "[2]" and card 2 are the same evidence.
 */
export const SourceCard = forwardRef<HTMLLIElement, {
  source: Source;
  number: number;
  cited: boolean;
  active?: boolean;
  canOpen?: boolean;
}>(function SourceCard({ source, number, cited, active, canOpen }, ref) {
  const location = [source.page ? `Page ${source.page}` : null, source.section].filter(Boolean).join(' · ');
  return (
    <li
      ref={ref}
      id={`source-${source.chunk_id}`}
      className={cn(
        'rounded-md border bg-canvas p-4 transition-colors',
        active ? 'border-ink' : 'border-hairline',
        !cited && 'opacity-80'
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            'mt-0.5 flex h-6 min-w-[24px] items-center justify-center rounded-xs text-caption font-semibold',
            active ? 'bg-primary text-on-primary' : 'bg-canvas-tint text-ink'
          )}
          aria-hidden
        >
          {number}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-label font-semibold text-ink">
            <FileText className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden />
            <span className="truncate">{source.document}</span>
          </p>
          {location && <p className="mt-0.5 text-caption text-ink-muted">{location}</p>}
          {source.excerpt && (
            <blockquote className="mt-2 line-clamp-6 border-l-2 border-hairline pl-3 text-small text-ink-muted">
              {source.excerpt}
            </blockquote>
          )}
          <div className="mt-2 flex items-center gap-3 text-caption">
            {!cited && <span className="text-ink-muted">Retrieved, not cited</span>}
            {canOpen && source.document_id && (
              <Link to={`/documents/${source.document_id}/edit`} className="text-link hover:underline">
                Open document
              </Link>
            )}
          </div>
        </div>
      </div>
    </li>
  );
});

export default SourceCard;
