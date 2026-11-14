import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api, { errorMessage, type InvitationPreview } from '../services/api';
import { AuthLayout } from '../components/auth/AuthLayout';
import { PasswordInput } from '../components/auth/PasswordInput';
import { PasswordRules } from '../components/auth/PasswordRules';
import { passwordProblem } from '../utils/password';
import { Button, Field, Input, Notice, PageLoader } from '../ui';

const ROLE_LABELS: Record<string, string> = {
  user: 'Member',
  admin: 'Administrator',
  org_admin: 'Organization administrator',
};

export default function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const { acceptInvitation } = useAuth();

  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState({ username: '', fullName: '', password: '', confirm: '' });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLoadError('This invitation link is incomplete.');
      return;
    }
    api.previewInvitation(token)
      .then(setPreview)
      .catch((err) => setLoadError(errorMessage(err, 'This invitation is invalid or has expired.')));
  }, [token]);

  if (loadError) {
    return (
      <AuthLayout title="Invitation unavailable" footer={<Link to="/login" className="font-semibold">Go to sign in</Link>}>
        <p className="text-body text-ink-muted">{loadError}</p>
        <p className="mt-2 text-body text-ink-muted">Ask your administrator to send a new invitation.</p>
      </AuthLayout>
    );
  }
  if (!preview) return <PageLoader />;

  const set = (key: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm({ ...form, [key]: event.target.value });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const problem = passwordProblem(form.password);
    if (problem) return setError(problem);
    if (form.password !== form.confirm) return setError('Passwords do not match');
    setSubmitting(true);
    try {
      await acceptInvitation(token, form.username.trim(), form.password, form.fullName.trim() || undefined);
      navigate('/chat', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Could not accept the invitation'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title={`Join ${preview.organization}`}
      subtitle={<>You were invited as <strong className="text-ink">{ROLE_LABELS[preview.role] ?? preview.role}</strong> with <strong className="text-ink">{preview.email}</strong>.</>}
      footer={<>This invitation expires on {new Date(preview.expires_at).toLocaleDateString()}.</>}
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Username">
          <Input autoComplete="username" required minLength={3} maxLength={50} value={form.username} onChange={set('username')} />
        </Field>
        <Field label="Full name" optional>
          <Input autoComplete="name" maxLength={255} value={form.fullName} onChange={set('fullName')} />
        </Field>
        <Field label="Password">
          <PasswordInput autoComplete="new-password" required value={form.password} onChange={set('password')} />
        </Field>
        <PasswordRules password={form.password} />
        <Field label="Confirm password">
          <PasswordInput autoComplete="new-password" required value={form.confirm} onChange={set('confirm')} />
        </Field>
        <Button type="submit" block loading={submitting}>Create account and join</Button>
      </form>
    </AuthLayout>
  );
}
