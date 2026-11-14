import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api, { errorMessage, type RegistrationMode } from '../services/api';
import { AuthLayout } from '../components/auth/AuthLayout';
import { PasswordInput } from '../components/auth/PasswordInput';
import { PasswordRules } from '../components/auth/PasswordRules';
import { passwordProblem } from '../utils/password';
import { Button, Field, Input, Notice, PageLoader } from '../ui';

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();
  // Sign-up never joins an existing organization: the server decides whether
  // it is open (a new workspace) or invitation-only.
  const [mode, setMode] = useState<RegistrationMode | null>(null);
  const [form, setForm] = useState({ email: '', username: '', fullName: '', organizationName: '', password: '', confirm: '' });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getRegistrationMode().then(setMode).catch(() => setMode('invite_only'));
  }, []);

  if (mode === null) return <PageLoader />;

  if (mode !== 'self_serve') {
    return (
      <AuthLayout
        title={mode === 'invite_only' ? 'Accounts are created by invitation' : 'Sign-up is closed'}
        footer={<Link to="/login" className="font-semibold">Back to sign in</Link>}
      >
        <p className="text-body text-ink-muted">
          {mode === 'invite_only'
            ? 'Ask an administrator of your organization to invite you. The invitation email has a link to set up your account.'
            : 'New accounts are created by your administrator.'}
        </p>
      </AuthLayout>
    );
  }

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
      await register(form.email.trim(), form.username.trim(), form.password, form.fullName.trim() || undefined,
        form.organizationName.trim() || undefined);
      navigate('/chat', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Could not create your workspace'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title="Create your workspace"
      subtitle="You'll be its administrator and can invite your team."
      footer={<>Already have an account? <Link to="/login" className="font-semibold">Sign in</Link></>}
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Organization name" optional hint="Shown to everyone you invite.">
          <Input autoComplete="organization" maxLength={200} value={form.organizationName} onChange={set('organizationName')} />
        </Field>
        <Field label="Work email">
          <Input type="email" autoComplete="email" required value={form.email} onChange={set('email')} />
        </Field>
        <div className="grid gap-5 md:grid-cols-2">
          <Field label="Username">
            <Input autoComplete="username" required minLength={3} maxLength={50} value={form.username} onChange={set('username')} />
          </Field>
          <Field label="Full name" optional>
            <Input autoComplete="name" maxLength={255} value={form.fullName} onChange={set('fullName')} />
          </Field>
        </div>
        <Field label="Password">
          <PasswordInput autoComplete="new-password" required value={form.password} onChange={set('password')} />
        </Field>
        <PasswordRules password={form.password} />
        <Field label="Confirm password">
          <PasswordInput autoComplete="new-password" required value={form.confirm} onChange={set('confirm')} />
        </Field>
        <Button type="submit" block loading={submitting}>Create workspace</Button>
      </form>
    </AuthLayout>
  );
}
