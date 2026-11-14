import { useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { PasswordInput } from '../auth/PasswordInput';
import { PasswordRules } from '../auth/PasswordRules';
import { passwordProblem } from '../../utils/password';
import { Button, Field, Input, Modal, Notice, Select } from '../../ui';
import { toast } from '../../utils/toast';
import { ROLE_HINT, ROLE_LABEL, grantableRoles, type Role } from './roles';

const USERNAME = /^\S{3,50}$/; // server: 3–50 characters

/**
 * Create an account directly, for organizations without email. Inviting is
 * better: the person sets their own password and proves the address is theirs.
 */
export default function CreateUserModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { user } = useAuth();
  const roles = grantableRoles(user);
  const [form, setForm] = useState({ email: '', username: '', full_name: '', password: '', role: 'user' as Role });
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  const problems = {
    email: /^\S+@\S+\.\S+$/.test(form.email.trim()) ? null : 'Enter a valid email address.',
    username: USERNAME.test(form.username) ? null : '3–50 characters, no spaces.',
    password: passwordProblem(form.password),
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (Object.values(problems).some(Boolean)) return;
    setSaving(true);
    setError(null);
    try {
      await api.createUser({
        email: form.email.trim(),
        username: form.username.trim(),
        full_name: form.full_name.trim() || undefined,
        password: form.password,
        role: form.role,
        is_active: true,
      });
      toast.success(`${form.email.trim()} can now sign in`);
      onCreated();
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Could not create the account'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!saving}
      size="lg"
      title="Add a member directly"
      description="Use this when email is not available. Share the password securely; the member should change it after signing in."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" form="create-user" loading={saving}>Create account</Button>
        </>
      }
    >
      <form id="create-user" onSubmit={submit} className="space-y-4" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Email" error={submitted ? problems.email ?? undefined : undefined}>
            <Input type="email" value={form.email} onChange={(e) => set('email')(e.target.value)} autoComplete="off" data-autofocus />
          </Field>
          <Field label="Username" error={submitted ? problems.username ?? undefined : undefined}>
            <Input value={form.username} onChange={(e) => set('username')(e.target.value)} autoComplete="off" maxLength={50} />
          </Field>
          <Field label="Full name" optional>
            <Input value={form.full_name} onChange={(e) => set('full_name')(e.target.value)} autoComplete="off" maxLength={255} />
          </Field>
          <Field label="Role" hint={ROLE_HINT[form.role]}>
            <Select value={form.role} onChange={(e) => set('role')(e.target.value)}>
              {roles.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Temporary password" error={submitted ? problems.password ?? undefined : undefined}>
          <PasswordInput value={form.password} onChange={(e) => set('password')(e.target.value)} autoComplete="new-password" />
        </Field>
        <PasswordRules password={form.password} />
      </form>
    </Modal>
  );
}
