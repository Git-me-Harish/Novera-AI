import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowRight, Bot, Palette, ScrollText, Users } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, { errorMessage, type AuditEvent, type OrganizationUsage } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { QuotaMeter, formatBytes } from '../../components/admin/QuotaMeter';
import { Card, Notice, PageHeader, SectionHeading, Skeleton } from '../../ui';

interface Overview {
  usage: OrganizationUsage | null;
  users: { total_users: number; active_users: number; admin_users: number; verified_users: number } | null;
  system: { total_documents: number; total_chunks: number } | null;
  recent: AuditEvent[] | null;
}

const SECTIONS: { to: string; title: string; text: string; icon: ReactNode }[] = [
  { to: '/admin/members', title: 'Members & invitations', text: 'Invite people, change roles, deactivate accounts.', icon: <Users className="h-5 w-5" /> },
  { to: '/admin/ai', title: 'AI models', text: 'Choose the providers and models that answer questions.', icon: <Bot className="h-5 w-5" /> },
  { to: '/admin/branding', title: 'Branding', text: 'Logo, name and colours your members see.', icon: <Palette className="h-5 w-5" /> },
  { to: '/admin/usage', title: 'Usage & limits', text: 'Plan limits and request rates.', icon: <Activity className="h-5 w-5" /> },
  { to: '/admin/audit', title: 'Audit log', text: 'Every sign-in, change and upload.', icon: <ScrollText className="h-5 w-5" /> },
];

function Figure({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div>
      <dt className="text-caption text-ink-muted">{label}</dt>
      <dd className="mt-1 text-display-sm font-heavy tabular-nums text-ink">{value}</dd>
      {hint && <dd className="text-caption text-ink-muted">{hint}</dd>}
    </div>
  );
}

export default function AdminDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState<Overview>({ usage: null, users: null, system: null, recent: null });
  const [failed, setFailed] = useState<string[]>([]);

  useEffect(() => {
    // Each panel loads on its own: one slow or failing source must not blank the page.
    const settle = <T,>(key: keyof Overview, label: string, request: Promise<T>) =>
      request
        .then((value) => setData((prev) => ({ ...prev, [key]: value })))
        .catch((err) => setFailed((prev) => [...prev, `${label}: ${errorMessage(err)}`]));
    settle('usage', 'Usage', api.getOrganizationUsage());
    settle('users', 'Members', api.getUserStats());
    settle('system', 'Documents', api.getSystemStats());
    settle('recent', 'Activity', api.getAuditLog({ limit: 6 }).then((p) => p.items));
  }, []);

  const { usage, users, system, recent } = data;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        eyebrow="Administration"
        title="Overview"
        description={`Your organization at a glance${user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}.`}
      />

      {failed.length > 0 && (
        <div className="mt-6"><Notice tone="warning" title="Some figures could not be loaded">{failed.join(' · ')}</Notice></div>
      )}
      {usage?.status === 'suspended' && (
        <div className="mt-6"><Notice tone="error" title="This organization is suspended">Members cannot sign in or ask questions until it is reactivated.</Notice></div>
      )}

      <Card className="mt-8">
        <dl className="grid grid-cols-2 gap-6 lg:grid-cols-4">
          {users ? (
            <>
              <Figure label="Members" value={users.active_users} hint={`${users.total_users - users.active_users} deactivated`} />
              <Figure label="Administrators" value={users.admin_users} hint={`${users.total_users - users.verified_users} unverified email${users.total_users - users.verified_users === 1 ? '' : 's'}`} />
            </>
          ) : (
            <><Skeleton className="h-16" /><Skeleton className="h-16" /></>
          )}
          {system ? (
            <>
              <Figure label="Documents" value={system.total_documents} />
              <Figure label="Indexed passages" value={system.total_chunks.toLocaleString()} />
            </>
          ) : (
            <><Skeleton className="h-16" /><Skeleton className="h-16" /></>
          )}
        </dl>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionHeading actions={<Link to="/admin/usage" className="text-small font-semibold">Details</Link>}>Plan limits</SectionHeading>
          {usage ? (
            <div className="space-y-5">
              <QuotaMeter label="Members" entry={usage.quotas.users} />
              <QuotaMeter label="Documents" entry={usage.quotas.documents} />
              <QuotaMeter label="Storage" entry={usage.quotas.storage_bytes} format={formatBytes} />
            </div>
          ) : (
            <div className="space-y-4"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
          )}
        </Card>

        <Card>
          <SectionHeading actions={<Link to="/admin/audit" className="text-small font-semibold">Full log</Link>}>Recent activity</SectionHeading>
          {recent === null ? (
            <div className="space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-8" />)}</div>
          ) : recent.length === 0 ? (
            <p className="text-small text-ink-muted">Nothing recorded yet.</p>
          ) : (
            <ol className="space-y-3">
              {recent.map((event) => (
                <li key={event.id} className="flex items-baseline justify-between gap-3 text-small">
                  <span className="min-w-0 truncate text-ink">
                    <span className="font-semibold">{event.actor_email ?? 'System'}</span>{' '}
                    <span className="text-ink-muted">{event.action.replace(/[._]/g, ' ')}</span>
                  </span>
                  <time dateTime={event.created_at} className="shrink-0 text-caption text-ink-muted">
                    {formatDistanceToNow(new Date(event.created_at), { addSuffix: true })}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <nav aria-label="Administration sections" className="mt-section">
        <h2 className="text-heading-sm font-heavy">Manage</h2>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SECTIONS.map((s) => (
            <li key={s.to}>
              <Link to={s.to} className="group flex h-full items-start gap-3 rounded-md border border-hairline bg-canvas p-4 text-ink transition-colors hover:border-field-border hover:no-underline">
                <span className="mt-0.5 text-ink-muted" aria-hidden>{s.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1 font-semibold">
                    {s.title}
                    <ArrowRight className="h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                  </span>
                  <span className="mt-1 block text-small text-ink-muted">{s.text}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
