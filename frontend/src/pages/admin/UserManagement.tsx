import { useCallback, useEffect, useRef, useState } from 'react';
import { KeyRound, MoreHorizontal, Pencil, Search, Trash2, UserCheck, UserPlus, UserX, Users, X } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, { errorMessage, type AdminUser } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import InvitationsPanel from '../../components/admin/InvitationsPanel';
import CreateUserModal from '../../components/admin/CreateUserModal';
import EditUserModal from '../../components/admin/EditUserModal';
import ResetPasswordModal from '../../components/admin/ResetPasswordModal';
import { ROLE_LABEL, canManage, canResetPassword } from '../../components/admin/roles';
import { Badge, Button, EmptyState, IconButton, Input, Menu, Modal, Notice, PageHeader, Select, Skeleton, Tabs, type MenuItem } from '../../ui';
import { toast } from '../../utils/toast';

const PAGE = 50;
type View = 'members' | 'invitations';
type Confirm = { kind: 'deactivate' | 'delete'; member: AdminUser } | null;

function Avatar({ member }: { member: AdminUser }) {
  const name = member.full_name || member.username;
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('');
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-canvas-tint text-caption font-heavy text-ink" aria-hidden>
      {initials || '?'}
    </span>
  );
}

export default function UserManagement() {
  const { user } = useAuth();
  const [view, setView] = useState<View>('members');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState<'' | 'active' | 'inactive'>('');
  const [members, setMembers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [resetting, setResetting] = useState<AdminUser | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [working, setWorking] = useState(false);
  const [pendingInvites, setPendingInvites] = useState<number | undefined>();
  const seq = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const params = useCallback((skip: number) => ({
    skip,
    limit: PAGE,
    search: search || undefined,
    role: role || undefined,
    is_active: status === '' ? undefined : status === 'active',
  }), [search, role, status]);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const page = await api.getUsers(params(0));
      if (mine !== seq.current) return;
      setMembers(page.users);
      setTotal(page.total);
    } catch (err) {
      if (mine === seq.current) setError(errorMessage(err, 'Could not load members'));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [params]);

  useEffect(() => { load(); }, [load]);

  const refreshInviteCount = useCallback(() => {
    api.getOrganizationUsage().then((u) => setPendingInvites(u.quotas.pending_invitations)).catch(() => undefined);
  }, []);
  useEffect(() => { refreshInviteCount(); }, [refreshInviteCount]);

  const more = async () => {
    setLoadingMore(true);
    try {
      const page = await api.getUsers(params(members.length));
      setMembers((prev) => [...prev, ...page.users.filter((u) => !prev.some((p) => p.id === u.id))]);
      setTotal(page.total);
    } catch (err) {
      toast.error(errorMessage(err, 'Could not load more members'));
    } finally {
      setLoadingMore(false);
    }
  };

  const setActive = async (member: AdminUser, active: boolean) => {
    setWorking(true);
    try {
      await api.updateUser(member.id, { is_active: active });
      toast.success(active ? `${member.email} reactivated` : `${member.email} deactivated and signed out`);
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Could not change the member’s status'));
    } finally {
      setWorking(false);
    }
  };

  const remove = async (member: AdminUser) => {
    setWorking(true);
    try {
      await api.deleteUser(member.id);
      toast.success(`${member.email} deleted`);
      setConfirm(null);
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Could not delete the member'));
    } finally {
      setWorking(false);
    }
  };

  const menuFor = (member: AdminUser): MenuItem[] => {
    const items: MenuItem[] = [{ label: 'Edit', icon: <Pencil className="h-4 w-4" />, onSelect: () => setEditing(member) }];
    if (canResetPassword(user, member)) items.push({ label: 'Set a new password', icon: <KeyRound className="h-4 w-4" />, onSelect: () => setResetting(member) });
    if (canManage(user, member)) {
      items.push(member.is_active
        ? { label: 'Deactivate', icon: <UserX className="h-4 w-4" />, onSelect: () => setConfirm({ kind: 'deactivate', member }) }
        : { label: 'Reactivate', icon: <UserCheck className="h-4 w-4" />, onSelect: () => setActive(member, true) });
      items.push({ label: 'Delete', icon: <Trash2 className="h-4 w-4" />, danger: true, onSelect: () => setConfirm({ kind: 'delete', member }) });
    }
    return items;
  };

  const filtered = Boolean(search || role || status);

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        eyebrow="Administration"
        title="Members"
        description="Who can use your organization’s knowledge, and what they can change."
        actions={
          <>
            <Button variant="secondary" onClick={() => setCreating(true)}>Add directly</Button>
            <Button leading={<UserPlus className="h-4 w-4" />} onClick={() => setView('invitations')}>Invite</Button>
          </>
        }
      />

      <div className="mt-8">
        <Tabs
          label="Members and invitations"
          value={view}
          onChange={setView}
          items={[
            { id: 'members', label: 'Members', count: total || undefined },
            { id: 'invitations', label: 'Invitations', count: pendingInvites },
          ]}
        />
      </div>

      {view === 'invitations' ? (
        <div className="mt-6"><InvitationsPanel onChanged={() => { refreshInviteCount(); load(); }} /></div>
      ) : (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-[1fr_12rem_10rem]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" aria-hidden />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name, email or username" aria-label="Search members" className="pl-11 pr-11" />
              {query && (
                <IconButton label="Clear search" size="sm" onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
                  <X className="h-4 w-4" />
                </IconButton>
              )}
            </div>
            <Select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
              <option value="">All roles</option>
              {['user', 'admin', 'org_admin'].map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </Select>
            <Select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} aria-label="Status">
              <option value="">Any status</option>
              <option value="active">Active</option>
              <option value="inactive">Deactivated</option>
            </Select>
          </div>

          <div className="mt-4">
            {loading ? (
              <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}</div>
            ) : error ? (
              <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>Try again</Button>}>{error}</Notice>
            ) : members.length === 0 ? (
              <EmptyState icon={<Users className="h-8 w-8" />} title={filtered ? 'No matching members' : 'No members yet'}
                action={!filtered ? <Button onClick={() => setView('invitations')}>Invite someone</Button> : undefined}>
                {filtered ? 'Try another search or filter.' : 'Invite people to start asking questions.'}
              </EmptyState>
            ) : (
              <>
                <ul className="divide-y divide-hairline rounded-md border border-hairline bg-canvas">
                  {members.map((m) => (
                    <li key={m.id} className="flex items-center gap-3 px-4 py-3">
                      <Avatar member={m} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-semibold text-ink">
                          {m.full_name || m.username}
                          {m.id === user?.id && <span className="font-normal text-ink-muted"> (you)</span>}
                        </p>
                        <p className="truncate text-caption text-ink-muted">
                          {m.email} · {m.last_login ? `last seen ${formatDistanceToNow(new Date(m.last_login), { addSuffix: true })}` : 'never signed in'}
                        </p>
                      </div>
                      <div className="hidden flex-wrap justify-end gap-1.5 sm:flex">
                        {!m.is_active && <Badge tone="error">Deactivated</Badge>}
                        {!m.is_verified && <Badge tone="warning">Unverified</Badge>}
                        <Badge tone={m.role === 'user' ? 'neutral' : 'info'}>{ROLE_LABEL[m.role] ?? m.role}</Badge>
                      </div>
                      <Menu
                        label={`Actions for ${m.email}`}
                        items={menuFor(m)}
                        trigger={(props) => (
                          <IconButton {...props} label={`Actions for ${m.email}`}>
                            <MoreHorizontal className="h-5 w-5" />
                          </IconButton>
                        )}
                      />
                    </li>
                  ))}
                </ul>
                <div className="mt-4 flex items-center justify-between">
                  <p className="text-caption text-ink-muted">{members.length} of {total}</p>
                  {members.length < total && <Button variant="secondary" loading={loadingMore} onClick={more}>Load more</Button>}
                </div>
              </>
            )}
          </div>
        </>
      )}

      {creating && <CreateUserModal onClose={() => setCreating(false)} onCreated={() => { load(); refreshInviteCount(); }} />}
      {editing && <EditUserModal member={editing} onClose={() => setEditing(null)} onSaved={load} />}
      {resetting && <ResetPasswordModal member={resetting} onClose={() => setResetting(null)} />}

      <Modal
        open={confirm !== null}
        onClose={() => !working && setConfirm(null)}
        dismissible={!working}
        size="sm"
        title={confirm?.kind === 'delete' ? 'Delete member?' : 'Deactivate member?'}
        description={
          confirm?.kind === 'delete'
            ? `${confirm.member.email} loses access and their conversations are removed. Documents they uploaded stay. This cannot be undone.`
            : confirm ? `${confirm.member.email} is signed out everywhere and cannot sign in until reactivated. Nothing is deleted.` : undefined
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)} disabled={working}>Cancel</Button>
            {confirm?.kind === 'delete' ? (
              <Button variant="danger" loading={working} onClick={() => remove(confirm.member)}>Delete</Button>
            ) : (
              <Button variant="danger" loading={working} onClick={() => confirm && setActive(confirm.member, false)}>Deactivate</Button>
            )}
          </>
        }
      />
    </div>
  );
}
