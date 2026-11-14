import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api, { errorMessage } from '../services/api';
import { AuthLayout } from '../components/auth/AuthLayout';
import { PasswordInput } from '../components/auth/PasswordInput';
import { PasswordRules } from '../components/auth/PasswordRules';
import { passwordProblem } from '../utils/password';
import { Button, Field, Notice, PageLoader } from '../ui';

type TokenState = 'checking' | 'valid' | 'invalid';

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const navigate = useNavigate();
  const [tokenState, setTokenState] = useState<TokenState>('checking');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setTokenState('invalid');
      return;
    }
    api.verifyResetToken(token)
      .then(() => setTokenState('valid'))
      .catch(() => setTokenState('invalid'));
  }, [token]);

  if (tokenState === 'checking') return <PageLoader />;

  if (tokenState === 'invalid' || !token) {
    return (
      <AuthLayout title="This reset link has expired" footer={<Link to="/login" className="font-semibold">Back to sign in</Link>}>
        <p className="text-body text-ink-muted">Reset links work once and expire after 15 minutes.</p>
        <Link to="/forgot-password" className="mt-6 inline-flex">
          <Button>Request a new link</Button>
        </Link>
      </AuthLayout>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const problem = passwordProblem(password);
    if (problem) return setError(problem);
    if (password !== confirm) return setError('Passwords do not match');
    setSubmitting(true);
    try {
      await api.resetPassword(token, password);
      navigate('/login', { replace: true, state: { message: 'Password updated. Sign in with your new password.' } });
    } catch (err) {
      setError(errorMessage(err, 'Could not reset the password'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout title="Choose a new password" footer={<Link to="/login" className="font-semibold">Back to sign in</Link>}>
      <form onSubmit={submit} className="space-y-5" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="New password">
          <PasswordInput autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <PasswordRules password={password} />
        <Field label="Confirm new password">
          <PasswordInput autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        <Button type="submit" block loading={submitting}>Update password</Button>
      </form>
    </AuthLayout>
  );
}
