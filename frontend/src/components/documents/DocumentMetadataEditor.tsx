import { useState, type FormEvent } from 'react';
import api, { errorMessage, type DocumentInfo } from '../../services/api';
import { Button, Field, Input, Modal, Notice } from '../../ui';
import { toast } from '../../utils/toast';

const splitName = (filename: string) => {
  const dot = filename.lastIndexOf('.');
  return dot > 0 ? [filename.slice(0, dot), filename.slice(dot)] : [filename, ''];
};

/**
 * Rename a document or change its type and department. The name is what
 * citations show; type and department drive filters. No re-indexing needed.
 */
export default function DocumentMetadataEditor({
  info,
  onSaved,
  onClose,
}: {
  info: DocumentInfo;
  onSaved: (info: DocumentInfo) => void;
  onClose: () => void;
}) {
  const [stem, extension] = splitName(info.filename);
  const [name, setName] = useState(stem);
  const [docType, setDocType] = useState(info.doc_type);
  const [department, setDepartment] = useState(info.department ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nameProblem = !name.trim() ? 'Enter a name.' : /[\\/]/.test(name) ? 'Names cannot contain / or \\.' : null;
  const typeProblem = !docType.trim() ? 'Enter a type.' : null;
  const changed =
    name.trim() + extension !== info.filename ||
    docType.trim().toLowerCase() !== info.doc_type ||
    (department.trim() || null) !== info.department;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (nameProblem || typeProblem || !changed) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateDocument(info.id, {
        filename: name.trim() + extension,
        doc_type: docType.trim(),
        department: department.trim() || null,
      });
      onSaved(updated);
      toast.success('Document details saved');
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Could not save the details'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!saving}
      title="Document details"
      description="Changes apply to the next question. Nothing is re-indexed."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" form="document-details" loading={saving} disabled={!changed || !!nameProblem || !!typeProblem}>Save</Button>
        </>
      }
    >
      <form id="document-details" onSubmit={submit} className="space-y-4" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Name" hint={extension ? `Citations show this name. The ${extension} extension is kept.` : 'Citations show this name.'} error={nameProblem ?? undefined}>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={255 - extension.length} data-autofocus />
        </Field>
        <Field label="Type" error={typeProblem ?? undefined}>
          <Input value={docType} onChange={(e) => setDocType(e.target.value)} maxLength={50} />
        </Field>
        <Field label="Department" optional>
          <Input value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={100} />
        </Field>
        <p className="text-caption text-ink-muted">Uploaded as “{info.original_filename}”. Downloads keep that name.</p>
      </form>
    </Modal>
  );
}
