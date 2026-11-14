import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import api, { type ConversationSummary } from '../services/api';
import { useAuth } from './AuthContext';

interface ConversationContextType {
  currentConversationId: string | null;
  setCurrentConversationId: (id: string | null) => void;
  /** Pinned first, then most recent — the sidebar list. */
  recent: ConversationSummary[];
  recentLoading: boolean;
  /** Re-read after anything that creates, renames, pins or deletes a conversation. */
  refreshRecent: () => Promise<void>;
}

const ConversationContext = createContext<ConversationContextType | undefined>(undefined);
const RECENT_LIMIT = 30;

export function ConversationProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [recent, setRecent] = useState<ConversationSummary[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);

  const refreshRecent = useCallback(async () => {
    if (!isAuthenticated) return;
    setRecentLoading(true);
    try {
      setRecent((await api.listConversations({ limit: RECENT_LIMIT })).items);
    } catch {
      /* the sidebar list is non-critical; keep what we have */
    } finally {
      setRecentLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (isAuthenticated) refreshRecent();
    else setRecent([]);
  }, [isAuthenticated, refreshRecent]);

  const value = useMemo(
    () => ({ currentConversationId, setCurrentConversationId, recent, recentLoading, refreshRecent }),
    [currentConversationId, recent, recentLoading, refreshRecent]
  );
  return <ConversationContext.Provider value={value}>{children}</ConversationContext.Provider>;
}

export function useConversation() {
  const context = useContext(ConversationContext);
  if (!context) {
    throw new Error('useConversation must be used within ConversationProvider');
  }
  return context;
}
