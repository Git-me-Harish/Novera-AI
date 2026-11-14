import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, { errorMessage, type EditHistoryItem } from '../../services/api';
import { Button, EmptyState, Modal, Notice, Skeleton } from '../../ui';

/** Every saved edit of one chunk, newest first, with before/after text. */
export default function EditHistoryModal({ chunkId, onClose }: { chunkId: string; onClose: () => void }) {
  const [history, setHistory] = useState<EditHistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getChunkHistory(chunkId, 50)
      .then((items) => !cancelled && setHistory(items))
      .catch((err) => !cancelled && setError(errorMessage(err, 'Could not load the history')));
    return () => { cancelled = true; };
  }, [chunkId]);

  return (
    <Modal open onClose={onClose} size="xl" title="Edit history" footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {error ? (
        <Notice tone="error">{error}</Notice>
      ) : history === null ? (
        <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : history.length === 0 ? (
        <EmptyState icon={<History className="h-8 w-8" />} title="No edits yet">This chunk still has its original text.</EmptyState>
      ) : (
        <ol className="space-y-3">
          {history.map((item, i) => (
            <li key={item.id}>
              <details className="group rounded-sm border border-hairline" open={i === 0}>
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 hover:bg-canvas-soft">
                  <span className="min-w-0">
                    <span className="block text-small font-semibold text-ink">
                      {item.edited_by_name ?? 'A former member'}
                    </span>
                    <span className="block text-caption text-ink-muted">
                      <time dateTime={item.edited_at} title={new Date(item.edited_at).toLocaleString()}>
                        {formatDistanceToNow(new Date(item.edited_at), { addSuffix: true })}
                      </time>
                      {item.change_summary && <> · {item.change_summary}</>}
                    </span>
                  </span>
                  <span className="text-caption text-ink-muted group-open:hidden">Show</span>
                  <span className="hidden text-caption text-ink-muted group-open:inline">Hide</span>
                </summary>
                <div className="grid gap-3 border-t border-hairline p-4 md:grid-cols-2">
                  {[
                    { label: 'Before', text: item.old_content },
                    { label: 'After', text: item.new_content },
                  ].map((side) => (
                    <div key={side.label}>
                      <p className="mb-1.5 text-caption font-semibold text-ink-muted">{side.label}</p>
                      <div className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded-sm bg-canvas-soft p-3 font-mono text-caption leading-relaxed text-ink">
                        {side.text}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}
