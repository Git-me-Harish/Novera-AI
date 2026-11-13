import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import api, { errorMessage, type InvitationPreview } from '../services/api';

const ROLE_LABELS: Record<string, string> = {
  user: 'Member',
  admin: 'Administrator',
  org_admin: 'Organization administrator',
};

function passwordProblem(password: string): string | null {
  if (password.length < 8) return 'Password must be at least 8 characters';
  if (!/[A-Z]/.test(password)) return 'Password must contain an uppercase letter';
  if (!/[a-z]/.test(password)) return 'Password must contain a lowercase letter';
  if (!/[0-9]/.test(password)) return 'Password must contain a number';
  if (!/[^A-Za-z0-9]/.test(password)) return 'Password must contain a special character';
  return null;
}

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

  const input = 'block w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500';

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12">
      <div className="max-w-md w-full bg-white border border-gray-200 rounded-lg p-8">
        {loadError ? (
          <div>
            <h1 className="text-xl font-bold text-gray-900 mb-2">Invitation unavailable</h1>
            <p className="text-gray-600">{loadError}</p>
            <p className="text-gray-600 mt-2">Ask your administrator to send a new invitation.</p>
            <Link to="/login" className="inline-block mt-6 font-medium text-primary-600 hover:text-primary-700">
              Go to sign in
            </Link>
          </div>
        ) : !preview ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" aria-label="Loading invitation" />
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Join {preview.organization}</h1>
              <p className="text-gray-600 mt-1">
                You were invited as <strong>{ROLE_LABELS[preview.role] ?? preview.role}</strong> with{' '}
                <strong>{preview.email}</strong>.
              </p>
            </div>

            {error && (
              <div className="flex gap-2 p-3 rounded-md bg-red-50 text-red-800 text-sm" role="alert">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">Username</span>
              <input className={input} required minLength={3} maxLength={50} autoComplete="username"
                value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">Full name (optional)</span>
              <input className={input} maxLength={255} autoComplete="name"
                value={form.fullName} onChange={(e) => setForm({ ...form, fullName: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">Password</span>
              <input className={input} type="password" required autoComplete="new-password"
                value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </label>
            <label className="block">
              <span className="block text-sm font-medium text-gray-700 mb-1">Confirm password</span>
              <input className={input} type="password" required autoComplete="new-password"
                value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
            </label>

            <button type="submit" disabled={submitting}
              className="w-full inline-flex justify-center items-center gap-2 px-4 py-2.5 bg-gray-900 text-white rounded-md font-medium hover:bg-gray-800 disabled:opacity-60">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              Create account and join
            </button>
            <p className="text-xs text-gray-500 text-center">
              This invitation expires {new Date(preview.expires_at).toLocaleDateString()}.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
