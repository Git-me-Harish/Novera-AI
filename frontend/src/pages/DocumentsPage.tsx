import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FileText, Search, Upload, X } from 'lucide-react';
import api, { errorMessage, type Document } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import UploadModal from '../components/documents/UploadModal';
import DocumentCard from '../components/documents/DocumentCard';
import { Button, EmptyState, IconButton, Input, Modal, Notice, PageHeader, Select, Skeleton, Tabs } from '../ui';
import { toast } from '../utils/toast';

type StatusFilter = 'all' | 'completed' | 'processing' | 'failed';
const POLL_MS = 4000;

export default function DocumentsPage() {
  const { isAdmin } = useAuth();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>('all');
  const [type, setType] = useState('all');
  const [query, setQuery] = useState('');
  const [uploading, setUploading] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null);
  const [deleting, setDeleting] = useState(false);
  const poll = useRef<number | null>(null);

  // One list for the whole organization; status/type/search filter locally so
  // the counts on the tabs always describe the same data set.
  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
      setLoadError(null);
    }
    try {
      const { documents: list } = await api.getDocuments({ limit: 500 });
      setDocuments(list);
    } catch (error) {
      if (!silent) setLoadError(errorMessage(error, 'Could not load documents'));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll only while something is still being indexed, and not in background tabs.
  const indexing = documents.some((d) => d.status === 'processing' || d.status === 'pending');
  useEffect(() => {
    if (!indexing) return;
    poll.current = window.setInterval(() => {
      if (document.visibilityState === 'visible') load(true);
    }, POLL_MS);
    return () => {
      if (poll.current) window.clearInterval(poll.current);
    };
  }, [indexing, load]);

  const types = useMemo(() => [...new Set(documents.map((d) => d.doc_type))].sort(), [documents]);
  const counts = useMemo(() => ({
    all: documents.length,
    completed: documents.filter((d) => d.status === 'completed').length,
    processing: documents.filter((d) => d.status === 'processing' || d.status === 'pending').length,
    failed: documents.filter((d) => d.status === 'failed').length,
  }), [documents]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return documents.filter((d) => {
      if (status === 'processing' && !(d.status === 'processing' || d.status === 'pending')) return false;
      if (status !== 'all' && status !== 'processing' && d.status !== status) return false;
      if (type !== 'all' && d.doc_type !== type) return false;
      if (!q) return true;
      return [d.filename, d.doc_type, d.department ?? ''].some((v) => v.toLowerCase().includes(q));
    });
  }, [documents, status, type, query]);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.deleteDocument(pendingDelete.id);
      setDocuments((prev) => prev.filter((d) => d.id !== pendingDelete.id));
      toast.success(`“${pendingDelete.filename}” deleted`);
      setPendingDelete(null);
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the document'));
    } finally {
      setDeleting(false);
    }
  };

  const filtered = query.trim() !== '' || status !== 'all' || type !== 'all';

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        title="Documents"
        description={
          isAdmin
            ? 'The knowledge your organization’s answers are grounded in.'
            : 'The knowledge your answers are grounded in. Ask an administrator to add or remove documents.'
        }
        actions={isAdmin && (
          <Button leading={<Upload className="h-4 w-4" />} onClick={() => setUploading(true)}>Upload</Button>
        )}
      />

      <div className="mt-8 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" aria-hidden />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, type or department"
              aria-label="Search documents"
              className="pl-11 pr-11"
            />
            {query && (
              <IconButton label="Clear search" size="sm" onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
                <X className="h-4 w-4" />
              </IconButton>
            )}
          </div>
          {types.length > 1 && (
            <Select value={type} onChange={(e) => setType(e.target.value)} aria-label="Document type" className="sm:w-48">
              <option value="all">All types</option>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </Select>
          )}
        </div>
        <Tabs
          label="Document status"
          value={status}
          onChange={setStatus}
          items={[
            { id: 'all', label: 'All', count: counts.all },
            { id: 'completed', label: 'Ready', count: counts.completed },
            { id: 'processing', label: 'Indexing', count: counts.processing },
            { id: 'failed', label: 'Failed', count: counts.failed },
          ]}
        />
      </div>

      <div className="mt-4">
        {loading ? (
          <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16" />)}</div>
        ) : loadError ? (
          <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={() => load()}>Try again</Button>}>{loadError}</Notice>
        ) : visible.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-8 w-8" />}
            title={filtered ? 'No matching documents' : 'No documents yet'}
            action={!filtered && isAdmin ? <Button leading={<Upload className="h-4 w-4" />} onClick={() => setUploading(true)}>Upload documents</Button> : undefined}
          >
            {filtered
              ? 'Try a different search or filter.'
              : isAdmin
                ? 'Upload PDFs, Word, Excel or text files. Answers will cite them.'
                : 'Once an administrator uploads documents you can ask questions about them.'}
          </EmptyState>
        ) : (
          <>
            {counts.failed > 0 && status !== 'failed' && (
              <div className="mb-4">
                <Notice tone="warning">
                  {counts.failed} document{counts.failed === 1 ? '' : 's'} could not be processed.{' '}
                  <button type="button" className="font-semibold text-link hover:underline" onClick={() => setStatus('failed')}>Review</button>
                </Notice>
              </div>
            )}
            <ul className="divide-y divide-hairline rounded-md border border-hairline bg-canvas" aria-live="polite">
              {visible.map((doc) => (
                <DocumentCard key={doc.id} document={doc} canManage={isAdmin} onDelete={setPendingDelete} />
              ))}
            </ul>
            {filtered && (
              <p className="mt-3 text-caption text-ink-muted">Showing {visible.length} of {documents.length}</p>
            )}
          </>
        )}
      </div>

      {uploading && isAdmin && (
        <UploadModal knownTypes={types} onClose={() => setUploading(false)} onSuccess={() => load(true)} />
      )}

      <Modal
        open={pendingDelete !== null}
        onClose={() => !deleting && setPendingDelete(null)}
        dismissible={!deleting}
        size="sm"
        title="Delete document?"
        description={pendingDelete ? `“${pendingDelete.filename}” and its chunks will be removed for everyone in your organization. Answers will no longer cite it.` : undefined}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)} disabled={deleting}>Cancel</Button>
            <Button variant="danger" loading={deleting} onClick={confirmDelete}>Delete</Button>
          </>
        }
      />
    </div>
  );
}
