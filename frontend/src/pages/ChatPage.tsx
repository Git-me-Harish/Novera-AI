import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  BarChart3,
  Download,
  FileDown,
  ListChecks,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  RotateCcw,
  Trash2,
  Upload,
} from 'lucide-react';
import api, { errorMessage, type ChatMessage, type ChatResponse, type Document } from '../services/api';
import MessageBubble from '../components/chat/MessageBubble';
import { PromptBar, type PromptBarHandle } from '../components/chat/PromptBar';
import AnalyticsModal from '../components/chat/AnalyticsModal';
import SelectiveExportModal from '../components/chat/SelectiveExportModal';
import { useConversation } from '../contexts/ConversationContext';
import { useAuth } from '../contexts/AuthContext';
import { useBrand } from '../contexts/BrandContext';
import { Button, IconButton, Input, Menu, Modal, PixelLoader } from '../ui';
import { toast } from '../utils/toast';

interface Meta {
  title: string;
  isPinned: boolean;
  hasMoreBefore: boolean;
  oldestSequence: number | null;
}

const EMPTY_META: Meta = { title: '', isPinned: false, hasMoreBefore: false, oldestSequence: null };

function toChatMessages(messages: { role: string; content: string; timestamp: string; metadata: any }[]): ChatMessage[] {
  return messages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content, timestamp: m.timestamp, metadata: m.metadata }));
}

