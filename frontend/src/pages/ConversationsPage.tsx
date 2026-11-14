import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Archive,
  ArchiveRestore,
  Download,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import api, {
  errorMessage,
  HIGHLIGHT_END,
  HIGHLIGHT_START,
  type ConversationListView,
  type ConversationStats,
  type ConversationSummary,
} from '../services/api';
import { useConversation } from '../contexts/ConversationContext';
import { Button, EmptyState, IconButton, Input, Menu, Modal, Notice, PageHeader, Skeleton, Tabs, cn } from '../ui';
import { toast } from '../utils/toast';

const PAGE_SIZE = 30;

/** Search snippet: matches are wrapped in control characters, never HTML. */
function Snippet({ text }: { text: string }) {
  return (
    <>
      {text.split(HIGHLIGHT_START).map((part, i) => {
        if (i === 0) return <span key={i}>{part}</span>;
        const [match, rest = ''] = part.split(HIGHLIGHT_END);
        return (
          <span key={i}>
            <mark className="rounded-[2px] bg-highlight px-0.5 text-ink">{match}</mark>
            {rest}
          </span>
        );
      })}
    </>
  );
}

export default function ConversationsPage() {
  const navigate = useNavigate();
  const { refreshRecent } = useConversation();
  const [view, setView] = useState<ConversationListView>('all');
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [retentionDays, setRetentionDays] = useState(30);
  const [stats, setStats] = useState<ConversationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(null);
  const [forever, setForever] = useState<ConversationSummary | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  const refreshStats = useCallback(() => {
    api.getConversationStats().then(setStats).catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setLoadError(null);
    setSelected(new Set());
    try {
      const page = await api.listConversations({ view, q: debounced, limit: PAGE_SIZE });
      if (mine !== seq.current) return; // a newer search superseded this one
      setItems(page.items);
      setCursor(page.next_cursor);
      setRetentionDays(page.retention_days);
    } catch (error) {
      if (mine === seq.current) setLoadError(errorMessage(error, 'Could not load conversations'));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [view, debounced]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { refreshStats(); }, [refreshStats]);

  const afterChange = () => {
    refreshStats();
    refreshRecent();
  };

  const loadMore = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await api.listConversations({ view, q: debounced, cursor, limit: PAGE_SIZE });
      setItems((prev) => [...prev, ...page.items.filter((c) => !prev.some((p) => p.id === c.id))]);
      setCursor(page.next_cursor);
    } catch (error) {
      toast.error(errorMessage(error, 'Could not load more conversations'));
    } finally {
      setLoadingMore(false);
    }
  };

  const mark = (id: string, on: boolean) =>
    setBusy((prev) => {
      const next = new Set(prev);
      if (on) next.add(id); else next.delete(id);
      return next;
    });

  const removeLocal = (ids: string[]) => {
    setItems((prev) => prev.filter((c) => !ids.includes(c.id)));
    setSelected((prev) => new Set([...prev].filter((id) => !ids.includes(id))));
  };

  const update = async (conv: ConversationSummary, patch: { title?: string; is_pinned?: boolean; is_archived?: boolean }, done?: string) => {
    mark(conv.id, true);
    try {
      const updated = await api.updateConversation(conv.id, patch);
      const belongs =
        (view === 'all' && !updated.is_archived) || (view === 'pinned' && updated.is_pinned) || (view === 'archived' && updated.is_archived);
      if (!belongs) removeLocal([updated.id]);
      else setItems((prev) => {
        const next = prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c));
        return view === 'all' ? [...next.filter((c) => c.is_pinned), ...next.filter((c) => !c.is_pinned)] : next;
      });
      if (done) toast.success(done);
      afterChange();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not update the conversation'));
    } finally {
      mark(conv.id, false);
    }
  };

  const restore = async (ids: string[]) => {
    const results = await Promise.allSettled(ids.map((id) => api.restoreConversation(id)));
    const failed = results.filter((r) => r.status === 'rejected').length;
    if (failed) toast.error(`${failed} conversation${failed > 1 ? 's' : ''} could not be restored`);
    else toast.success(ids.length > 1 ? `${ids.length} conversations restored` : 'Conversation restored');
    load();
    afterChange();
  };

  const softDelete = async (ids: string[]) => {
    if (!ids.length) return;
    const snapshot = items;
    removeLocal(ids);
    try {
      const { deleted } = ids.length === 1
        ? (await api.deleteConversation(ids[0]), { deleted: 1 })
        : await api.bulkDeleteConversations(ids);
      toast.withAction(`${deleted} conversation${deleted === 1 ? '' : 's'} moved to Recently deleted`, {
        label: 'Undo',
        onClick: () => restore(ids),
      });
      afterChange();
    } catch (error) {
      setItems(snapshot);
      toast.error(errorMessage(error, 'Could not delete'));
    }
  };

  const deleteForever = async () => {
    const conv = forever;
    setForever(null);
    if (!conv) return;
    mark(conv.id, true);
    try {
      await api.deleteConversationPermanently(conv.id);
      removeLocal([conv.id]);
      toast.success('Conversation permanently deleted');
      afterChange();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the conversation'));
    } finally {
      mark(conv.id, false);
    }
  };

  const commitRename = async (conv: ConversationSummary) => {
    const title = renaming?.value.trim();
    setRenaming(null);
    if (title && title !== conv.title) await update(conv, { title });
  };

  const onRenameKey = (event: KeyboardEvent<HTMLInputElement>, conv: ConversationSummary) => {
    if (event.key === 'Enter') commitRename(conv);
    if (event.key === 'Escape') setRenaming(null);
  };

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  const isTrash = view === 'deleted';
  const allSelected = items.length > 0 && selected.size === items.length;
  const emptyText = debounced
    ? `No conversations match “${debounced}”.`
    : {
        all: 'Your conversations appear here once you ask a question.',
        pinned: 'Pin a conversation to keep it at the top of the list.',
        archived: 'Archived conversations appear here.',
        deleted: `Deleted conversations stay here for ${retentionDays} days, then they are removed permanently.`,
      }[view];

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        title="Conversations"
        description={stats ? `${stats.total} conversation${stats.total === 1 ? '' : 's'} · ${stats.messages} messages` : 'Everything you have asked, searchable.'}
        actions={<Button leading={<Plus className="h-4 w-4" />} onClick={() => navigate('/chat')}>New chat</Button>}
      />

      <div className="mt-8 space-y-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" aria-hidden />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search titles and messages"
            aria-label="Search conversations"
            maxLength={200}
            className="pl-11 pr-11"
          />
          {query && (
            <IconButton label="Clear search" size="sm" onClick={() => setQuery('')} className="absolute right-2 top-1/2 -translate-y-1/2">
              <X className="h-4 w-4" />
            </IconButton>
          )}
        </div>
        <Tabs
          label="Conversation views"
          value={view}
          onChange={setView}
          items={[
            { id: 'all', label: 'All', count: stats?.total },
            { id: 'pinned', label: 'Pinned', count: stats?.pinned },
            { id: 'archived', label: 'Archived', count: stats?.archived },
            { id: 'deleted', label: 'Recently deleted', count: stats?.deleted },
          ]}
        />
      </div>

      {items.length > 0 && (
        <div className="mt-4 flex min-h-[40px] items-center justify-between gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 text-small text-ink-muted">
            <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--primary))]" checked={allSelected}
              onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((c) => c.id)))} />
            {selected.size ? `${selected.size} selected` : 'Select all'}
          </label>
          {selected.size > 0 && (isTrash ? (
            <Button size="sm" variant="secondary" leading={<RotateCcw className="h-4 w-4" />} onClick={() => restore([...selected])}>
              Restore selected
            </Button>
          ) : (
            <Button size="sm" variant="danger" leading={<Trash2 className="h-4 w-4" />} onClick={() => softDelete([...selected])}>
              Delete selected
            </Button>
          ))}
        </div>
      )}

      <div className="mt-2">
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20" />)}
          </div>
        ) : loadError ? (
          <Notice tone="error" action={<Button size="sm" variant="secondary" onClick={load}>Try again</Button>}>{loadError}</Notice>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<MessageSquare className="h-8 w-8" />}
            title={debounced ? 'No matches' : 'Nothing here yet'}
            action={view === 'all' && !debounced ? <Button onClick={() => navigate('/chat')}>Start a conversation</Button> : undefined}
          >
            {emptyText}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-hairline rounded-md border border-hairline bg-canvas">
            {items.map((conv) => {
              const isBusy = busy.has(conv.id);
              const isRenaming = renaming?.id === conv.id;
              return (
                <li key={conv.id} className={cn('flex items-start gap-3 px-4 py-4', isBusy && 'opacity-60', selected.has(conv.id) && 'bg-canvas-soft')}>
                  <input type="checkbox" className="mt-1 h-4 w-4 accent-[rgb(var(--primary))]" checked={selected.has(conv.id)}
                    onChange={() => toggle(conv.id)} aria-label={`Select “${conv.title}”`} />
                  <div className="min-w-0 flex-1">
                    {isRenaming ? (
                      <Input
                        autoFocus
                        value={renaming.value}
                        maxLength={200}
                        onChange={(event) => setRenaming({ id: conv.id, value: event.target.value })}
                        onKeyDown={(event) => onRenameKey(event, conv)}
                        onBlur={() => commitRename(conv)}
                        aria-label="Conversation title"
                        className="min-h-[36px] py-1.5"
                      />
                    ) : isTrash ? (
                      <p className="truncate font-semibold text-ink">{conv.title}</p>
                    ) : (
                      <Link to={`/chat/${conv.id}`} className="flex items-center gap-2 text-ink hover:underline">
                        {conv.is_pinned && <Pin className="h-3.5 w-3.5 shrink-0 text-ink-muted" aria-label="Pinned" />}
                        <span className="truncate font-semibold">{conv.title}</span>
                      </Link>
                    )}
                    {(conv.snippet || conv.preview) && (
                      <p className="mt-1 line-clamp-2 text-small text-ink-muted">
                        {conv.snippet ? <Snippet text={conv.snippet} /> : conv.preview}
                      </p>
                    )}
                    <p className="mt-1.5 text-caption text-ink-muted">
                      {conv.message_count} message{conv.message_count === 1 ? '' : 's'} ·{' '}
                      {isTrash && conv.deleted_at
                        ? `deleted ${formatDistanceToNow(new Date(conv.deleted_at), { addSuffix: true })}`
                        : formatDistanceToNow(new Date(conv.last_message_at), { addSuffix: true })}
                    </p>
                  </div>
                  <Menu
                    label={`Actions for “${conv.title}”`}
                    items={isTrash ? [
                      { label: 'Restore', icon: <RotateCcw className="h-4 w-4" />, onSelect: () => restore([conv.id]) },
                      { label: 'Delete forever', icon: <Trash2 className="h-4 w-4" />, danger: true, onSelect: () => setForever(conv) },
                    ] : [
                      { label: 'Rename', icon: <Pencil className="h-4 w-4" />, onSelect: () => setRenaming({ id: conv.id, value: conv.title }) },
                      ...(!conv.is_archived ? [{
                        label: conv.is_pinned ? 'Unpin' : 'Pin',
                        icon: conv.is_pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />,
                        onSelect: () => update(conv, { is_pinned: !conv.is_pinned }),
                      }] : []),
                      {
                        label: conv.is_archived ? 'Unarchive' : 'Archive',
                        icon: conv.is_archived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />,
                        onSelect: () => update(conv, { is_archived: !conv.is_archived }, conv.is_archived ? 'Conversation unarchived' : 'Conversation archived'),
                      },
                      { label: 'Export as Markdown', icon: <Download className="h-4 w-4" />, onSelect: () => api.downloadConversation(conv.id, 'markdown').catch((e) => toast.error(errorMessage(e, 'Export failed'))) },
                      { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, danger: true, onSelect: () => softDelete([conv.id]) },
                    ]}
                    trigger={(props) => (
                      <IconButton {...props} label={`Actions for “${conv.title}”`} disabled={isBusy}>
                        <MoreHorizontal className="h-5 w-5" />
                      </IconButton>
                    )}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {cursor && !loading && (
        <div className="mt-6 flex justify-center">
          <Button variant="secondary" loading={loadingMore} onClick={loadMore}>Load more</Button>
        </div>
      )}

      <Modal
        open={forever !== null}
        onClose={() => setForever(null)}
        size="sm"
        title="Delete forever?"
        description={forever ? `“${forever.title}” and all its messages will be removed. This cannot be undone.` : undefined}
        footer={
          <>
            <Button variant="ghost" onClick={() => setForever(null)}>Cancel</Button>
            <Button variant="danger" onClick={deleteForever}>Delete forever</Button>
          </>
        }
      />
    </div>
  );
}
