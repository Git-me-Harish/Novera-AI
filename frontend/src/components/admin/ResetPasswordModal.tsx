import { useState, type FormEvent } from 'react';
import api, { errorMessage, type AdminUser } from '../../services/api';
import { PasswordInput } from '../auth/PasswordInput';
import { PasswordRules } from '../auth/PasswordRules';
import { passwordProblem } from '../../utils/password';
import { Button, Field, Modal, Notice } from '../../ui';
import { toast } from '../../utils/toast';

/** Set a new password for a member; every session they have is signed out. */
export default function ResetPasswordModal({ member, onClose }: { member: AdminUser; onClose: () => void }) {
  const [password, setPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const problem = passwordProblem(password);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (problem) return;
    setSaving(true);
    setError(null);
    try {
      await api.resetUserPassword(member.id, password);
      toast.success(`Password set for ${member.email}`);
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Could not reset the password'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!saving}
      title="Set a new password"
      description={`${member.email} is signed out everywhere. Share the new password securely.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" form="reset-password" loading={saving}>Set password</Button>
        </>
      }
    >
      <form id="reset-password" onSubmit={submit} className="space-y-4" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="New password" error={submitted ? problem ?? undefined : undefined}>
          <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" data-autofocus />
        </Field>
        <PasswordRules password={password} />
      </form>
    </Modal>
  );
}
