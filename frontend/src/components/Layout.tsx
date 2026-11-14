import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  Bot,
  ChevronsLeft,
  ChevronsRight,
  FileText,
  History,
  LayoutDashboard,
  LogOut,
  Menu as MenuIcon,
  MessageSquare,
  Monitor,
  Moon,
  Palette,
  Pin,
  Plus,
  ScrollText,
  Sun,
  User as UserIcon,
  Users,
  X,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useConversation } from '../contexts/ConversationContext';
import { useTheme, type ThemePreference } from '../contexts/ThemeContext';
import { Wordmark } from './brand/Wordmark';
import CommandPalette from './common/CommandPalette';
import { useCommandPalette } from '../hooks/useCommandPalette';
import { Button, IconButton, Menu, cn } from '../ui';

interface NavEntry {
  to: string;
  label: string;
  icon: typeof MessageSquare;
  end?: boolean;
}

const WORKSPACE_NAV: NavEntry[] = [
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/conversations', label: 'Conversations', icon: History },
  { to: '/documents', label: 'Documents', icon: FileText },
];

const ADMIN_NAV: NavEntry[] = [
  { to: '/admin', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/admin/members', label: 'Members', icon: Users },
  { to: '/admin/usage', label: 'Usage & limits', icon: Activity },
  { to: '/admin/audit', label: 'Audit log', icon: ScrollText },
  { to: '/admin/ai', label: 'AI models', icon: Bot },
  { to: '/admin/branding', label: 'Branding', icon: Palette },
];

const THEME_OPTIONS: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'system', label: 'Match system', icon: Monitor },
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
];

const COLLAPSE_KEY = 'novera:sidebar-collapsed';

/**
 * App shell. Desktop: a collapsible sidebar (workspace navigation, pinned
 * and recent conversations, admin section, account menu). Below the laptop
 * breakpoint it becomes a drawer behind a 56px top bar.
 */
export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const palette = useCommandPalette();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => setDrawerOpen(false), [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setDrawerOpen(false);
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, value ? '0' : '1');
      } catch {
        /* preference not persisted */
      }
      return !value;
    });
  };

  return (
    <div className="flex h-[100dvh] bg-canvas-warm text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-xs focus:bg-primary focus:px-4 focus:py-2 focus:text-on-primary"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside
        className={cn(
          'hidden shrink-0 border-r border-hairline bg-canvas transition-[width] duration-200 lg:flex lg:flex-col',
          collapsed ? 'w-16' : 'w-[272px]'
        )}
        aria-label="Primary"
      >
        <Sidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink-deep/50 animate-fade-in" onClick={() => setDrawerOpen(false)} aria-hidden />
          <aside
            className="relative flex h-full w-[min(86vw,300px)] flex-col border-r border-hairline bg-canvas animate-rise-in"
            aria-label="Primary"
            role="dialog"
            aria-modal="true"
          >
            <Sidebar collapsed={false} onClose={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileTopBar onOpen={() => setDrawerOpen(true)} />
        <main id="main" tabIndex={-1} className="min-h-0 flex-1 overflow-y-auto focus:outline-none">
          {children}
        </main>
      </div>
      {/* Signed-in only: on public pages it would call authenticated APIs. */}
      <CommandPalette isOpen={palette.isOpen} onClose={palette.close} />
    </div>
  );
}

function MobileTopBar({ onOpen }: { onOpen: () => void }) {
  const navigate = useNavigate();
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-hairline bg-canvas px-2 lg:hidden">
      <IconButton label="Open navigation" onClick={onOpen}>
        <MenuIcon className="h-5 w-5" />
      </IconButton>
      <Link to="/chat" className="px-2" aria-label="Home">
        <Wordmark />
      </Link>
      <IconButton label="New chat" onClick={() => navigate('/chat')}>
        <Plus className="h-5 w-5" />
      </IconButton>
    </header>
  );
}

