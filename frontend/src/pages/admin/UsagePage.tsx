import { useCallback, useEffect, useState } from 'react';
import api, { errorMessage, type OrganizationUsage } from '../../services/api';
import { QuotaMeter, formatBytes } from '../../components/admin/QuotaMeter';
import { Badge, Button, Card, Notice, PageHeader, SectionHeading, Skeleton } from '../../ui';

const RATE_LABELS: Record<keyof OrganizationUsage['rate_limits'], { label: string; unit: string }> = {
  chat_per_minute: { label: 'Questions', unit: 'per minute' },
  chat_messages_per_day: { label: 'Questions', unit: 'per day' },
  upload_per_minute: { label: 'Uploads', unit: 'per minute' },
  api_per_minute: { label: 'All API requests', unit: 'per minute' },
};

// Shared by everyone in the organization (see RateLimitMiddleware); 0 means no daily cap.
const rateValue = (key: keyof OrganizationUsage['rate_limits'], value: number) =>
  key === 'chat_messages_per_day' && value === 0 ? 'No limit' : value.toLocaleString();

export default function UsagePage() {
  const [usage, setUsage] = useState<OrganizationUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api.getOrganizationUsage().then(setUsage).catch((err) => setError(errorMessage(err, 'Could not load usage')));
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        eyebrow="Administration"
        title="Usage & limits"
        description="What your organization uses against its plan. Limits are set by the platform operator."
        actions={usage && <Badge tone={usage.status === 'active' ? 'success' : 'error'}>{usage.status === 'active' ? 'Active' : 'Suspended'}</Badge>}
      />

      {error ? (
        <div className="mt-8"><Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>Try again</Button>}>{error}</Notice></div>
      ) : !usage ? (
        <div className="mt-8 space-y-4"><Skeleton className="h-48" /><Skeleton className="h-40" /></div>
      ) : (
        <div className="mt-8 space-y-6">
          {usage.status === 'suspended' && (
            <Notice tone="error" title="This organization is suspended">
              Members cannot sign in or ask questions until the platform operator reactivates it.
            </Notice>
          )}
          <Card>
            <SectionHeading description="Uploads and invitations are refused once a limit is reached.">Plan limits</SectionHeading>
            <div className="space-y-6">
              <QuotaMeter label="Members" entry={usage.quotas.users} />
              <QuotaMeter label="Documents" entry={usage.quotas.documents} />
              <QuotaMeter label="Storage" entry={usage.quotas.storage_bytes} format={formatBytes} />
            </div>
            <p className="mt-6 border-t border-hairline pt-4 text-small text-ink-muted">
              {usage.quotas.pending_invitations ?? 0} pending invitation{usage.quotas.pending_invitations === 1 ? '' : 's'} count toward the member limit.
            </p>
          </Card>

          <Card>
            <SectionHeading description="Shared by everyone in the organization. Requests over a limit are asked to retry shortly.">Rate limits</SectionHeading>
            <dl className="grid gap-4 sm:grid-cols-2">
              {(Object.keys(RATE_LABELS) as (keyof OrganizationUsage['rate_limits'])[]).map((key) => (
                <div key={key} className="rounded-sm bg-canvas-soft p-4">
                  <dt className="text-caption text-ink-muted">{RATE_LABELS[key].label} · {RATE_LABELS[key].unit}</dt>
                  <dd className="mt-1 text-heading-sm font-heavy tabular-nums text-ink">{rateValue(key, usage.rate_limits[key])}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
      )}
    </div>
  );
}
