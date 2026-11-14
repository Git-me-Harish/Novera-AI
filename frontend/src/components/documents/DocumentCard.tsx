import { Link, useNavigate } from 'react-router-dom';
import { FileText, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import type { Document } from '../../services/api';
import { Badge, IconButton, Menu, Spinner, type BadgeTone } from '../../ui';

const STATUS: Record<string, { label: string; tone: BadgeTone }> = {
  completed: { label: 'Ready', tone: 'success' },
  processing: { label: 'Indexing', tone: 'warning' },
  pending: { label: 'Queued', tone: 'neutral' },
  failed: { label: 'Failed', tone: 'error' },
};

/**
 * One document row. Ready documents open the chunk editor; others show
 * their status only. Delete is offered to administrators.
 */
export default function DocumentCard({
  document: doc,
  onDelete,
  canManage,
}: {
  document: Document;
  onDelete: (doc: Document) => void;
  canManage: boolean;
}) {
  const navigate = useNavigate();
  const status = STATUS[doc.status] ?? { label: doc.status, tone: 'neutral' as const };
  const ready = doc.status === 'completed';
  const busy = doc.status === 'processing' || doc.status === 'pending';

  const name = (
    <span className="flex min-w-0 items-center gap-3">
      <FileText className="h-5 w-5 shrink-0 text-ink-muted" aria-hidden />
      <span className="truncate font-semibold" title={doc.filename}>{doc.filename}</span>
    </span>
  );

  return (
    <li className="flex items-center gap-4 px-4 py-3.5">
      <div className="min-w-0 flex-1">
        {ready ? <Link to={`/documents/${doc.id}/edit`} className="text-ink hover:underline">{name}</Link> : <span className="text-ink">{name}</span>}
        <p className="mt-1 pl-8 text-caption text-ink-muted">
          <span className="capitalize">{doc.doc_type}</span>
          {doc.department && <> · {doc.department}</>}
          {ready && <> · {doc.total_pages} page{doc.total_pages === 1 ? '' : 's'} · {doc.total_chunks} chunks</>}
          {' · '}uploaded {formatDistanceToNow(new Date(doc.upload_date), { addSuffix: true })}
        </p>
      </div>
      <Badge tone={status.tone} className="shrink-0">
        {busy && <Spinner className="h-3 w-3" />}
        {status.label}
      </Badge>
      {canManage ? (
        <Menu
          label={`Actions for ${doc.filename}`}
          items={[
            ...(ready ? [{ label: 'Open and edit', icon: <Pencil className="h-4 w-4" />, onSelect: () => navigate(`/documents/${doc.id}/edit`) }] : []),
            { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, danger: true, onSelect: () => onDelete(doc) },
          ]}
          trigger={(props) => (
            <IconButton {...props} label={`Actions for ${doc.filename}`}>
              <MoreHorizontal className="h-5 w-5" />
            </IconButton>
          )}
        />
      ) : (
        <span className="w-10" aria-hidden />
      )}
    </li>
  );
}
