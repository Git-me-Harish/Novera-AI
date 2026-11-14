import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import api, { errorMessage } from '../services/api';
import { AuthLayout } from '../components/auth/AuthLayout';
import { Button, Field, Input, Notice } from '../ui';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.forgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setError(errorMessage(err, 'Could not send the reset link. Try again shortly.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title={sent ? 'Check your email' : 'Reset your password'}
      subtitle={sent ? undefined : "Enter your account email and we'll send a reset link."}
      footer={<Link to="/login" className="font-semibold">Back to sign in</Link>}
    >
      {sent ? (
        <div className="space-y-4">
          {/* Same message whether or not the account exists: no account enumeration. */}
          <p className="text-body text-ink-muted">
            If an account exists for <strong className="text-ink">{email}</strong>, a reset link is on its way.
            It expires in 15 minutes.
          </p>
          <Button variant="secondary" onClick={() => setSent(false)}>Use a different email</Button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-5" noValidate>
          {error && <Notice tone="error">{error}</Notice>}
          <Field label="Email">
            <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button type="submit" block loading={submitting} disabled={!email}>Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  );
}