function Sidebar({
  collapsed,
  onToggleCollapsed,
  onClose,
}: {
  collapsed: boolean;
  onToggleCollapsed?: () => void;
  onClose?: () => void;
}) {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const { recent, currentConversationId } = useConversation();
  const pinned = recent.filter((c) => c.is_pinned);
  const latest = recent.filter((c) => !c.is_pinned).slice(0, 15);

  return (
    <>
      <div className={cn('flex h-16 shrink-0 items-center border-b border-hairline', collapsed ? 'justify-center' : 'justify-between px-4')}>
        {!collapsed && (
          <Link to="/chat" aria-label="Home">
            <Wordmark />
          </Link>
        )}
        {onClose ? (
          <IconButton label="Close navigation" onClick={onClose}>
            <X className="h-5 w-5" />
          </IconButton>
        ) : (
          <IconButton label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} onClick={onToggleCollapsed}>
            {collapsed ? <ChevronsRight className="h-5 w-5" /> : <ChevronsLeft className="h-5 w-5" />}
          </IconButton>
        )}
      </div>

      <div className={cn('shrink-0', collapsed ? 'px-2 py-3' : 'px-3 py-3')}>
        {collapsed ? (
          <IconButton label="New chat" variant="tertiary" onClick={() => navigate('/chat')} className="w-full">
            <Plus className="h-5 w-5" />
          </IconButton>
        ) : (
          <Button block leading={<Plus className="h-4 w-4" />} onClick={() => navigate('/chat')}>
            New chat
          </Button>
        )}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-3" aria-label="Workspace">
        <NavList entries={WORKSPACE_NAV} collapsed={collapsed} />

        {!collapsed && pinned.length > 0 && (
          <ConversationGroup title="Pinned" items={pinned} currentId={currentConversationId} pinned />
        )}
        {!collapsed && latest.length > 0 && (
          <ConversationGroup title="Recent" items={latest} currentId={currentConversationId} />
        )}

        {isAdmin && (
          <div className="mt-5">
            {!collapsed && <p className="px-3 pb-1.5 text-caption font-semibold text-ink-muted">Administration</p>}
            {collapsed && <div className="mx-3 mb-2 border-t border-hairline" aria-hidden />}
            <NavList entries={ADMIN_NAV} collapsed={collapsed} />
          </div>
        )}
      </nav>

      <AccountMenu collapsed={collapsed} />
    </>
  );
}

function NavList({ entries, collapsed }: { entries: NavEntry[]; collapsed: boolean }) {
  return (
    <ul className="space-y-0.5">
      {entries.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                'relative flex items-center gap-3 rounded-md px-3 py-2 text-label transition-colors',
                collapsed && 'justify-center px-0',
                isActive ? 'bg-canvas-tint font-semibold text-ink' : 'text-ink-muted hover:bg-canvas-soft hover:text-ink'
              )
            }
          >
            {({ isActive }) => (
              <>
                {/* Design.md app-shell row: the active indicator is the action charcoal. */}
                {isActive && <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-primary" aria-hidden />}
                <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
                {!collapsed && <span className="truncate">{label}</span>}
              </>
            )}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function ConversationGroup({
  title,
  items,
  currentId,
  pinned,
}: {
  title: string;
  items: { id: string; title: string }[];
  currentId: string | null;
  pinned?: boolean;
}) {
  return (
    <div className="mt-5">
      <p className="px-3 pb-1.5 text-caption font-semibold text-ink-muted">{title}</p>
      <ul className="space-y-0.5">
        {items.map((conv) => (
          <li key={conv.id}>
            <Link
              to={`/chat/${conv.id}`}
              aria-current={conv.id === currentId ? 'page' : undefined}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-small transition-colors',
                conv.id === currentId ? 'bg-canvas-tint text-ink' : 'text-ink-muted hover:bg-canvas-soft hover:text-ink'
              )}
            >
              {pinned && <Pin className="h-3.5 w-3.5 shrink-0" aria-hidden />}
              <span className="truncate">{conv.title}</span>
            </Link>
          </li>
        ))}
      </ul>
      {!pinned && (
        <Link to="/conversations" className="mt-1 block px-3 py-1.5 text-caption text-link hover:underline">
          View all conversations
        </Link>
      )}
    </div>
  );
}

function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const { user, logout } = useAuth();
  const { preference, setPreference } = useTheme();
  const navigate = useNavigate();
  const name = user?.full_name || user?.username || user?.email || 'Account';
  const initials = name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div className={cn('shrink-0 border-t border-hairline', collapsed ? 'p-2' : 'p-3')}>
      <Menu
        label="Account"
        align="start"
        items={[
          { label: 'Profile & security', icon: <UserIcon className="h-4 w-4" />, onSelect: () => navigate('/profile') },
          ...THEME_OPTIONS.map(({ value, label, icon: Icon }) => ({
            label,
            checked: preference === value,
            icon: <Icon className="h-4 w-4" />,
            onSelect: () => setPreference(value),
          })),
          {
            label: 'Sign out',
            icon: <LogOut className="h-4 w-4" />,
            danger: true,
            onSelect: async () => {
              await logout();
              navigate('/login');
            },
          },
        ]}
        trigger={(props) => (
          <button
            {...props}
            type="button"
            className={cn(
              'flex w-full items-center gap-3 rounded-md text-left transition-colors hover:bg-canvas-soft',
              collapsed ? 'justify-center p-1.5' : 'px-2 py-2'
            )}
            aria-label={collapsed ? `Account: ${name}` : undefined}
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-caption font-semibold text-canvas" aria-hidden>
              {initials}
            </span>
            {!collapsed && (
              <span className="min-w-0">
                <span className="block truncate text-label font-semibold text-ink">{name}</span>
                <span className="block truncate text-caption text-ink-muted">{user?.email}</span>
              </span>
            )}
          </button>
        )}
      />
    </div>
  );
}
