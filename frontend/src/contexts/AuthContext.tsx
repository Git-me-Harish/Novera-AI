/*AuthContext — application-wide authentication state and helpers*/

import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
  useCallback,
} from 'react';
import api, { AUTH_EXPIRED_EVENT, refreshAccessToken } from '../services/api';

interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  avatar_url: string | null;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  preferences: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at?: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    username: string,
    password: string,
    fullName?: string,
    organizationName?: string
  ) => Promise<void>;
  acceptInvitation: (token: string, username: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (data: Partial<User>) => Promise<void>;
  isAuthenticated: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Token helpers

function getAccessToken(): string | null {
  return localStorage.getItem('access_token');
}

function getRefreshToken(): string | null {
  return localStorage.getItem('refresh_token');
}

function setTokens(access: string, refresh?: string): void {
  localStorage.setItem('access_token', access);
  if (refresh) localStorage.setItem('refresh_token', refresh);
}

function clearTokens(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

// Decode the JWT exp claim without a library.Returns the expiry as a Unix timestamp (seconds), or 0 on failure.
function getTokenExpiry(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return typeof payload.exp === 'number' ? payload.exp : 0;
  } catch {
    return 0;
  }
}

function isTokenExpiringSoon(token: string, bufferSeconds = 300): boolean {
  const exp = getTokenExpiry(token);
  if (!exp) return true;
  return Date.now() / 1000 + bufferSeconds > exp;
}

// Provider
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Auth check on mount

  const checkAuth = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setLoading(false);
      return;
    }

    // Proactively refresh if expiring within 5 minutes
    if (isTokenExpiringSoon(token)) {
      const refreshed = await refreshAccessToken();
      if (!refreshed) {
        clearTokens();
        setLoading(false);
        return;
      }
    }

    try {
      const userData = await api.getCurrentUser();
      setUser(userData as User);
    } catch {
      clearTokens();
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // The API client refreshes on 401 (single-flight) and emits this event when
  // the session cannot be renewed; an interceptor on the global axios
  // instance never saw requests made through the API client.
  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  // Auth actions
  const login = useCallback(async (email: string, password: string) => {
    const response = await api.login(email, password);
    setTokens(response.access_token, response.refresh_token ?? undefined);
    setUser(response.user as User);
  }, []);

  const register = useCallback(
    async (
      email: string,
      username: string,
      password: string,
      fullName?: string,
      organizationName?: string
    ) => {
      const response = await api.register(email, username, password, fullName, organizationName);
      setTokens(response.access_token, response.refresh_token ?? undefined);
      setUser(response.user as User);
    },
    []
  );

  const acceptInvitation = useCallback(
    async (token: string, username: string, password: string, fullName?: string) => {
      const response = await api.acceptInvitation({ token, username, password, full_name: fullName });
      setTokens(response.access_token, response.refresh_token ?? undefined);
      setUser(response.user as User);
    },
    []
  );

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await api.logout(refreshToken);
      } catch {
      }
    }
    clearTokens();
    setUser(null);
  }, []);

  const updateProfile = useCallback(async (data: Partial<User>) => {
    const updatedUser = await api.updateProfile({
      full_name: data.full_name ?? undefined,
      avatar_url: data.avatar_url ?? undefined,
      preferences: data.preferences,
      metadata: data.metadata,
    });
    setUser(updatedUser as User);
  }, []);

  const value: AuthContextType = {
    user,
    loading,
    login,
    register,
    acceptInvitation,
    logout,
    updateProfile,
    isAuthenticated: !!user,
    isAdmin:
      user?.role === 'admin' ||
      user?.role === 'org_admin' ||
      user?.role === 'super_admin',
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}