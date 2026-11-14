import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api, { errorMessage } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { AuthLayout } from '../components/auth/AuthLayout';
import { Button, Notice, PageLoader } from '../ui';

type Status = 'verifying' | 'verified' | 'failed';

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [status, setStatus] = useState<Status>(token ? 'verifying' : 'failed');
  const [error, setError] = useState<string | null>(token ? null : 'This verification link is incomplete.');
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    // Tokens are single use; StrictMode's double effect must not burn it twice.
    if (!token || started.current) return;
    started.current = true;
    api.verifyEmail(token)
      .then(() => {
        setStatus('verified');
        window.setTimeout(
          () => navigate(isAuthenticated ? '/chat' : '/login', {
            replace: true,
            state: { message: 'Email verified. You can sign in.' },
          }),
          2500
        );
      })
      .catch((err) => {
        setStatus('failed');
        setError(errorMessage(err, 'This verification link is invalid or has expired.'));
      });
  }, [token, navigate, isAuthenticated]);

  const resend = async () => {
    setResending(true);
    try {
      await api.resendVerificationEmail();
      setResent(true);
    } catch (err) {
      setError(errorMessage(err, 'Could not send a new link'));
    } finally {
      setResending(false);
    }
  };

  if (status === 'verifying') return <PageLoader />;

  return (
    <AuthLayout
      title={status === 'verified' ? 'Email verified' : 'Verification failed'}
      footer={<Link to="/login" className="font-semibold">Go to sign in</Link>}
    >
      {status === 'verified' ? (
        <p className="text-body text-ink-muted">Thanks — taking you on in a moment.</p>
      ) : (
        <div className="space-y-4">
          {error && <Notice tone="error">{error}</Notice>}
          {resent && <Notice tone="success">A new verification email is on its way.</Notice>}
          {isAuthenticated && !resent && (
            <Button loading={resending} onClick={resend}>Send a new link</Button>
          )}
          {!isAuthenticated && <p className="text-small text-ink-muted">Sign in to request a new verification link.</p>}
        </div>
      )}
    </AuthLayout>
  );
}