export default function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const { brand } = useBrand();
  const { setCurrentConversationId, refreshRecent } = useConversation();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [meta, setMeta] = useState<Meta>(EMPTY_META);
  const [input, setInput] = useState('');
  const [busySince, setBusySince] = useState<number | null>(null);
  const [failedQuery, setFailedQuery] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [showSelectiveExport, setShowSelectiveExport] = useState(false);

  const prompt = useRef<PromptBarHandle>(null);
  const bottom = useRef<HTMLDivElement>(null);
  // The id the current view belongs to; ignores late responses after navigation.
  const activeId = useRef<string | null>(conversationId ?? null);
  // Set when this page creates a conversation, so the URL change that
  // follows does not reload what is already on screen.
  const justCreated = useRef<string | null>(null);
  const busy = busySince !== null;

  useEffect(() => {
    setCurrentConversationId(conversationId ?? null);
    return () => setCurrentConversationId(null);
  }, [conversationId, setCurrentConversationId]);

  // Load the conversation from the URL (or reset for a new chat).
  useEffect(() => {
    activeId.current = conversationId ?? null;
    setSuggestions([]);
    setFailedQuery(null);
    if (!conversationId) {
      setMessages([]);
      setMeta(EMPTY_META);
      return;
    }
    if (justCreated.current === conversationId) {
      justCreated.current = null; // already on screen
      return;
    }
    let cancelled = false;
    setLoadingConversation(true);
    api.getConversation(conversationId, { limit: 100 })
      .then((conversation) => {
        if (cancelled) return;
        setMessages(toChatMessages(conversation.messages));
        setMeta({
          title: conversation.title,
          isPinned: conversation.is_pinned,
          hasMoreBefore: conversation.has_more_before,
          oldestSequence: conversation.messages[0]?.sequence ?? null,
        });
      })
      .catch(() => {
        if (cancelled) return;
        toast.error('That conversation is not available');
        navigate('/chat', { replace: true });
      })
      .finally(() => !cancelled && setLoadingConversation(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  // Starter prompts come from this organization's own documents.
  useEffect(() => {
    if (conversationId || documents) return;
    api.getDocuments({ limit: 6, status: 'completed' })
      .then((result) => setDocuments(result.documents))
      .catch(() => setDocuments([]));
  }, [conversationId, documents]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, busy]);

  const loadEarlier = async () => {
    if (!conversationId || meta.oldestSequence == null) return;
    setLoadingEarlier(true);
    try {
      const page = await api.getConversation(conversationId, { before: meta.oldestSequence, limit: 100 });
      setMessages((current) => [...toChatMessages(page.messages), ...current]);
      setMeta((m) => ({ ...m, hasMoreBefore: page.has_more_before, oldestSequence: page.messages[0]?.sequence ?? m.oldestSequence }));
    } catch (error) {
      toast.error(errorMessage(error, 'Could not load earlier messages'));
    } finally {
      setLoadingEarlier(false);
    }
  };

  const send = useCallback(async (text?: string) => {
    const query = (text ?? input).trim();
    if (!query || busySince !== null) return;
    const startedFor = activeId.current;
    setMessages((current) => [...current, { role: 'user', content: query, timestamp: new Date().toISOString() }]);
    setInput('');
    setSuggestions([]);
    setFailedQuery(null);
    setBusySince(Date.now());
    try {
      const response: ChatResponse = await api.sendChatMessage({ query, conversation_id: startedFor });
      if (activeId.current !== startedFor) return; // user navigated away mid-answer
      if (!startedFor) {
        activeId.current = response.conversation_id;
        justCreated.current = response.conversation_id;
        setMeta((m) => ({ ...m, title: query.slice(0, 60) }));
        navigate(`/chat/${response.conversation_id}`, { replace: true });
      }
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: response.answer,
          timestamp: new Date().toISOString(),
          metadata: { sources: response.sources, confidence: response.confidence, citations: response.citations },
        },
      ]);
      setSuggestions(response.suggestions ?? []);
      refreshRecent();
      // The generated title arrives a few seconds later.
      if (!startedFor) window.setTimeout(refreshRecent, 4000);
    } catch (error) {
      if (activeId.current !== startedFor) return;
      setFailedQuery(query);
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: errorMessage(error, 'The answer could not be generated. Please try again.'),
          timestamp: new Date().toISOString(),
          metadata: { error: true },
        },
      ]);
    } finally {
      setBusySince(null);
      prompt.current?.focus();
    }
  }, [busySince, input, navigate, refreshRecent]);

  const retry = () => {
    if (!failedQuery) return;
    // Drop the failed exchange, then resend the same question.
    setMessages((current) => current.slice(0, -2));
    send(failedQuery);
  };

  const updateConversation = async (patch: { title?: string; is_pinned?: boolean }) => {
    if (!conversationId) return;
    try {
      const updated = await api.updateConversation(conversationId, patch);
      setMeta((m) => ({ ...m, title: updated.title, isPinned: updated.is_pinned }));
      refreshRecent();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not update the conversation'));
    }
  };

  const deleteConversation = async () => {
    if (!conversationId) return;
    setConfirmDelete(false);
    try {
      await api.deleteConversation(conversationId);
      refreshRecent();
      const id = conversationId;
      toast.withAction('Conversation moved to Recently deleted', {
        label: 'Undo',
        onClick: async () => {
          await api.restoreConversation(id);
          refreshRecent();
          navigate(`/chat/${id}`);
        },
      });
      navigate('/chat');
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the conversation'));
    }
  };

  const download = async (format: 'markdown' | 'pdf') => {
    if (!conversationId) return;
    try {
      await api.downloadConversation(conversationId, format);
    } catch (error) {
      toast.error(errorMessage(error, 'Export failed'));
    }
  };

  const starters = useMemo(() => {
    const docs = (documents ?? []).slice(0, 4);
    return docs.map((doc) => {
      const name = doc.filename.replace(/\.[a-z0-9]+$/i, '').replace(/[_-]+/g, ' ');
      return `Summarize the key points of “${name}”`;
    });
  }, [documents]);

  const lastIsAnswer = messages.length > 0 && messages[messages.length - 1].role === 'assistant';

  return (
    <div className="flex h-full flex-col">
      {conversationId && (
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-hairline bg-canvas px-4 lg:h-16 lg:px-6">
          {renaming ? (
            <form
              className="flex flex-1 items-center gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setRenaming(false);
                if (renameValue.trim() && renameValue.trim() !== meta.title) updateConversation({ title: renameValue.trim() });
              }}
            >
              <Input
                autoFocus
                value={renameValue}
                maxLength={200}
                onChange={(event) => setRenameValue(event.target.value)}
                onKeyDown={(event) => event.key === 'Escape' && setRenaming(false)}
                aria-label="Conversation title"
                className="min-h-[36px] py-1.5"
              />
              <Button type="submit" size="sm">Save</Button>
              <Button size="sm" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Button>
            </form>
          ) : (
            <h1 className="flex min-w-0 items-center gap-2 text-heading-sm font-heavy">
              {meta.isPinned && <Pin className="h-4 w-4 shrink-0 text-ink-muted" aria-label="Pinned" />}
              <span className="truncate">{meta.title || 'Conversation'}</span>
            </h1>
          )}
          {!renaming && (
            <Menu
              label="Conversation actions"
              items={[
                { label: 'Rename', icon: <Pencil className="h-4 w-4" />, onSelect: () => { setRenameValue(meta.title); setRenaming(true); } },
                meta.isPinned
                  ? { label: 'Unpin', icon: <PinOff className="h-4 w-4" />, onSelect: () => updateConversation({ is_pinned: false }) }
                  : { label: 'Pin', icon: <Pin className="h-4 w-4" />, onSelect: () => updateConversation({ is_pinned: true }) },
                { label: 'Export as Markdown', icon: <Download className="h-4 w-4" />, onSelect: () => download('markdown') },
                { label: 'Export as PDF', icon: <FileDown className="h-4 w-4" />, onSelect: () => download('pdf') },
                { label: 'Export selected messages…', icon: <ListChecks className="h-4 w-4" />, onSelect: () => setShowSelectiveExport(true) },
                { label: 'Usage for this conversation', icon: <BarChart3 className="h-4 w-4" />, onSelect: () => setShowAnalytics(true) },
                { label: 'Delete', icon: <Trash2 className="h-4 w-4" />, danger: true, onSelect: () => setConfirmDelete(true) },
              ]}
              trigger={(props) => (
                <IconButton {...props} label="Conversation actions">
                  <MoreHorizontal className="h-5 w-5" />
                </IconButton>
              )}
            />
          )}
        </header>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite" aria-busy={busy || loadingConversation}>
        <div className="mx-auto w-full max-w-3xl px-4 py-8 lg:px-6">
          {loadingConversation ? (
            <div className="space-y-6" aria-label="Loading conversation">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton h-16" />)}
            </div>
          ) : messages.length === 0 ? (
            <section className="pt-[8vh]">
              <h1 className="display-title">What would you like to know?</h1>
              <span className="gold-rule" aria-hidden />
              <p className="mt-4 max-w-prose text-body-loose font-book text-ink-muted">
                {brand.appName} answers from your organization's documents and cites every claim, so you can check the source.
              </p>
              {documents && documents.length === 0 ? (
                <div className="mt-8 rounded-md bg-canvas-soft p-6">
                  <p className="text-body font-semibold">No documents yet</p>
                  <p className="mt-1 text-small text-ink-muted">
                    {isAdmin ? 'Upload documents so answers have something to draw on.' : 'Ask an administrator to upload documents.'}
                  </p>
                  {isAdmin && (
                    <Link to="/documents" className="mt-4 inline-flex">
                      <Button leading={<Upload className="h-4 w-4" />}>Upload documents</Button>
                    </Link>
                  )}
                </div>
              ) : (
                starters.length > 0 && (
                  <div className="mt-8">
                    <p className="mb-3 text-label font-semibold text-ink-muted">Start with one of your documents</p>
                    <div className="grid gap-2 md:grid-cols-2">
                      {starters.map((starter) => (
                        <button
                          key={starter}
                          type="button"
                          onClick={() => send(starter)}
                          className="rounded-md border border-hairline bg-canvas p-4 text-left text-small text-ink transition-colors hover:border-ink"
                        >
                          {starter}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              )}
            </section>
          ) : (
            <div className="space-y-8">
              {meta.hasMoreBefore && (
                <div className="flex justify-center">
                  <Button variant="ghost" size="sm" loading={loadingEarlier} onClick={loadEarlier}>
                    Load earlier messages
                  </Button>
                </div>
              )}
              {messages.map((message, index) => (
                <MessageBubble key={`${message.timestamp}-${index}`} message={message} />
              ))}
              {busy && <PixelLoader label="Searching your documents and writing an answer" startedAt={busySince ?? undefined} />}
              {failedQuery && !busy && (
                <Button variant="secondary" size="sm" leading={<RotateCcw className="h-4 w-4" />} onClick={retry}>
                  Retry
                </Button>
              )}
              {lastIsAnswer && !busy && suggestions.length > 0 && (
                <div>
                  <p className="mb-2 text-caption font-semibold text-ink-muted">Follow up</p>
                  <div className="flex flex-wrap gap-2">
                    {suggestions.slice(0, 4).map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => send(suggestion)}
                        className="rounded-xs border border-hairline bg-canvas px-3 py-2 text-left text-small text-ink transition-colors hover:border-ink"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <div ref={bottom} />
        </div>
      </div>

      <div className="shrink-0 border-t border-hairline bg-canvas-warm">
        <div className="mx-auto w-full max-w-3xl px-4 py-4 lg:px-6">
          <PromptBar ref={prompt} value={input} onChange={setInput} onSubmit={() => send()} busy={busy} />
          <p className="mt-2 text-center text-caption text-ink-muted">
            Answers come from your organization's documents. Check the cited sources for important decisions.
          </p>
        </div>
      </div>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="Delete this conversation?"
        description="It moves to Recently deleted, where you can restore it."
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="danger" onClick={deleteConversation}>Delete</Button>
          </>
        }
      />
      {conversationId && showAnalytics && (
        <AnalyticsModal conversationId={conversationId} onClose={() => setShowAnalytics(false)} />
      )}
      {conversationId && showSelectiveExport && (
        <SelectiveExportModal onClose={() => setShowSelectiveExport(false)} conversationId={conversationId} />
      )}
    </div>
  );
}
