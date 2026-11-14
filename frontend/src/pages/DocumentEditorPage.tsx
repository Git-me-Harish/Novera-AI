import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Eye, FileWarning, Pencil, Sparkles } from 'lucide-react';
import api, { errorMessage, type ChunkData, type DocumentEditStats, type DocumentInfo } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { toast } from '../utils/toast';
import DocumentViewer from '../components/documents/DocumentViewer';
import ChunkList from '../components/documents/ChunkList';
import ChunkEditor from '../components/documents/ChunkEditor';
import EditHistoryModal from '../components/documents/EditHistoryModal';
import DocumentMetadataEditor from '../components/documents/DocumentMetadataEditor';
import { Badge, Button, EmptyState, Modal, PageHeader, PageLoader, PixelLoader } from '../ui';

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0">
      <dt className="text-caption text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-heading-sm font-heavy tabular-nums text-ink">{value}</dd>
    </div>
  );
}

export default function DocumentEditorPage() {
  const { documentId = '' } = useParams<{ documentId: string }>();
  const { isAdmin } = useAuth();

  const [info, setInfo] = useState<DocumentInfo | null>(null);
  const [chunks, setChunks] = useState<ChunkData[]>([]);
  const [stats, setStats] = useState<DocumentEditStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [previewing, setPreviewing] = useState(false);
  const [editingDetails, setEditingDetails] = useState(false);
  const [open, setOpen] = useState<ChunkData | null>(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [confirmTitles, setConfirmTitles] = useState(false);
  const [generating, setGenerating] = useState<number | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const [docInfo, chunkList, editStats] = await Promise.all([
        api.getDocumentInfo(documentId),
        api.getDocumentChunks(documentId),
        api.getDocumentEditStats(documentId),
      ]);
      setInfo(docInfo);
      setChunks(chunkList);
      setStats(editStats);
    } catch (err) {
      if (!silent) setError(errorMessage(err, 'This document could not be loaded.'));
      else toast.error(errorMessage(err, 'Could not refresh the document'));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [documentId]);

  useEffect(() => { load(); }, [load]);

  const refreshStats = () => api.getDocumentEditStats(documentId).then(setStats).catch(() => undefined);

  const onUpdated = (chunk?: ChunkData) => {
    if (!chunk) {
      load(true); // revert: the server rebuilt the chunk
      return;
    }
    setChunks((prev) => prev.map((c) => (c.id === chunk.id ? chunk : c)));
    setOpen((current) => (current?.id === chunk.id ? chunk : current));
    refreshStats();
  };

  const onRemoved = (chunkId: string) => {
    setChunks((prev) => prev.filter((c) => c.id !== chunkId));
    setInfo((prev) => (prev ? { ...prev, total_chunks: Math.max(0, prev.total_chunks - 1) } : prev));
    refreshStats();
  };

  const generateTitles = async () => {
    setConfirmTitles(false);
    setGenerating(Date.now());
    try {
      const result = await api.generateAllTitles(documentId);
      if (result.failed) toast.warning(`${result.success} titles generated, ${result.failed} failed`);
      else toast.success(`${result.success} titles generated`);
      await load(true);
    } catch (err) {
      toast.error(errorMessage(err, 'Title generation failed'));
    } finally {
      setGenerating(null);
    }
  };

  if (loading) return <PageLoader />;

  if (error || !info) {
    return (
      <div className="mx-auto w-full max-w-5xl px-4 py-section lg:px-8">
        <EmptyState
          icon={<FileWarning className="h-8 w-8" />}
          title="Document unavailable"
          action={<Button variant="secondary" onClick={() => load()}>Try again</Button>}
        >
          {error ?? 'This document could not be found.'}
        </EmptyState>
      </div>
    );
  }

  const titled = chunks.filter((c) => c.title).length;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-8 lg:py-section">
      <Link to="/documents" className="mb-6 inline-flex items-center gap-1.5 text-small font-semibold text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Documents
      </Link>

      <PageHeader
        title={<span className="break-words">{info.filename}</span>}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <Badge className="capitalize">{info.doc_type}</Badge>
            {info.department && <Badge>{info.department}</Badge>}
            <span>{info.file_size_mb} MB · uploaded {new Date(info.upload_date).toLocaleDateString()}</span>
          </span>
        }
        actions={
          <>
            <Button variant="secondary" leading={<Eye className="h-4 w-4" />} onClick={() => setPreviewing(true)}>Original</Button>
            {isAdmin && <Button variant="secondary" leading={<Pencil className="h-4 w-4" />} onClick={() => setEditingDetails(true)}>Details</Button>}
            {isAdmin && (
              <Button
                variant="secondary"
                leading={<Sparkles className="h-4 w-4" />}
                onClick={() => setConfirmTitles(true)}
                disabled={generating !== null || chunks.length === 0}
              >
                Title chunks
              </Button>
            )}
          </>
        }
      />

      {generating !== null && (
        <div className="mt-6 rounded-md border border-hairline bg-canvas px-4 py-3">
          <PixelLoader label={`Writing titles for ${chunks.length} chunks`} startedAt={generating} />
        </div>
      )}

      <dl className="mt-8 grid grid-cols-2 gap-6 rounded-md border border-hairline bg-canvas p-6 sm:grid-cols-4">
        <Stat label="Pages" value={info.total_pages} />
        <Stat label="Chunks" value={chunks.length} />
        <Stat label="Edited" value={stats ? `${stats.edited_chunks} (${Math.round(stats.edit_percentage)}%)` : '—'} />
        <Stat label="Titled" value={chunks.length ? `${Math.round((titled / chunks.length) * 100)}%` : '—'} />
      </dl>

      {!isAdmin && (
        <p className="mt-4 text-small text-ink-muted">You can read every chunk. Administrators can correct text that was extracted badly.</p>
      )}

      <div className="mt-section">
        <ChunkList chunks={chunks} onOpen={setOpen} />
      </div>

      {previewing && <DocumentViewer info={info} onClose={() => setPreviewing(false)} />}
      {editingDetails && <DocumentMetadataEditor info={info} onSaved={setInfo} onClose={() => setEditingDetails(false)} />}
      {open && (
        <ChunkEditor
          key={open.id}
          chunk={open}
          canEdit={isAdmin}
          onUpdated={onUpdated}
          onRemoved={onRemoved}
          onHistory={(id) => { setOpen(null); setHistoryFor(id); }}
          onClose={() => setOpen(null)}
        />
      )}
      {historyFor && <EditHistoryModal chunkId={historyFor} onClose={() => setHistoryFor(null)} />}

      <Modal
        open={confirmTitles}
        onClose={() => setConfirmTitles(false)}
        size="sm"
        title="Title every chunk?"
        description={`The AI model writes a short title for each of the ${chunks.length} chunks, replacing existing titles. Large documents take a few minutes and use model credits.`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmTitles(false)}>Cancel</Button>
            <Button onClick={generateTitles}>Generate titles</Button>
          </>
        }
      />
    </div>
  );
}
