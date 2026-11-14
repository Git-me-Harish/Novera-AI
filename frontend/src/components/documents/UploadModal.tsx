import { useCallback, useId, useRef, useState, type DragEvent } from 'react';
import { AlertCircle, CheckCircle2, File as FileIcon, Upload, X } from 'lucide-react';
import api, { errorMessage } from '../../services/api';
import { Button, Field, IconButton, Input, Modal, Notice, cn } from '../../ui';

/** Mirrors the backend defaults (ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, 20 per batch). */
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls'];
const MAX_SIZE_MB = 50;
const MAX_FILES = 20;

interface FileEntry {
  file: File;
  id: string;
  error?: string;
}

interface UploadResult {
  filename: string;
  status: string;
  message?: string;
  error?: string;
}

function validate(file: File): string | undefined {
  const dot = file.name.lastIndexOf('.');
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
  if (!ALLOWED_EXTENSIONS.includes(ext)) return `${ext || 'This file type'} is not supported`;
  if (file.size > MAX_SIZE_MB * 1024 * 1024) return `Larger than ${MAX_SIZE_MB} MB`;
  if (file.size === 0) return 'The file is empty';
  return undefined;
}

const size = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export default function UploadModal({
  onClose,
  onSuccess,
  knownTypes = [],
}: {
  onClose: () => void;
  onSuccess: () => void;
  /** Document types already in use, offered as suggestions. */
  knownTypes?: string[];
}) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [docType, setDocType] = useState('');
  const [department, setDepartment] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState<UploadResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const listId = useId();

  const add = useCallback((incoming: FileList | File[]) => {
    setResults(null);
    setError(null);
    setFiles((prev) => {
      const names = new Set(prev.map((e) => e.file.name));
      const fresh = Array.from(incoming)
        .filter((f) => !names.has(f.name))
        .map((f) => ({ file: f, id: `${f.name}-${f.size}-${f.lastModified}`, error: validate(f) }));
      return [...prev, ...fresh];
    });
  }, []);

  const valid = files.filter((e) => !e.error);
  const tooMany = valid.length > MAX_FILES;

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (!uploading && event.dataTransfer.files?.length) add(event.dataTransfer.files);
  };

  const upload = async () => {
    if (!valid.length || tooMany || !docType.trim()) return;
    setUploading(true);
    setProgress(0);
    setError(null);
    setResults(null);
    try {
      const raw = valid.map((e) => e.file);
      const type = docType.trim().toLowerCase();
      const dept = department.trim() || undefined;
      const response = raw.length === 1
        ? { results: [await api.uploadDocument(raw[0], type, dept, setProgress)] }
        : await api.uploadDocuments(raw, type, dept, setProgress);
      const list: UploadResult[] = response.results ?? [];
      setResults(list);
      setFiles([]);
      if (list.some((r) => r.status === 'processing')) onSuccess();
    } catch (err) {
      setError(errorMessage(err, 'Upload failed. Please try again.'));
    } finally {
      setUploading(false);
    }
  };

  const accepted = results?.filter((r) => r.status === 'processing').length ?? 0;

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!uploading}
      size="lg"
      title="Upload documents"
      description="Files are parsed, chunked and indexed for your organization. Large files take a few minutes."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={uploading}>{results ? 'Done' : 'Cancel'}</Button>
          {!results && (
            <Button
              onClick={upload}
              loading={uploading}
              disabled={!valid.length || tooMany || !docType.trim()}
              leading={<Upload className="h-4 w-4" />}
            >
              {valid.length > 1 ? `Upload ${valid.length} files` : 'Upload'}
            </Button>
          )}
        </>
      }
    >
      <div className="space-y-5">
        {results ? (
          <div className="space-y-3">
            <Notice tone={accepted === results.length ? 'success' : 'warning'}>
              {accepted} of {results.length} file{results.length === 1 ? '' : 's'} accepted. Indexing continues in the background.
            </Notice>
            <ul className="divide-y divide-hairline rounded-sm border border-hairline">
              {results.map((r, i) => (
                <li key={`${r.filename}-${i}`} className="flex items-start gap-3 px-4 py-3">
                  {r.status === 'processing'
                    ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-label="Accepted" />
                    : <AlertCircle className={cn('mt-0.5 h-4 w-4 shrink-0', r.status === 'duplicate' ? 'text-warning' : 'text-error')} aria-label={r.status} />}
                  <div className="min-w-0">
                    <p className="truncate text-small font-semibold text-ink">{r.filename}</p>
                    <p className="text-caption text-ink-muted">{r.message || r.error || r.status}</p>
                  </div>
                </li>
              ))}
            </ul>
            <Button variant="secondary" size="sm" onClick={() => setResults(null)}>Upload more</Button>
          </div>
        ) : (
          <>
            <div
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                'flex flex-col items-center rounded-md border border-dashed px-6 py-8 text-center transition-colors',
                dragging ? 'border-focus bg-focus/[0.06]' : 'border-field-border bg-canvas-soft'
              )}
            >
              <Upload className="mb-3 h-6 w-6 text-ink-muted" aria-hidden />
              <p className="text-body text-ink">Drop files here, or</p>
              <Button variant="secondary" size="sm" className="mt-3" onClick={() => picker.current?.click()} disabled={uploading}>
                Choose files
              </Button>
              <input
                ref={picker}
                type="file"
                multiple
                accept={ALLOWED_EXTENSIONS.join(',')}
                className="sr-only"
                tabIndex={-1}
                aria-hidden
                onChange={(event) => {
                  if (event.target.files?.length) add(event.target.files);
                  event.target.value = '';
                }}
              />
              <p className="mt-3 text-caption text-ink-muted">
                PDF, Word, Excel or text · up to {MAX_SIZE_MB} MB each · {MAX_FILES} files per upload
              </p>
            </div>

            {files.length > 0 && (
              <div>
                <ul className="max-h-56 divide-y divide-hairline overflow-y-auto rounded-sm border border-hairline">
                  {files.map((entry) => (
                    <li key={entry.id} className="flex items-center gap-3 px-4 py-2.5">
                      <FileIcon className={cn('h-4 w-4 shrink-0', entry.error ? 'text-error' : 'text-ink-muted')} aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-small font-semibold text-ink">{entry.file.name}</p>
                        <p className={cn('text-caption', entry.error ? 'text-error' : 'text-ink-muted')}>
                          {entry.error ?? size(entry.file.size)}
                        </p>
                      </div>
                      {!uploading && (
                        <IconButton label={`Remove ${entry.file.name}`} size="sm" onClick={() => setFiles((prev) => prev.filter((e) => e.id !== entry.id))}>
                          <X className="h-4 w-4" />
                        </IconButton>
                      )}
                    </li>
                  ))}
                </ul>
                <p className={cn('mt-2 text-caption', tooMany ? 'text-error' : 'text-ink-muted')}>
                  {tooMany
                    ? `Choose at most ${MAX_FILES} files per upload.`
                    : `${valid.length} ready${files.length > valid.length ? ` · ${files.length - valid.length} will be skipped` : ''}`}
                </p>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Document type" hint="Used to filter documents, for example “policy” or “handbook”.">
                <Input value={docType} onChange={(e) => setDocType(e.target.value)} list={listId} maxLength={50} disabled={uploading} required />
              </Field>
              <datalist id={listId}>
                {knownTypes.map((t) => <option key={t} value={t} />)}
              </datalist>
              <Field label="Department" optional>
                <Input value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={100} disabled={uploading} />
              </Field>
            </div>

            {uploading && (
              <div>
                <div
                  role="progressbar"
                  aria-label="Upload progress"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(progress * 100)}
                  className="h-1.5 overflow-hidden rounded-full bg-canvas-tint"
                >
                  <div className="h-full bg-primary transition-[width] duration-200" style={{ width: `${Math.round(progress * 100)}%` }} />
                </div>
                <p className="mt-2 text-caption text-ink-muted">
                  {progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : 'Upload complete, checking files…'}
                </p>
              </div>
            )}
            {error && <Notice tone="error">{error}</Notice>}
          </>
        )}
      </div>
    </Modal>
  );
}
