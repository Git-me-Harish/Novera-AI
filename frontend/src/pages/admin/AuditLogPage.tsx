import { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollText } from 'lucide-react';
import { format } from 'date-fns';
import api, { errorMessage, type AuditEvent } from '../../services/api';
import { Badge, Button, EmptyState, Field, Input, Notice, PageHeader, Select, Skeleton, type BadgeTone } from '../../ui';

/** Mirrors app.services.tenancy.audit.Action. Unknown actions show raw. */
const ACTIONS: Record<string, string> = {
  'auth.login': 'Signed in',
  'auth.login_failed': 'Failed sign-in',
  'auth.logout': 'Signed out',
  'auth.password_changed': 'Changed password',
  'auth.password_reset': 'Reset password',
  'auth.registered': 'Registered',
  'user.created': 'Created member',
  'user.updated': 'Updated member',
  'user.role_changed': 'Changed role',
  'user.deactivated': 'Deactivated member',
  'user.reactivated': 'Reactivated member',
  'user.deleted': 'Deleted member',
  'user.password_reset_by_admin': 'Reset a member’s password',
  'invitation.created': 'Sent invitation',
  'invitation.revoked': 'Revoked invitation',
  'invitation.accepted': 'Accepted invitation',
  'organization.created': 'Created organization',
  'organization.updated': 'Updated organization',
  'organization.suspended': 'Suspended organization',
  'organization.reactivated': 'Reactivated organization',
  'organization.deleted': 'Deleted organization',
  'organization.limits_changed': 'Changed limits',
  'ai_settings.updated': 'Changed AI models',
  'ai_settings.reset': 'Reset AI models',
  'document.uploaded': 'Uploaded document',
  'document.deleted': 'Deleted document',
  'document.reprocessed': 'Reprocessed document',
  'document.updated': 'Edited document details',
  'chunk.edited': 'Edited chunk',
  'chunk.reverted': 'Restored chunk',
  'chunk.deleted': 'Deleted chunk',
  'quota.exceeded': 'Hit a plan limit',
  'access.denied': 'Was denied access',
};

const CATEGORIES = [
  { value: '', label: 'All activity' },
  { value: 'auth.', label: 'Sign-in & passwords' },
  { value: 'user.', label: 'Members' },
  { value: 'invitation.', label: 'Invitations' },
  { value: 'document.', label: 'Documents' },
  { value: 'chunk.', label: 'Chunk edits' },
  { value: 'ai_settings.', label: 'AI models' },
  { value: 'organization.', label: 'Organization' },
  { value: 'quota.', label: 'Plan limits' },
  { value: 'access.', label: 'Access denied' },
];

const OUTCOME_TONE: Record<AuditEvent['outcome'], BadgeTone> = { success: 'neutral', failure: 'error', denied: 'warning' };

/** `yyyy-mm-dd` from a date input → ISO bound for the whole local day. */
const dayBound = (day: string, end: boolean) => (day ? new Date(`${day}T${end ? '23:59:59.999' : '00:00:00'}`).toISOString() : undefined);

