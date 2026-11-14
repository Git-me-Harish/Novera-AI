import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Copy, Mail, MoreHorizontal, RefreshCw, X } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, {
  errorMessage,
  type CreatedInvitation,
  type InvitableRole,
  type Invitation,
  type OrganizationUsage,
} from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { Badge, Button, Card, EmptyState, Field, IconButton, Input, Menu, Notice, Select, Skeleton } from '../../ui';
import { toast } from '../../utils/toast';
import { ROLE_HINT, ROLE_LABEL, grantableRoles } from './roles';

/** Invite people by email and manage the invitations still pending. */
export default function InvitationsPanel({ onChanged }: { onChanged?: () => void }) {
  const { user } = useAuth();
  const roles = grantableRoles(user) as InvitableRole[];
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<InvitableRole>('user');
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<Invitation[] | null>(null);
  const [usage, setUsage] = useState<OrganizationUsage | null>(null);
  const [link, setLink] = useState<CreatedInvitation | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [items, orgUsage] = await Promise.all([api.listInvitations('pending'), api.getOrganizationUsage()]);
      setPending(items);
      setUsage(orgUsage);
      setError(null);
    } catch (err) {
      setError(errorMessage(err, 'Could not load invitations'));
      setPending((prev) => prev ?? []);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const after = (created: CreatedInvitation) => {
    if (created.email_sent) {
      toast.success(`Invitation emailed to ${created.email}`);
      setLink(null);
    } else {
      setLink(created); // email is not configured: the admin shares the link
    }
    refresh();
    onChanged?.();
  };

  const invite = async (event: FormEvent) => {
    event.preventDefault();
    setSending(true);
    try {
      after(await api.createInvitation(email.trim(), role));
      setEmail('');
    } catch (err) {
      toast.error(errorMessage(err, 'Could not send the invitation'));
    } finally {
      setSending(false);
    }
  };

  const act = async (invitation: Invitation, kind: 'resend' | 'revoke') => {
    setBusyId(invitation.id);
    try {
      if (kind === 'resend') after(await api.resendInvitation(invitation.id));
      else {
        await api.revokeInvitation(invitation.id);
        toast.success(`Invitation for ${invitation.email} revoked`);
        refresh();
        onChanged?.();
      }
    } catch (err) {
      toast.error(errorMessage(err, kind === 'resend' ? 'Could not resend' : 'Could not revoke'));
    } finally {
      setBusyId(null);
    }
  };

  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.invite_url);
      toast.success('Link copied');
    } catch {
      toast.error('Copy failed. Select the link and copy it.');
    }
  };

  const seats = usage?.quotas.users;
  const pendingCount = usage?.quotas.pending_invitations ?? 0;
  const full = seats?.limit != null && (seats.used ?? 0) + pendingCount >= seats.limit;

  return (
    <div className="space-y-6">
      <Card>
        <form onSubmit={invite} className="grid gap-4 md:grid-cols-[1fr_14rem_auto] md:items-start">
          <Field label="Email" hint="They choose their own password. The link works once and expires.">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" placeholder="name@company.com" />
          </Field>
          <Field label="Role" hint={ROLE_HINT[role]}>
            <Select value={role} onChange={(e) => setRole(e.target.value as InvitableRole)}>
              {roles.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </Select>
          </Field>
          <Button type="submit" className="md:mt-7" loading={sending} disabled={full || !email.trim()} leading={<Mail className="h-4 w-4" />}>
            Invite
          </Button>
        </form>
        {seats && (
          <p className={full ? 'mt-4 text-small text-error' : 'mt-4 text-small text-ink-muted'}>
            {seats.limit == null
              ? `${seats.used} member${seats.used === 1 ? '' : 's'} · ${pendingCount} pending`
              : full
                ? `All ${seats.limit} seats are taken or promised to pending invitations. Revoke one or ask for a higher limit.`
                : `${seats.used} of ${seats.limit} seats used · ${pendingCount} pending`}
          </p>
        )}
      </Card>

      {link && (
        <Notice
          tone="info"
          title={`Share this link with ${link.email}`}
          action={
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input readOnly value={link.invite_url} aria-label="Invitation link" onFocus={(e) => e.target.select()} className="font-mono text-small" />
              <Button variant="secondary" leading={<Copy className="h-4 w-4" />} onClick={copy}>Copy</Button>
              <IconButton label="Dismiss" onClick={() => setLink(null)}><X className="h-4 w-4" /></IconButton>
            </div>
          }
        >
          Email is not set up on this server, so nothing was sent. The link is shown only now.
        </Notice>
      )}

      <section aria-labelledby="pending-heading">
        <h2 id="pending-heading" className="text-heading-sm font-heavy">Pending</h2>
        <div className="mt-4">
          {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
          {pending === null ? (
            <div className="space-y-2">{[0, 1].map((i) => <Skeleton key={i} className="h-14" />)}</div>
          ) : pending.length === 0 ? (
            <EmptyState icon={<Mail className="h-8 w-8" />} title="No pending invitations">Invitations waiting to be accepted appear here.</EmptyState>
          ) : (
            <ul className="divide-y divide-hairline rounded-md border border-hairline bg-canvas">
              {pending.map((inv) => (
                <li key={inv.id} className="flex items-center gap-4 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-ink">{inv.email}</p>
                    <p className="text-caption text-ink-muted">
                      Invited {formatDistanceToNow(new Date(inv.created_at), { addSuffix: true })} · expires{' '}
                      {formatDistanceToNow(new Date(inv.expires_at), { addSuffix: true })}
                    </p>
                  </div>
                  <Badge>{ROLE_LABEL[inv.role] ?? inv.role}</Badge>
                  <Menu
                    label={`Actions for ${inv.email}`}
                    items={[
                      { label: 'Send a new link', icon: <RefreshCw className="h-4 w-4" />, onSelect: () => act(inv, 'resend') },
                      { label: 'Revoke', icon: <X className="h-4 w-4" />, danger: true, onSelect: () => act(inv, 'revoke') },
                    ]}
                    trigger={(props) => (
                      <IconButton {...props} label={`Actions for ${inv.email}`} disabled={busyId === inv.id}>
                        <MoreHorizontal className="h-5 w-5" />
                      </IconButton>
                    )}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
