import { useState } from 'react';
import { History, RotateCcw, Sparkles, Trash2 } from 'lucide-react';
import api, { errorMessage, type ChunkData } from '../../services/api';
import { Badge, Button, Field, Input, Modal, Notice, Textarea } from '../../ui';
import { toast } from '../../utils/toast';
import { chunkTitle } from './ChunkList';

/** Mirrors ChunkEditRequest.new_content on the server. */
const MIN_CHARS = 10;
const MAX_CHARS = 10_000;

type Confirm = null | 'revert' | 'delete';

/**
 * View or (for administrators) edit one chunk. Saving re-embeds the chunk, so
 * the next answer retrieves the corrected text.
 */
export default function ChunkEditor({
  chunk,
  canEdit,
  onUpdated,
  onRemoved,
  onHistory,
  onClose,
}: {
  chunk: ChunkData;
  canEdit: boolean;
  /** A changed chunk, or nothing when the caller should reload (revert). */
  onUpdated: (chunk?: ChunkData) => void;
  onRemoved: (chunkId: string) => void;
  onHistory: (chunkId: string) => void;
  onClose: () => void;
}) {
  const [content, setContent] = useState(chunk.content);
  const [title, setTitle] = useState(chunk.title ?? '');
  const [busy, setBusy] = useState<null | 'save' | 'title' | 'generate' | 'revert' | 'delete'>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [error, setError] = useState<string | null>(null);

  const dirty = content !== chunk.content;
  const titleDirty = title.trim() !== (chunk.title ?? '') && title.trim() !== '';
  const length = content.trim().length;
  const tooShort = length < MIN_CHARS;
  const tooLong = content.length > MAX_CHARS;

  const run = async (kind: NonNullable<typeof busy>, task: () => Promise<void>) => {
    setBusy(kind);
    setError(null);
    try {
      await task();
    } catch (err) {
      setError(errorMessage(err, 'That did not work. Please try again.'));
    } finally {
      setBusy(null);
    }
  };

  const save = () => run('save', async () => {
    const updated = await api.editChunk(chunk.id, content);
    let next = updated;
    if (titleDirty) {
      await api.updateChunkTitle(chunk.id, title.trim());
      next = { ...updated, title: title.trim() };
    }
    onUpdated(next);
    toast.success('Chunk saved and re-indexed');
    onClose();
  });

  const saveTitle = () => run('title', async () => {
    await api.updateChunkTitle(chunk.id, title.trim());
    onUpdated({ ...chunk, title: title.trim() });
    toast.success('Title updated');
  });

  const generate = () => run('generate', async () => {
    const result = await api.generateChunkTitle(chunk.id);
    setTitle(result.title);
    onUpdated({ ...chunk, title: result.title });
  });

  const revert = () => run('revert', async () => {
    await api.revertChunk(chunk.id);
    onUpdated();
    toast.success('Chunk restored to its original text');
    onClose();
  });

  const remove = () => run('delete', async () => {
    await api.deleteChunk(chunk.id);
    onRemoved(chunk.id);
    toast.success('Chunk deleted');
    onClose();
  });

  const confirming = confirm !== null;

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={busy === null}
      size="xl"
      title={chunkTitle(chunk)}
      description={
        <>
          Chunk {chunk.chunk_index + 1}
          {chunk.page_numbers.length > 0 && <> · page {chunk.page_numbers.join(', ')}</>}
          {' · '}{chunk.chunk_type} · {chunk.token_count} tokens
          {chunk.is_edited && chunk.edited_at && <> · edited {new Date(chunk.edited_at).toLocaleString()}</>}
        </>
      }
      footer={
        confirming ? (
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)} disabled={busy !== null}>Keep chunk</Button>
            {confirm === 'revert' ? (
              <Button loading={busy === 'revert'} onClick={revert}>Restore original</Button>
            ) : (
              <Button variant="danger" loading={busy === 'delete'} onClick={remove}>Delete chunk</Button>
            )}
          </>
        ) : canEdit ? (
          <>
            <div className="flex flex-wrap gap-2 sm:mr-auto">
              {chunk.is_edited && (
                <>
                  <Button variant="ghost" size="sm" leading={<History className="h-4 w-4" />} onClick={() => onHistory(chunk.id)}>History</Button>
                  <Button variant="ghost" size="sm" leading={<RotateCcw className="h-4 w-4" />} onClick={() => setConfirm('revert')}>Restore original</Button>
                </>
              )}
              <Button variant="ghost" size="sm" leading={<Trash2 className="h-4 w-4" />} onClick={() => setConfirm('delete')}>Delete</Button>
            </div>
            <Button variant="secondary" onClick={onClose} disabled={busy !== null}>Cancel</Button>
            <Button onClick={save} loading={busy === 'save'} disabled={!dirty || tooShort || tooLong}>Save and re-index</Button>
          </>
        ) : (
          <>
            {chunk.is_edited && <Button variant="ghost" leading={<History className="h-4 w-4" />} onClick={() => onHistory(chunk.id)}>History</Button>}
            <Button variant="secondary" onClick={onClose}>Close</Button>
          </>
        )
      }
    >
      <div className="space-y-5">
        {confirm === 'revert' && (
          <Notice tone="warning" title="Restore the original text?">
            Every edit to this chunk is discarded and the original extracted text is re-indexed.
          </Notice>
        )}
        {confirm === 'delete' && (
          <Notice tone="error" title="Delete this chunk?">
            Answers will no longer be able to use or cite this passage. This cannot be undone.
          </Notice>
        )}
        {error && <Notice tone="error">{error}</Notice>}

        {canEdit ? (
          <>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
              <Field label="Title" hint="Shown in the chunk list. Generated titles summarise the passage." className="flex-1">
                <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} disabled={confirming} />
              </Field>
              <div className="flex gap-2 sm:mt-7">
                <Button
                  variant="secondary"
                  leading={<Sparkles className="h-4 w-4" />}
                  loading={busy === 'generate'}
                  onClick={generate}
                  disabled={confirming}
                >
                  Generate
                </Button>
                {titleDirty && !dirty && (
                  <Button variant="secondary" loading={busy === 'title'} onClick={saveTitle}>Save title</Button>
                )}
              </div>
            </div>
            <Field
              label="Text"
              hint={
                tooLong
                  ? undefined
                  : `${content.length.toLocaleString()} / ${MAX_CHARS.toLocaleString()} characters. Saving updates what answers retrieve and quote.`
              }
              error={tooLong ? `Keep it under ${MAX_CHARS.toLocaleString()} characters.` : dirty && tooShort ? `Write at least ${MIN_CHARS} characters.` : undefined}
            >
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={16}
                disabled={confirming}
                className="font-mono text-small leading-relaxed"
              />
            </Field>
          </>
        ) : (
          <>
            {chunk.is_edited && <Badge tone="warning">Edited by an administrator</Badge>}
            <div className="whitespace-pre-wrap break-words rounded-sm border border-hairline bg-canvas-soft p-4 font-mono text-small leading-relaxed text-ink">
              {chunk.content}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
