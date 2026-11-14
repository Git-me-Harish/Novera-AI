import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Copy, Loader2, Mail, RefreshCw, X } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, {
  errorMessage,
  type CreatedInvitation,
  type InvitableRole,
  type Invitation,
  type OrganizationUsage,
} from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { toast } from '../../utils/toast';

/** Invite people to the organization and manage pending invitations. */
export default function InvitationsPanel({ onChanged }: { onChanged?: () => void }) {
  const { user } = useAuth();
  const canGrantOrgAdmin = user?.role === 'super_admin';
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<InvitableRole>('user');
  const [sending, setSending] = useState(false);
  const [pending, setPending] = useState<Invitation[]>([]);
  const [usage, setUsage] = useState<OrganizationUsage | null>(null);
  const [lastLink, setLastLink] = useState<CreatedInvitation | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [invitations, orgUsage] = await Promise.all([api.listInvitations('pending'), api.getOrganizationUsage()]);
      setPending(invitations);
      setUsage(orgUsage);
    } catch (error) {
      toast.error(errorMessage(error, 'Could not load invitations'));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const showResult = (created: CreatedInvitation) => {
    if (created.email_sent) {
      toast.success(`Invitation sent to ${created.email}`);
      setLastLink(null);
    } else {
      // Email is not configured: the admin shares the one-time link instead.
      setLastLink(created);
    }
  };

  const invite = async (event: FormEvent) => {
    event.preventDefault();
    setSending(true);
    try {
      showResult(await api.createInvitation(email.trim(), role));
      setEmail('');
      refresh();
      onChanged?.();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not send the invitation'));
    } finally {
      setSending(false);
    }
  };

  const revoke = async (invitation: Invitation) => {
    setBusyId(invitation.id);
    try {
      await api.revokeInvitation(invitation.id);
      toast.success(`Invitation for ${invitation.email} revoked`);
      refresh();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not revoke the invitation'));
    } finally {
      setBusyId(null);
    }
  };

  const resend = async (invitation: Invitation) => {
    setBusyId(invitation.id);
    try {
      showResult(await api.resendInvitation(invitation.id));
      refresh();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not resend the invitation'));
    } finally {
      setBusyId(null);
    }
  };

  const copyLink = async () => {
    if (!lastLink) return;
    try {
      await navigator.clipboard.writeText(lastLink.invite_url);
      toast.success('Invitation link copied');
    } catch {
      toast.error('Copy failed; select the link and copy it manually');
    }
  };

  const seats = usage?.quotas.users;
  const seatsFull = seats?.limit != null && (seats.used ?? 0) + (usage?.quotas.pending_invitations ?? 0) >= seats.limit;

  return (
    <section className="bg-white border border-gray-200 rounded-lg p-5" aria-labelledby="invitations-heading">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 id="invitations-heading" className="text-lg font-bold text-gray-900">Invite people</h2>
          <p className="text-sm text-gray-600">
            Invitees choose their own password; the link works once and expires.
          </p>
        </div>
        {seats && (
          <p className="text-sm text-gray-600 whitespace-nowrap">
            {seats.limit == null
              ? `${seats.used} members`
              : `${seats.used} of ${seats.limit} seats used · ${usage?.quotas.pending_invitations ?? 0} pending`}
          </p>
        )}
      </div>

      <form onSubmit={invite} className="flex flex-col sm:flex-row gap-2">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@company.com"
          aria-label="Email to invite"
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as InvitableRole)}
          aria-label="Role"
          className="px-3 py-2 border border-gray-300 rounded-md bg-white"
        >
          <option value="user">Member</option>
          <option value="admin">Administrator</option>
          {canGrantOrgAdmin && <option value="org_admin">Organization administrator</option>}
        </select>
        <button
          type="submit"
          disabled={sending || seatsFull}
          title={seatsFull ? 'All seats are in use' : undefined}
          className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-md font-medium hover:bg-gray-800 disabled:opacity-50"
        >
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
          Invite
        </button>
      </form>
      {seatsFull && <p className="text-sm text-amber-700 mt-2">All seats are in use. Remove a member or ask for a higher limit.</p>}

      {lastLink && (
        <div className="mt-4 p-3 rounded-md border border-gray-200 bg-gray-50">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm text-gray-800">
              Email is not configured, so share this one-time link with <strong>{lastLink.email}</strong>.
              It is shown only now.
            </p>
            <button onClick={() => setLastLink(null)} aria-label="Dismiss" className="text-gray-400 hover:text-gray-700">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex gap-2 mt-2">
            <input readOnly value={lastLink.invite_url} aria-label="Invitation link"
              className="flex-1 px-2 py-1.5 text-xs font-mono border border-gray-300 rounded-md bg-white"
              onFocus={(e) => e.target.select()} />
            <button onClick={copyLink} className="inline-flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-white">
              <Copy className="w-4 h-4" /> Copy
            </button>
          </div>
        </div>
      )}

      {pending.length > 0 && (
        <ul className="mt-5 divide-y divide-gray-100 border-t border-gray-100">
          {pending.map((inv) => (
            <li key={inv.id} className="flex items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{inv.email}</p>
                <p className="text-xs text-gray-500">
                  {inv.role === 'user' ? 'Member' : inv.role === 'admin' ? 'Administrator' : 'Organization administrator'}
                  {' · '}expires {formatDistanceToNow(new Date(inv.expires_at), { addSuffix: true })}
                </p>
              </div>
              <div className="flex gap-1">
                <button onClick={() => resend(inv)} disabled={busyId === inv.id} title="Send a new link"
                  aria-label={`Resend invitation to ${inv.email}`}
                  className="p-2 rounded-md text-gray-500 hover:text-gray-900 hover:bg-gray-100 disabled:opacity-50">
                  <RefreshCw className="w-4 h-4" />
                </button>
                <button onClick={() => revoke(inv)} disabled={busyId === inv.id} title="Revoke"
                  aria-label={`Revoke invitation to ${inv.email}`}
                  className="p-2 rounded-md text-gray-500 hover:text-red-700 hover:bg-red-50 disabled:opacity-50">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
