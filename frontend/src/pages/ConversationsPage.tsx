import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Archive,
  ArchiveRestore,
  CheckSquare,
  Download,
  Loader2,
  MessageSquare,
  Pencil,
  Pin,
  PinOff,
  Plus,
  RotateCcw,
  Search,
  Square,
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
import { ConversationCardSkeleton } from '../components/common/Skeletons';
import { toast } from '../utils/toast';

const TABS: { id: ConversationListView; label: string; statKey: keyof ConversationStats | null }[] = [
  { id: 'all', label: 'All', statKey: 'total' },
  { id: 'pinned', label: 'Pinned', statKey: 'pinned' },
  { id: 'archived', label: 'Archived', statKey: 'archived' },
  { id: 'deleted', label: 'Recently deleted', statKey: 'deleted' },
];

const TITLE_MAX = 200;
const PAGE_SIZE = 30;

/** Render a search snippet; matches are wrapped in control-character markers. */
function Snippet({ text }: { text: string }) {
  const parts = text.split(HIGHLIGHT_START);
  return (
    <>
      {parts.map((part, i) => {
        if (i === 0) return <span key={i}>{part}</span>;
        const [match, rest = ''] = part.split(HIGHLIGHT_END);
        return (
          <span key={i}>
            <mark className="bg-yellow-100 text-gray-900 rounded px-0.5">{match}</mark>
            {rest}
          </span>
        );
      })}
    </>
  );
}

