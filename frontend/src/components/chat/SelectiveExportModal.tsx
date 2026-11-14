import { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import api, { errorMessage, type StoredMessage } from '../../services/api';
import { Button, Modal, Notice, Skeleton, cn } from '../../ui';
import { toast } from '../../utils/toast';

type Format = 'markdown' | 'pdf' | 'json';
const FORMATS: { id: Format; label: string }[] = [
  { id: 'markdown', label: 'Markdown' },
  { id: 'pdf', label: 'PDF' },
  { id: 'json', label: 'JSON' },
];

/**
 * Export chosen messages. Loads the whole conversation itself (the chat view
 * may hold only the newest page) and selects by stable sequence number.
 */
export default function SelectiveExportModal({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const [messages, setMessages] = useState<StoredMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [format, setFormat] = useState<Format>('markdown');
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getConversation(conversationId, { limit: 1000 })
      .then((c) => {
        if (cancelled) return;
        const visible = c.messages.filter((m) => m.role !== 'system');
        setMessages(visible);
        setSelected(new Set(visible.map((m) => m.sequence)));
      })
      .catch((err) => !cancelled && setError(errorMessage(err, 'Could not load the messages')));
    return () => { cancelled = true; };
  }, [conversationId]);

  const all = messages?.length ?? 0;
  const allSelected = all > 0 && selected.size === all;
  const ordered = useMemo(() => [...selected].sort((a, b) => a - b), [selected]);

  const toggle = (sequence: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sequence)) next.delete(sequence); else next.add(sequence);
      return next;
    });

  const exportNow = async () => {
    setExporting(true);
    try {
      await api.downloadSelectedMessages(conversationId, ordered, format);
      toast.success(`Exported ${ordered.length} message${ordered.length === 1 ? '' : 's'}`);
      onClose();
    } catch (err) {
      toast.error(errorMessage(err, 'Export failed'));
    } finally {
      setExporting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!exporting}
      size="lg"
      title="Export messages"
      description="Choose the messages and a format."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={exporting}>Cancel</Button>
          <Button leading={<Download className="h-4 w-4" />} loading={exporting} disabled={!selected.size} onClick={exportNow}>
            Export {selected.size || ''}
          </Button>
        </>
      }
    >
      {error ? (
        <Notice tone="error">{error}</Notice>
      ) : !messages ? (
        <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : (
        <div className="space-y-4">
          <fieldset>
            <legend className="mb-2 text-small font-semibold text-ink">Format</legend>
            <div className="inline-flex rounded-sm border border-field-border p-0.5">
              {FORMATS.map((f) => (
                <label key={f.id} className={cn(
                  'cursor-pointer rounded-xs px-4 py-1.5 text-small font-semibold transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-focus',
                  format === f.id ? 'bg-primary text-on-primary' : 'text-ink-muted hover:text-ink'
                )}>
                  <input type="radio" name="export-format" value={f.id} checked={format === f.id} onChange={() => setFormat(f.id)} className="sr-only" />
                  {f.label}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="flex items-center justify-between">
            <label className="inline-flex cursor-pointer items-center gap-2 text-small text-ink-muted">
              <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--primary))]" checked={allSelected}
                onChange={() => setSelected(allSelected ? new Set() : new Set(messages.map((m) => m.sequence)))} />
              {allSelected ? 'All selected' : `${selected.size} of ${all} selected`}
            </label>
          </div>

          <ul className="max-h-[50vh] divide-y divide-hairline overflow-y-auto rounded-sm border border-hairline">
            {messages.map((m) => (
              <li key={m.id}>
                <label className={cn('flex cursor-pointer items-start gap-3 px-4 py-3', selected.has(m.sequence) && 'bg-canvas-soft')}>
                  <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--primary))]"
                    checked={selected.has(m.sequence)} onChange={() => toggle(m.sequence)} />
                  <span className="min-w-0">
                    <span className="block text-caption font-semibold text-ink-muted">
                      {m.role === 'user' ? 'You' : 'Answer'} · {new Date(m.timestamp).toLocaleString()}
                    </span>
                    <span className="mt-0.5 line-clamp-2 block text-small text-ink">{m.content}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}
