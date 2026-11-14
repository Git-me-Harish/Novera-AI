import { useCallback, useEffect, useState } from 'react';
import { FileText } from 'lucide-react';
import api, { errorMessage } from '../../services/api';
import { Badge, Button, Modal, Notice, Skeleton } from '../../ui';

interface ConversationAnalytics {
  total_messages: number;
  user_queries: number;
  ai_responses: number;
  documents_referenced: string[];
  total_sources_cited: number;
  confidence_distribution: { high: number; medium: number; low: number };
  primary_document: string | null;
  time_periods_discussed: string[];
  created_at: string;
  duration_minutes: number;
}

const duration = (minutes: number) =>
  minutes < 1 ? 'under a minute' : minutes < 60 ? `${Math.round(minutes)} min` : `${(minutes / 60).toFixed(1)} h`;

const CONFIDENCE = [
  { key: 'high', label: 'High', bar: 'bg-success' },
  { key: 'medium', label: 'Medium', bar: 'bg-warning' },
  { key: 'low', label: 'Low', bar: 'bg-error' },
] as const;

/** What a conversation drew on: questions, sources, documents, confidence. */
export default function AnalyticsModal({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const [data, setData] = useState<ConversationAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setData(null);
    api.getConversationAnalytics(conversationId)
      .then(setData)
      .catch((err) => setError(errorMessage(err, 'Could not load the usage summary')));
  }, [conversationId]);

  useEffect(() => { load(); }, [load]);

  const answered = data ? CONFIDENCE.reduce((sum, c) => sum + data.confidence_distribution[c.key], 0) : 0;

  return (
    <Modal open onClose={onClose} size="lg" title="Conversation summary" footer={<Button variant="secondary" onClick={onClose}>Close</Button>}>
      {error ? (
        <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>Try again</Button>}>{error}</Notice>
      ) : !data ? (
        <div className="space-y-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-10" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <div className="space-y-6">
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              ['Questions', data.user_queries],
              ['Answers', data.ai_responses],
              ['Sources cited', data.total_sources_cited],
              ['Duration', duration(data.duration_minutes)],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-sm bg-canvas-soft p-4">
                <dt className="text-caption text-ink-muted">{label}</dt>
                <dd className="mt-1 text-heading-sm font-heavy tabular-nums text-ink">{value}</dd>
              </div>
            ))}
          </dl>

          {answered > 0 && (
            <section>
              <h3 className="mb-2 text-small font-semibold text-ink">Answer confidence</h3>
              <div className="flex h-2 overflow-hidden rounded-full bg-canvas-tint" role="img"
                aria-label={CONFIDENCE.map((c) => `${c.label}: ${data.confidence_distribution[c.key]}`).join(', ')}>
                {CONFIDENCE.map((c) => (
                  <div key={c.key} className={c.bar} style={{ width: `${(data.confidence_distribution[c.key] / answered) * 100}%` }} />
                ))}
              </div>
              <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-caption text-ink-muted">
                {CONFIDENCE.map((c) => (
                  <li key={c.key} className="inline-flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${c.bar}`} aria-hidden />
                    {c.label} {data.confidence_distribution[c.key]}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-small font-semibold text-ink">Documents used</h3>
            {data.documents_referenced.length === 0 ? (
              <p className="text-small text-ink-muted">No answer in this conversation cited a document.</p>
            ) : (
              <ul className="divide-y divide-hairline rounded-sm border border-hairline">
                {data.documents_referenced.map((doc) => (
                  <li key={doc} className="flex items-center gap-3 px-4 py-2.5 text-small text-ink">
                    <FileText className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{doc}</span>
                    {doc === data.primary_document && <Badge>Most used</Badge>}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {data.time_periods_discussed.length > 0 && (
            <section>
              <h3 className="mb-2 text-small font-semibold text-ink">Periods discussed</h3>
              <div className="flex flex-wrap gap-2">
                {data.time_periods_discussed.map((p) => <Badge key={p}>{p}</Badge>)}
              </div>
            </section>
          )}

          <p className="text-caption text-ink-muted">Started {new Date(data.created_at).toLocaleString()} · {data.total_messages} messages</p>
        </div>
      )}
    </Modal>
  );
}