function Row({ event }: { event: AuditEvent }) {
  const label = ACTIONS[event.action] ?? event.action;
  const details = Object.entries(event.details ?? {});
  return (
    <li>
      <details className="group">
        <summary className="grid cursor-pointer list-none grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3 hover:bg-canvas-soft sm:grid-cols-[10rem_1fr_auto]">
          <time dateTime={event.created_at} className="text-caption tabular-nums text-ink-muted sm:text-small">
            {format(new Date(event.created_at), 'd MMM yyyy, HH:mm:ss')}
          </time>
          <span className="col-span-2 row-start-2 min-w-0 text-small text-ink sm:col-span-1 sm:row-start-auto">
            <span className="font-semibold">{event.actor_email ?? 'System'}</span>{' '}
            <span className="text-ink-muted">{label.charAt(0).toLowerCase() + label.slice(1)}</span>
            {typeof event.details?.email === 'string' && <span className="text-ink-muted"> · {event.details.email}</span>}
            {typeof event.details?.filename === 'string' && <span className="text-ink-muted"> · {event.details.filename}</span>}
          </span>
          <span className="justify-self-end">
            {event.outcome !== 'success' && <Badge tone={OUTCOME_TONE[event.outcome]}>{event.outcome}</Badge>}
          </span>
        </summary>
        <dl className="grid gap-x-6 gap-y-2 border-t border-hairline bg-canvas-soft px-4 py-3 text-caption sm:grid-cols-[10rem_1fr]">
          {[
            ['Action', event.action],
            ['Role', event.actor_role],
            ['Target', event.target_type ? `${event.target_type} ${event.target_id ?? ''}` : null],
            ['IP address', event.ip_address],
            ['Browser', event.user_agent],
            ['Request', event.request_id],
          ].filter(([, v]) => v).map(([k, v]) => (
            <div key={k as string} className="contents">
              <dt className="text-ink-muted">{k}</dt>
              <dd className="break-all font-mono text-ink">{v}</dd>
            </div>
          ))}
          {details.length > 0 && (
            <>
              <dt className="text-ink-muted">Details</dt>
              <dd>
                <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-ink">{JSON.stringify(event.details, null, 2)}</pre>
              </dd>
            </>
          )}
        </dl>
      </details>
    </li>
  );
}

export default function AuditLogPage() {
  const [category, setCategory] = useState('');
  const [outcome, setOutcome] = useState<'' | AuditEvent['outcome']>('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [items, setItems] = useState<AuditEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  const query = useCallback((next?: string | null) => api.getAuditLog({
    action: category || undefined,
    outcome: outcome || undefined,
    since: dayBound(since, false),
    until: dayBound(until, true),
    limit: 50,
    cursor: next,
  }), [category, outcome, since, until]);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const page = await query();
      if (mine !== seq.current) return;
      setItems(page.items);
      setCursor(page.next_cursor);
    } catch (err) {
      if (mine === seq.current) setError(errorMessage(err, 'Could not load the audit log'));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [query]);

  useEffect(() => { load(); }, [load]);

  const more = async () => {
    setLoadingMore(true);
    try {
      const page = await query(cursor);
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
    } catch (err) {
      setError(errorMessage(err, 'Could not load more events'));
    } finally {
      setLoadingMore(false);
    }
  };

  const filtered = Boolean(category || outcome || since || until);

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        eyebrow="Administration"
        title="Audit log"
        description="Who did what, and when. Entries cannot be edited or deleted. Passwords and keys are never recorded."
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Activity">
          <Select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </Select>
        </Field>
        <Field label="Outcome">
          <Select value={outcome} onChange={(e) => setOutcome(e.target.value as typeof outcome)}>
            <option value="">Any</option>
            <option value="success">Succeeded</option>
            <option value="denied">Denied</option>
            <option value="failure">Failed</option>
          </Select>
        </Field>
        <Field label="From">
          <Input type="date" value={since} max={until || undefined} onChange={(e) => setSince(e.target.value)} />
        </Field>
        <Field label="To">
          <Input type="date" value={until} min={since || undefined} onChange={(e) => setUntil(e.target.value)} />
        </Field>
      </div>
      {filtered && (
        <button type="button" className="mt-3 text-small font-semibold text-link hover:underline"
          onClick={() => { setCategory(''); setOutcome(''); setSince(''); setUntil(''); }}>
          Clear filters
        </button>
      )}

      <div className="mt-6">
        {loading ? (
          <div className="space-y-2">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-12" />)}</div>
        ) : error && items.length === 0 ? (
          <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>Try again</Button>}>{error}</Notice>
        ) : items.length === 0 ? (
          <EmptyState icon={<ScrollText className="h-8 w-8" />} title={filtered ? 'No matching events' : 'No activity yet'}>
            {filtered ? 'Try a wider date range or another filter.' : 'Sign-ins, member changes, uploads and settings changes appear here.'}
          </EmptyState>
        ) : (
          <>
            <ol className="divide-y divide-hairline rounded-md border border-hairline bg-canvas">
              {items.map((event) => <Row key={event.id} event={event} />)}
            </ol>
            {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}
            {cursor && (
              <div className="mt-6 flex justify-center">
                <Button variant="secondary" loading={loadingMore} onClick={more}>Load older events</Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
