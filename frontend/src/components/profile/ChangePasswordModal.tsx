import { useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../services/api';
import { PasswordInput } from '../auth/PasswordInput';
import { PasswordRules } from '../auth/PasswordRules';
import { passwordProblem } from '../../utils/password';
import { Button, Field, Modal, Notice } from '../../ui';
import { toast } from '../../utils/toast';

export default function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ruleProblem = passwordProblem(next);
  const sameAsOld = next !== '' && next === current;
  const mismatch = confirm !== '' && confirm !== next;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (!current || ruleProblem || sameAsOld || confirm !== next) return;
    setSaving(true);
    setError(null);
    try {
      await api.changePassword(current, next);
      toast.success('Password changed');
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Could not change your password'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!saving}
      title="Change password"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" form="change-password" loading={saving}>Change password</Button>
        </>
      }
    >
      <form id="change-password" onSubmit={submit} className="space-y-4" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Current password" error={submitted && !current ? 'Enter your current password.' : undefined}>
          <PasswordInput value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" data-autofocus />
        </Field>
        <Field
          label="New password"
          error={submitted && ruleProblem ? ruleProblem : sameAsOld ? 'Choose a password you have not used here.' : undefined}
        >
          <PasswordInput value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
        </Field>
        <PasswordRules password={next} />
        <Field label="Confirm new password" error={mismatch || (submitted && confirm !== next) ? 'The passwords do not match.' : undefined}>
          <PasswordInput value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
        </Field>
      </form>
    </Modal>
  );
}
