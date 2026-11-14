import { useEffect, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import api, { errorMessage, type DocumentInfo } from '../../services/api';
import { Button, EmptyState, Modal, Notice, Spinner } from '../../ui';
import { toast } from '../../utils/toast';

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Original-file preview. Text files show inline; PDFs render in the browser's
 * own viewer from an authenticated download (the file URL itself needs a
 * bearer token, so it cannot be linked directly); anything else downloads.
 */
export default function DocumentViewer({ info, onClose }: { info: DocumentInfo; onClose: () => void }) {
  const [text, setText] = useState<{ content: string; is_truncated: boolean } | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(info.preview_type === 'text' || info.preview_type === 'pdf');
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    (async () => {
      try {
        if (info.preview_type === 'text') {
          const preview = await api.getTextPreview(info.id, 20_000);
          if (!cancelled) setText(preview);
        } else if (info.preview_type === 'pdf') {
          const blob = await api.downloadDocument(info.id);
          objectUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
          if (!cancelled) setPdfUrl(objectUrl);
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, 'The preview could not be loaded.'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [info.id, info.preview_type]);

  const download = async () => {
    setDownloading(true);
    try {
      saveBlob(await api.downloadDocument(info.id), info.original_filename || info.filename);
    } catch (err) {
      toast.error(errorMessage(err, 'Download failed'));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={info.filename}
      description={`${info.file_size_mb} MB · ${info.total_pages} page${info.total_pages === 1 ? '' : 's'}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Close</Button>
          <Button leading={<Download className="h-4 w-4" />} loading={downloading} onClick={download}>Download original</Button>
        </>
      }
    >
      {loading ? (
        <div className="flex h-64 items-center justify-center"><Spinner label="Loading preview" /></div>
      ) : error ? (
        <Notice tone="error">{error}</Notice>
      ) : pdfUrl ? (
        <iframe src={pdfUrl} title={`Preview of ${info.filename}`} className="h-[65vh] w-full rounded-sm border border-hairline bg-canvas-soft" />
      ) : text ? (
        <>
          <pre className="whitespace-pre-wrap break-words rounded-sm border border-hairline bg-canvas-soft p-4 font-mono text-small leading-relaxed text-ink">
            {text.content}
          </pre>
          {text.is_truncated && <p className="mt-3 text-caption text-ink-muted">Showing the beginning of the file. Download it to read the rest.</p>}
        </>
      ) : (
        <EmptyState icon={<FileText className="h-8 w-8" />} title="No preview for this file type">
          Download the original to open it in its own application. The extracted text is in the chunk list.
        </EmptyState>
      )}
    </Modal>
  );
}