export default function ConversationsPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<ConversationListView>('all');
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [retentionDays, setRetentionDays] = useState(30);
  const [stats, setStats] = useState<ConversationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const requestSeq = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const refreshStats = useCallback(async () => {
    try {
      setStats(await api.getConversationStats());
    } catch {
      /* stats are decorative; the list still works */
    }
  }, []);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setLoadError(null);
    setSelected(new Set());
    try {
      const page = await api.listConversations({ view, q: debouncedQuery, limit: PAGE_SIZE });
      if (seq !== requestSeq.current) return; // a newer search superseded this one
      setItems(page.items);
      setCursor(page.next_cursor);
      setRetentionDays(page.retention_days);
    } catch (error) {
      if (seq === requestSeq.current) setLoadError(errorMessage(error, 'Failed to load conversations'));
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [view, debouncedQuery]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    refreshStats();
  }, [refreshStats]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.listConversations({ view, q: debouncedQuery, cursor, limit: PAGE_SIZE });
      setItems((prev) => [...prev, ...page.items.filter((c) => !prev.some((p) => p.id === c.id))]);
      setCursor(page.next_cursor);
    } catch (error) {
      toast.error(errorMessage(error, 'Failed to load more conversations'));
    } finally {
      setLoadingMore(false);
    }
  };

  const setBusy = (id: string, busy: boolean) =>
    setBusyIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });

  const removeLocal = (ids: string[]) => {
    setItems((prev) => prev.filter((c) => !ids.includes(c.id)));
    setSelected((prev) => new Set([...prev].filter((id) => !ids.includes(id))));
  };

  /** Apply a server update and keep the list consistent with the current tab. */
  const applyUpdate = (updated: ConversationSummary) => {
    const belongs =
      (view === 'all' && !updated.is_archived) ||
      (view === 'pinned' && updated.is_pinned) ||
      (view === 'archived' && updated.is_archived);
    if (!belongs) {
      removeLocal([updated.id]);
      return;
    }
    setItems((prev) => {
      const next = prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c));
      // Keep pinned conversations first, like the server ordering.
      return view === 'all'
        ? [...next.filter((c) => c.is_pinned), ...next.filter((c) => !c.is_pinned)]
        : next;
    });
  };

  const update = async (
    conv: ConversationSummary,
    patch: { title?: string; is_pinned?: boolean; is_archived?: boolean },
    success?: string
  ) => {
    setBusy(conv.id, true);
    try {
      applyUpdate(await api.updateConversation(conv.id, patch));
      if (success) toast.success(success);
      refreshStats();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not update the conversation'));
    } finally {
      setBusy(conv.id, false);
    }
  };

  const restore = async (ids: string[]) => {
    const results = await Promise.allSettled(ids.map((id) => api.restoreConversation(id)));
    const failed = results.filter((r) => r.status === 'rejected').length;
    if (failed) toast.error(`${failed} conversation${failed > 1 ? 's' : ''} could not be restored`);
    else toast.success(ids.length > 1 ? `${ids.length} conversations restored` : 'Conversation restored');
    load();
    refreshStats();
  };

  const softDelete = async (ids: string[]) => {
    if (ids.length === 0) return;
    const snapshot = items;
    removeLocal(ids);
    try {
      const { deleted } =
        ids.length === 1
          ? (await api.deleteConversation(ids[0]), { deleted: 1 })
          : await api.bulkDeleteConversations(ids);
      toast.withAction(
        `${deleted} conversation${deleted === 1 ? '' : 's'} moved to Recently deleted`,
        { label: 'Undo', onClick: () => restore(ids) }
      );
      refreshStats();
    } catch (error) {
      setItems(snapshot);
      toast.error(errorMessage(error, 'Could not delete'));
    }
  };

  const deleteForever = async (conv: ConversationSummary) => {
    if (!confirm(`Permanently delete "${conv.title}"? This cannot be undone.`)) return;
    setBusy(conv.id, true);
    try {
      await api.deleteConversationPermanently(conv.id);
      removeLocal([conv.id]);
      toast.success('Conversation permanently deleted');
      refreshStats();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the conversation'));
    } finally {
      setBusy(conv.id, false);
    }
  };

  const exportConversation = async (conv: ConversationSummary, format: 'markdown' | 'pdf') => {
    setBusy(conv.id, true);
    try {
      await api.downloadConversation(conv.id, format);
    } catch (error) {
      toast.error(errorMessage(error, 'Export failed'));
    } finally {
      setBusy(conv.id, false);
    }
  };

  const startRename = (conv: ConversationSummary) => {
    setRenamingId(conv.id);
    setRenameValue(conv.title);
  };

  const commitRename = async (conv: ConversationSummary) => {
    const title = renameValue.trim();
    setRenamingId(null);
    if (!title || title === conv.title) return;
    await update(conv, { title });
  };

  const onRenameKey = (event: KeyboardEvent<HTMLInputElement>, conv: ConversationSummary) => {
    if (event.key === 'Enter') commitRename(conv);
    if (event.key === 'Escape') setRenamingId(null);
  };

  const toggleSelected = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allSelected = items.length > 0 && selected.size === items.length;
  const isTrash = view === 'deleted';

  const emptyMessage = debouncedQuery
    ? `No conversations match "${debouncedQuery}"`
    : {
        all: 'No conversations yet',
        pinned: 'Pin a conversation to keep it at the top',
        archived: 'Archived conversations appear here',
        deleted: `Deleted conversations stay here for ${retentionDays} days`,
      }[view];

  return (
    <div className="h-full flex flex-col bg-gray-50">
      <div className="bg-white border-b border-gray-200 flex-shrink-0">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Conversations</h1>
              <p className="text-sm text-gray-600 mt-1">
                {stats
                  ? `${stats.total} conversation${stats.total === 1 ? '' : 's'} · ${stats.messages} messages`
                  : 'Your chat history'}
              </p>
            </div>
            <button
              onClick={() => navigate('/chat')}
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 text-white rounded-md hover:bg-primary-700 font-medium"
            >
              <Plus className="w-4 h-4" />
              <span>New chat</span>
            </button>
          </div>

          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search titles and messages"
              aria-label="Search conversations"
              maxLength={200}
              className="w-full pl-10 pr-10 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                aria-label="Clear search"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          <div className="flex gap-1 overflow-x-auto" role="tablist">
            {TABS.map((tab) => {
              const count = tab.statKey && stats ? stats[tab.statKey] : null;
              return (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={view === tab.id}
                  onClick={() => setView(tab.id)}
                  className={`px-3 py-2 text-sm rounded-md whitespace-nowrap ${
                    view === tab.id ? 'bg-gray-900 text-white' : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {tab.label}
                  {count !== null && <span className="ml-1.5 opacity-70">{count}</span>}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4">
          {items.length > 0 && (
            <div className="flex items-center justify-between mb-3 text-sm">
              <button
                onClick={() => setSelected(allSelected ? new Set() : new Set(items.map((c) => c.id)))}
                className="inline-flex items-center gap-2 text-gray-700 hover:text-gray-900"
              >
                {allSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                {selected.size > 0 ? `${selected.size} selected` : 'Select all'}
              </button>
              {selected.size > 0 && !isTrash && (
                <button
                  onClick={() => softDelete([...selected])}
                  className="inline-flex items-center gap-2 px-3 py-1.5 text-red-700 border border-red-200 rounded-md hover:bg-red-50"
                >
                  <Trash2 className="w-4 h-4" /> Delete selected
                </button>
              )}
              {selected.size > 0 && isTrash && (
                <button
                  onClick={() => restore([...selected])}
                  className="inline-flex items-center gap-2 px-3 py-1.5 border border-gray-300 rounded-md hover:bg-gray-100"
                >
                  <RotateCcw className="w-4 h-4" /> Restore selected
                </button>
              )}
            </div>
          )}

          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <ConversationCardSkeleton key={i} />
              ))}
            </div>
          ) : loadError ? (
            <div className="text-center py-16">
              <p className="text-gray-700 mb-4">{loadError}</p>
              <button onClick={load} className="px-4 py-2 bg-gray-900 text-white rounded-md">
                Try again
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-16 bg-white border border-gray-200 rounded-lg">
              <MessageSquare className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-700">{emptyMessage}</p>
              {view === 'all' && !debouncedQuery && (
                <button
                  onClick={() => navigate('/chat')}
                  className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
                >
                  Start a conversation
                </button>
              )}
            </div>
          ) : (
            <ul className="space-y-2">
              {items.map((conv) => {
                const busy = busyIds.has(conv.id);
                const renaming = renamingId === conv.id;
                return (
                  <li
                    key={conv.id}
                    className={`group bg-white border rounded-lg p-4 transition-colors ${
                      selected.has(conv.id) ? 'border-primary-400 bg-primary-50/40' : 'border-gray-200 hover:border-gray-300'
                    } ${busy ? 'opacity-60' : ''}`}
                  >
                    <div className="flex items-start gap-3">
                      <button
                        onClick={() => toggleSelected(conv.id)}
                        aria-label={selected.has(conv.id) ? 'Deselect conversation' : 'Select conversation'}
                        className="mt-0.5 text-gray-400 hover:text-gray-700"
                      >
                        {selected.has(conv.id) ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                      </button>

                      <div className="flex-1 min-w-0">
                        {renaming ? (
                          <input
                            autoFocus
                            value={renameValue}
                            maxLength={TITLE_MAX}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => onRenameKey(e, conv)}
                            onBlur={() => commitRename(conv)}
                            aria-label="Conversation title"
                            className="w-full px-2 py-1 border border-gray-300 rounded-md text-base font-semibold focus:outline-none focus:ring-2 focus:ring-primary-500"
                          />
                        ) : (
                          <button
                            onClick={() => !isTrash && navigate(`/chat/${conv.id}`)}
                            disabled={isTrash}
                            className="text-left w-full"
                          >
                            <span className="flex items-center gap-2">
                              {conv.is_pinned && <Pin className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" aria-label="Pinned" />}
                              <span className="font-semibold text-gray-900 truncate">{conv.title}</span>
                            </span>
                            {(conv.snippet || conv.preview) && (
                              <span className="block text-sm text-gray-600 mt-1 line-clamp-2">
                                {conv.snippet ? <Snippet text={conv.snippet} /> : conv.preview}
                              </span>
                            )}
                          </button>
                        )}
                        <p className="text-xs text-gray-500 mt-2">
                          {conv.message_count} message{conv.message_count === 1 ? '' : 's'} ·{' '}
                          {isTrash && conv.deleted_at
                            ? `deleted ${formatDistanceToNow(new Date(conv.deleted_at), { addSuffix: true })}`
                            : formatDistanceToNow(new Date(conv.last_message_at), { addSuffix: true })}
                        </p>
                      </div>

                      <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                        {busy && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
                        {isTrash ? (
                          <>
                            <IconButton label="Restore" onClick={() => restore([conv.id])} disabled={busy}>
                              <RotateCcw className="w-4 h-4" />
                            </IconButton>
                            <IconButton label="Delete forever" onClick={() => deleteForever(conv)} disabled={busy} danger>
                              <Trash2 className="w-4 h-4" />
                            </IconButton>
                          </>
                        ) : (
                          <>
                            <IconButton label="Rename" onClick={() => startRename(conv)} disabled={busy}>
                              <Pencil className="w-4 h-4" />
                            </IconButton>
                            {!conv.is_archived && (
                              <IconButton
                                label={conv.is_pinned ? 'Unpin' : 'Pin'}
                                onClick={() => update(conv, { is_pinned: !conv.is_pinned })}
                                disabled={busy}
                              >
                                {conv.is_pinned ? <PinOff className="w-4 h-4" /> : <Pin className="w-4 h-4" />}
                              </IconButton>
                            )}
                            <IconButton
                              label={conv.is_archived ? 'Unarchive' : 'Archive'}
                              onClick={() =>
                                update(conv, { is_archived: !conv.is_archived },
                                  conv.is_archived ? 'Conversation unarchived' : 'Conversation archived')
                              }
                              disabled={busy}
                            >
                              {conv.is_archived ? <ArchiveRestore className="w-4 h-4" /> : <Archive className="w-4 h-4" />}
                            </IconButton>
                            <IconButton label="Export as Markdown" onClick={() => exportConversation(conv, 'markdown')} disabled={busy}>
                              <Download className="w-4 h-4" />
                            </IconButton>
                            <IconButton label="Delete" onClick={() => softDelete([conv.id])} disabled={busy} danger>
                              <Trash2 className="w-4 h-4" />
                            </IconButton>
                          </>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {cursor && !loading && (
            <div className="flex justify-center py-6">
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-100 disabled:opacity-60"
              >
                {loadingMore && <Loader2 className="w-4 h-4 animate-spin" />}
                Load more
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`p-2 rounded-md disabled:opacity-50 ${
        danger ? 'text-gray-500 hover:text-red-700 hover:bg-red-50' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
      }`}
    >
      {children}
    </button>
  );
}
