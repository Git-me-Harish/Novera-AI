import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api, { errorMessage, type RegistrationMode } from '../services/api';
import { AuthLayout } from '../components/auth/AuthLayout';
import { PasswordInput } from '../components/auth/PasswordInput';
import { Button, Field, Input, Notice } from '../ui';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const state = location.state as { from?: { pathname: string }; message?: string } | null;
  const from = state?.from?.pathname || '/chat';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<RegistrationMode | null>(null);

  useEffect(() => {
    api.getRegistrationMode().then(setMode).catch(() => setMode(null));
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'Sign-in failed. Check your email and password.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Use the email your organization invited."
      footer={
        mode === 'self_serve' ? (
          <>New here? <Link to="/register" className="font-semibold">Create a workspace</Link></>
        ) : mode === 'invite_only' ? (
          <>Joining a team? Use the invitation link in your email.</>
        ) : null
      }
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        {/* Messages passed by other pages (e.g. after a password reset). */}
        {state?.message && <Notice tone="success">{state.message}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <PasswordInput autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-small">Forgot password?</Link>
        </div>
        <Button type="submit" block loading={submitting} disabled={!email || !password}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
