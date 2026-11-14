import { useState, type FormEvent } from 'react';
import { KeyRound, Monitor, Moon, Sun } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { useAuth } from '../contexts/AuthContext';
import { useTheme, type ThemePreference } from '../contexts/ThemeContext';
import api, { errorMessage } from '../services/api';
import ChangePasswordModal from '../components/profile/ChangePasswordModal';
import { Badge, Button, Card, Field, Input, Notice, PageHeader, SectionHeading, cn } from '../ui';
import { toast } from '../utils/toast';

const ROLE_LABEL: Record<string, string> = {
  super_admin: 'Platform administrator',
  org_admin: 'Organization administrator',
  admin: 'Administrator',
  user: 'Member',
};

const THEMES: { id: ThemePreference; label: string; icon: JSX.Element }[] = [
  { id: 'system', label: 'Match system', icon: <Monitor className="h-4 w-4" /> },
  { id: 'light', label: 'Light', icon: <Sun className="h-4 w-4" /> },
  { id: 'dark', label: 'Dark', icon: <Moon className="h-4 w-4" /> },
];

function Initials({ name }: { name: string }) {
  const letters = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('');
  return (
    <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-canvas-tint text-heading-sm font-heavy text-ink" aria-hidden>
      {letters || '?'}
    </span>
  );
}

export default function ProfilePage() {
  const { user, updateProfile } = useAuth();
  const { preference, setPreference } = useTheme();
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [saving, setSaving] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);

  if (!user) return null;
  const display = user.full_name || user.username;
  const nameChanged = fullName.trim() !== (user.full_name ?? '');

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!nameChanged) return;
    setSaving(true);
    try {
      await updateProfile({ full_name: fullName.trim() });
      toast.success('Profile saved');
    } catch (err) {
      toast.error(errorMessage(err, 'Could not save your profile'));
    } finally {
      setSaving(false);
    }
  };

  const resend = async () => {
    setResending(true);
    try {
      await api.resendVerificationEmail();
      setResent(true);
    } catch (err) {
      toast.error(errorMessage(err, 'Could not send the email'));
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader title="Profile" description="Your account, sign-in and appearance." />

      <div className="mt-8 space-y-6">
        <Card>
          <div className="flex items-center gap-4">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" className="h-16 w-16 shrink-0 rounded-full object-cover" />
            ) : (
              <Initials name={display} />
            )}
            <div className="min-w-0">
              <p className="truncate text-heading-sm font-heavy text-ink">{display}</p>
              <p className="truncate text-small text-ink-muted">{user.email}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge>{ROLE_LABEL[user.role] ?? user.role}</Badge>
                {user.is_verified ? <Badge tone="success">Email verified</Badge> : <Badge tone="warning">Email not verified</Badge>}
              </div>
            </div>
          </div>

          {!user.is_verified && (
            <div className="mt-6">
              <Notice
                tone="warning"
                action={!resent && <Button size="sm" variant="secondary" loading={resending} onClick={resend}>Send verification email</Button>}
              >
                {resent
                  ? `A verification link is on its way to ${user.email}.`
                  : 'Verify your email address to change your password and receive account notices.'}
              </Notice>
            </div>
          )}

          <form onSubmit={save} className="mt-6 border-t border-hairline pt-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Full name">
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={255} autoComplete="name" />
              </Field>
              <Field label="Username" hint="Usernames cannot be changed.">
                <Input value={user.username} disabled readOnly />
              </Field>
            </div>
            <div className="mt-4 flex justify-end">
              <Button type="submit" loading={saving} disabled={!nameChanged}>Save</Button>
            </div>
          </form>
        </Card>

        <Card>
          <SectionHeading description="Use a password you do not use anywhere else.">Sign-in</SectionHeading>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-small text-ink-muted">
              Member since {user.created_at ? formatDistanceToNow(new Date(user.created_at), { addSuffix: true }) : '—'}
            </p>
            <Button
              variant="secondary"
              leading={<KeyRound className="h-4 w-4" />}
              onClick={() => setChangingPassword(true)}
              disabled={!user.is_verified}
              title={user.is_verified ? undefined : 'Verify your email first'}
            >
              Change password
            </Button>
          </div>
        </Card>

        <Card>
          <SectionHeading description="Saved on this device.">Appearance</SectionHeading>
          <div role="radiogroup" aria-label="Theme" className="grid gap-2 sm:grid-cols-3">
            {THEMES.map((t) => (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={preference === t.id}
                onClick={() => setPreference(t.id)}
                className={cn(
                  'flex items-center gap-2 rounded-sm border px-4 py-3 text-small font-semibold transition-colors',
                  preference === t.id ? 'border-ink bg-canvas-soft text-ink' : 'border-hairline text-ink-muted hover:border-field-border hover:text-ink'
                )}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>
        </Card>
      </div>

      {changingPassword && <ChangePasswordModal onClose={() => setChangingPassword(false)} />}
    </div>
  );
}
