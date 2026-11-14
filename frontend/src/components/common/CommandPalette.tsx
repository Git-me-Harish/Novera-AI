import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  Bot,
  FileText,
  History,
  LayoutDashboard,
  MessageSquare,
  Palette,
  Plus,
  ScrollText,
  Search,
  User,
  Users,
} from 'lucide-react';
import api, { type ConversationSummary, type Document } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { cn } from '../../ui';

interface Command {
  id: string;
  group: 'Actions' | 'Conversations' | 'Documents';
  label: string;
  detail?: string;
  icon: ReactNode;
  run: () => void;
}

/**
 * Ctrl/Cmd+K command palette (WAI-ARIA combobox + listbox). Actions are
 * filtered locally; conversations are searched on the server (titles and
 * message text); documents are filtered by name.
 */
export default function CommandPalette({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [query, setQuery] = useState('');
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    opener.current = document.activeElement as HTMLElement | null;
    setQuery('');
    setActive(0);
    window.setTimeout(() => input.current?.focus(), 0);
    api.getDocuments({ limit: 100 }).then((r) => setDocuments(r.documents)).catch(() => setDocuments([]));
    return () => opener.current?.focus?.();
  }, [isOpen]);

  // Server-side conversation search, debounced; ignores stale responses.
  useEffect(() => {
    if (!isOpen) return;
    let stale = false;
    const timer = window.setTimeout(() => {
      api.listConversations({ q: query, limit: 6 })
        .then((page) => !stale && setConversations(page.items))
        .catch(() => !stale && setConversations([]));
    }, query ? 200 : 0);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
  }, [isOpen, query]);

  const go = (path: string) => () => {
    onClose();
    navigate(path);
  };

  const commands = useMemo<Command[]>(() => {
    const q = query.trim().toLowerCase();
    const actions: Command[] = [
      { id: 'new', group: 'Actions' as const, label: 'New chat', icon: <Plus className="h-4 w-4" />, run: go('/chat') },
      { id: 'convs', group: 'Actions' as const, label: 'All conversations', icon: <History className="h-4 w-4" />, run: go('/conversations') },
      { id: 'docs', group: 'Actions' as const, label: 'Documents', icon: <FileText className="h-4 w-4" />, run: go('/documents') },
      { id: 'profile', group: 'Actions' as const, label: 'Profile & security', icon: <User className="h-4 w-4" />, run: go('/profile') },
      ...(isAdmin
        ? [
            { id: 'admin', group: 'Actions' as const, label: 'Administration overview', icon: <LayoutDashboard className="h-4 w-4" />, run: go('/admin') },
            { id: 'members', group: 'Actions' as const, label: 'Members & invitations', icon: <Users className="h-4 w-4" />, run: go('/admin/members') },
            { id: 'usage', group: 'Actions' as const, label: 'Usage & limits', icon: <Activity className="h-4 w-4" />, run: go('/admin/usage') },
            { id: 'audit', group: 'Actions' as const, label: 'Audit log', icon: <ScrollText className="h-4 w-4" />, run: go('/admin/audit') },
            { id: 'ai', group: 'Actions' as const, label: 'AI models', icon: <Bot className="h-4 w-4" />, run: go('/admin/ai') },
            { id: 'brand', group: 'Actions' as const, label: 'Branding', icon: <Palette className="h-4 w-4" />, run: go('/admin/branding') },
          ]
        : []),
    ].filter((c) => !q || c.label.toLowerCase().includes(q));

    const convs: Command[] = conversations.map((c) => ({
      id: `c-${c.id}`,
      group: 'Conversations',
      label: c.title,
      detail: `${c.message_count} messages`,
      icon: <MessageSquare className="h-4 w-4" />,
      run: go(`/chat/${c.id}`),
    }));

    const docs: Command[] = documents
      .filter((d) => !q || d.filename.toLowerCase().includes(q))
      .slice(0, 6)
      .map((d) => ({
        id: `d-${d.id}`,
        group: 'Documents',
        label: d.filename,
        detail: d.status,
        icon: <FileText className="h-4 w-4" />,
        run: go(`/documents/${d.id}/edit`),
      }));
    return [...actions, ...convs, ...docs];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, conversations, documents, isAdmin]);

  useEffect(() => setActive(0), [query]);

  if (!isOpen) return null;

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, commands.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      commands[active]?.run();
    }
  };

  const groups = ['Actions', 'Conversations', 'Documents'] as const;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]">
      <div className="absolute inset-0 bg-ink-deep/50 animate-fade-in" onClick={onClose} aria-hidden />
      <div role="dialog" aria-modal="true" aria-label="Command palette"
        className="relative w-full max-w-xl overflow-hidden rounded-md border border-hairline bg-canvas animate-rise-in">
        <div className="flex items-center gap-3 border-b border-hairline px-4">
          <Search className="h-4 w-4 text-ink-muted" aria-hidden />
          <input
            ref={input}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search conversations, documents and actions"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-results"
            aria-activedescendant={commands[active] ? `cmd-${commands[active].id}` : undefined}
            aria-autocomplete="list"
            className="h-14 flex-1 bg-transparent text-body text-ink placeholder:text-ink-muted/80 focus:outline-none"
          />
          <kbd className="rounded-xs border border-hairline px-1.5 py-0.5 font-mono text-caption text-ink-muted">Esc</kbd>
        </div>
        <ul id="command-results" role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto py-2">
          {commands.length === 0 && <li className="px-4 py-8 text-center text-small text-ink-muted">No results for “{query}”</li>}
          {groups.map((group) => {
            const items = commands.filter((c) => c.group === group);
            if (!items.length) return null;
            return (
              <li key={group} role="presentation">
                <p className="px-4 pb-1 pt-3 text-caption font-semibold text-ink-muted">{group}</p>
                <ul role="group" aria-label={group}>
                  {items.map((command) => {
                    const index = commands.indexOf(command);
                    return (
                      <li
                        key={command.id}
                        id={`cmd-${command.id}`}
                        role="option"
                        aria-selected={index === active}
                        onMouseEnter={() => setActive(index)}
                        onClick={command.run}
                        className={cn(
                          'mx-2 flex cursor-pointer items-center gap-3 rounded-xs px-3 py-2 text-small',
                          index === active ? 'bg-canvas-tint text-ink' : 'text-ink'
                        )}
                      >
                        <span className="text-ink-muted" aria-hidden>{command.icon}</span>
                        <span className="flex-1 truncate">{command.label}</span>
                        {command.detail && <span className="text-caption text-ink-muted">{command.detail}</span>}
                      </li>
                    );
                  })}
                </ul>
              </li>
            );
          })}
        </ul>
      </div>
    </div>,
    document.body
  );
}
