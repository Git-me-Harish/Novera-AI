import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type { Customization, CustomizationUpdateRequest, ThemePreset } from '../types';
import { apiBase } from '../utils/apiBase';

const API_VERSION = '/api/v1';
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

/** Fired when the session cannot be refreshed; AuthContext listens and signs out. */
export const AUTH_EXPIRED_EVENT = 'novera:auth-expired';

/* ── Chat history ─────────────────────────────────────────────────────────── */

/** Search snippets wrap matches in these control characters (never in user text). */
export const HIGHLIGHT_START = '\u0002';
export const HIGHLIGHT_END = '\u0003';

export interface ConversationSummary {
  id: string;
  title: string;
  title_source: 'default' | 'auto' | 'user';
  is_pinned: boolean;
  is_archived: boolean;
  message_count: number;
  last_message_at: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  /** Latest message, trimmed. */
  preview: string | null;
  /** Best search match with highlight markers; only present when searching. */
  snippet: string | null;
}

export interface ConversationPage {
  items: ConversationSummary[];
  next_cursor: string | null;
  retention_days: number;
}

export interface StoredMessage {
  id: string;
  sequence: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata: ChatMessage['metadata'] & Record<string, unknown>;
}

export interface ConversationDetail extends ConversationSummary {
  user_id: string;
  metadata: Record<string, unknown>;
  context: Record<string, unknown>;
  messages: StoredMessage[];
  has_more_before: boolean;
}

export interface ConversationStats {
  total: number;
  pinned: number;
  archived: number;
  deleted: number;
  messages: number;
}

export type ConversationListView = 'all' | 'pinned' | 'archived' | 'deleted';

/** @deprecated kept for older components; use ConversationDetail. */
export type Conversation = ConversationDetail;


/* ── Organization membership & administration ─────────────────────────── */

export type RegistrationMode = 'invite_only' | 'self_serve' | 'disabled';
export type InvitableRole = 'user' | 'admin' | 'org_admin';

export interface Invitation {
  id: string;
  email: string;
  role: InvitableRole;
  status: 'pending' | 'accepted' | 'revoked' | 'expired';
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  invited_by: string | null;
}

export interface CreatedInvitation extends Invitation {
  email_sent: boolean;
  /** Shown once; only a hash is stored server-side. */
  invite_url: string;
}

export interface InvitationPreview {
  email: string;
  role: InvitableRole;
  organization: string;
  expires_at: string;
}

export interface QuotaEntry {
  limit: number | null;
  used: number | null;
  remaining: number | null;
  percent: number | null;
}

export interface OrganizationUsage {
  organization_id: string;
  status: 'active' | 'suspended';
  quotas: {
    users: QuotaEntry;
    documents: QuotaEntry;
    storage_bytes: QuotaEntry;
    pending_invitations: number;
  };
  rate_limits: {
    chat_per_minute: number;
    upload_per_minute: number;
    api_per_minute: number;
    chat_messages_per_day: number;
  };
}

export interface AuditEvent {
  id: string;
  created_at: string;
  organization_id: string | null;
  actor_user_id: string | null;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  outcome: 'success' | 'failure' | 'denied';
  target_type: string | null;
  target_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  request_id: string | null;
  details: Record<string, unknown>;
}

/* ── Domain types ───────────────────────────────────────────────────────── */

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  metadata?: {
    sources?: Source[];
    confidence?: string;
    citations?: any[];
    error?: boolean;
    reformulated_query?: string;
  };
}

export interface ChatRequest {
  query: string;
  conversation_id?: string | null;
  doc_type?: string;
  department?: string;
  stream?: boolean;
}

export interface Source {
  document: string;
  page: number | null;
  section: string | null;
  chunk_id: string;
}

export interface ChatResponse {
  answer: string;
  conversation_id: string;
  sources: Source[];
  citations: any[];
  confidence: string;
  status: string;
  suggestions?: string[];
  metadata: {
    chunks_used?: number;
    tokens?: any;
    searched_documents?: boolean;
    retrieval_metadata?: any;
    context_summary?: {
      primary_document?: string;
      active_documents?: string[];
      recent_time_period?: string;
      message_count?: number;
      last_intent?: string;
    };
    query_reformulated?: boolean;
  };
}

export interface Document {
  id: string;
  filename: string;
  doc_type: string;
  department: string | null;
  total_pages: number;
  total_chunks: number;
  status: string;
  upload_date: string;
  processed_date: string | null;
}


export interface AdminUser {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  last_login: string | null;
  document_count: number;
}

export interface UserStats {
  total_users: number;
  active_users: number;
  admin_users: number;
  regular_users: number;
  verified_users: number;
}

export interface SystemStats {
  total_users: number;
  total_documents: number;
  total_chunks: number;
  active_sessions: number;
  storage_used_mb: number;
}

export interface TokenStats {
  conversation_id: string;
  summary: {
    total_messages: number;
    total_tokens: number;
    cached_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cache_efficiency_percent: number;
    total_cost_usd: number;
    avg_tokens_per_message: number;
    avg_cost_per_message: number;
  };
  messages: MessageTokenStat[];
  pricing_info: {
    model: string;
    cached_token_price: number;
    regular_token_price: number;
    currency: string;
  };
}

export interface MessageTokenStat {
  message_id: string;
  timestamp: string;
  tokens: {
    total: number;
    cached: number;
    prompt: number;
    completion: number;
  };
  cost_usd: number;
}

export interface ChunkData {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  chunk_type: string;
  page_numbers: number[];
  section_title: string | null;
  token_count: number;
  title: string | null;
  is_edited: boolean;
  edited_at: string | null;
  edited_by: string | null;
  edit_count: number;
  metadata: any;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  original_filename: string;
  file_size_mb: number;
  doc_type: string;
  department: string | null;
  total_pages: number;
  total_chunks: number;
  has_tables: boolean;
  has_images: boolean;
  status: string;
  upload_date: string;
  processed_date: string | null;
  mime_type: string;
  preview_type: string;
  is_previewable: boolean;
}

export interface EditHistoryItem {
  id: string;
  edited_at: string;
  edited_by: string;
  old_content: string;
  new_content: string;
  change_summary: string | null;
  metadata: any;
}

export interface DocumentEditStats {
  total_chunks: number;
  edited_chunks: number;
  unedited_chunks: number;
  total_edits: number;
  edit_percentage: number;
}

/* ── Transport ────────────────────────────────────────────────────────────── */

export const apiClient: AxiosInstance = axios.create({
  baseURL: `${apiBase}${API_VERSION}`,
  headers: { 'Content-Type': 'application/json' },
  // Answers can take a while; uploads set their own timeout.
  timeout: 60_000,
});
const client = apiClient;

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshInFlight: Promise<string | null> | null = null;

/**
 * Exchange the refresh token for a new access token.
 * Single-flight: concurrent callers share one request, so a burst of 401s
 * triggers exactly one refresh instead of racing each other.
 */
export function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (!refreshToken) return null;
      try {
        const res = await axios.post<{ access_token: string; refresh_token?: string }>(
          `${apiBase}${API_VERSION}/auth/refresh`,
          { refresh_token: refreshToken },
          { timeout: 15_000 }
        );
        localStorage.setItem(ACCESS_TOKEN_KEY, res.data.access_token);
        // Store a rotated refresh token if the server issues one.
        if (res.data.refresh_token) {
          localStorage.setItem(REFRESH_TOKEN_KEY, res.data.refresh_token);
        }
        return res.data.access_token;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export function clearSession(): void {
  // Only our own keys: other preferences in localStorage must survive sign-out.
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

const NO_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/register', '/auth/logout'];

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const isAuthCall = NO_REFRESH_PATHS.some((p) => original?.url?.startsWith(p));
    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      const token = await refreshAccessToken();
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return client(original);
      }
      clearSession();
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    return Promise.reject(error);
  }
);

/** The server's error message for display, without leaking request data. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { detail?: unknown; message?: string } | undefined;
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail)) return 'Please check the highlighted fields';
    if (data?.message) return data.message;
    if (error.code === 'ECONNABORTED') return 'The request timed out. Please try again.';
    if (!error.response) return 'Cannot reach the server. Check your connection.';
  }
  return fallback;
}

/**
 * Turn a FastAPI 422 into a readable Error. Never logs: validation errors echo
 * the submitted input, which for login is the password.
 */
function throwValidationError(error: unknown): void {
  const detail = axios.isAxiosError(error)
    ? (error.response?.data as { detail?: unknown } | undefined)?.detail
    : undefined;
  if (Array.isArray(detail)) {
    throw new Error(
      detail
        .map((item: { loc?: unknown[]; msg?: string }) =>
          `${(item.loc ?? []).filter((part) => part !== 'body').join('.')}: ${item.msg ?? 'invalid'}`)
        .join('; ')
    );
  }
}

function downloadFilename(header: string | undefined, fallback: string): string {
  const match = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match ? decodeURIComponent(match[1]) : fallback;
}

/** Save a Blob as a file in the browser. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/* ── API ──────────────────────────────────────────────────────────────── */

class APIService {
  async healthCheck() {
    try {
      const response = await client.get('/health');
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  async sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
    const response = await client.post('/chat', request);
    return response.data;
  }

  async getConversationAnalytics(conversationId: string): Promise<any> {
    const response = await client.get(`/chat/conversations/${conversationId}/analytics`);
    return response.data;
  }

  async getConversationTokenStats(conversationId: string): Promise<TokenStats> {
    const response = await client.get(`/chat/conversations/${conversationId}/token-stats`);
    return response.data;
  }

  async uploadDocument(
    file: File,
    docType: string,
    department?: string
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    const params: any = { doc_type: docType };
    if (department) params.department = department;

    const response = await client.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      params,
    });
    return response.data;
  }

  async uploadDocuments(
    files: File[],
    docType: string,
    department?: string
  ): Promise<any> {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));

    const params: any = { doc_type: docType };
    if (department) params.department = department;

    const response = await client.post('/documents/upload-multiple', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params,
    });
    return response.data;
  }

  async getDocuments(params?: {
    skip?: number;
    limit?: number;
    doc_type?: string;
    status?: string;
    department?: string;
  }): Promise<{ total: number; documents: Document[] }> {
    const response = await client.get('/documents', { params });
    return response.data;
  }

  async getDocumentStatus(documentId: string): Promise<any> {
    const response = await client.get(`/documents/${documentId}/status`);
    return response.data;
  }

  async deleteDocument(documentId: string): Promise<void> {
    await client.delete(`/documents/${documentId}`);
  }

  async search(query: string, topK: number = 5, docType?: string) {
    const response = await client.post('/search', null, {
      params: { query, top_k: topK, doc_type: docType },
    });
    return response.data;
  }

  async register(
    email: string,
    username: string,
    password: string,
    fullName?: string,
    organizationName?: string
  ): Promise<any> {
    try {
      const response = await client.post('/auth/register', {
        email,
        username,
        password,
        full_name: fullName,
        organization_name: organizationName,
      });
      
      return response.data;
      
    } catch (error: any) {
      if (error.response?.status === 422) {
        throwValidationError(error);
      }
      throw error;
    }
  }

  async login(email: string, password: string): Promise<any> {
    try {
      
      const response = await client.post('/auth/login', {
        email: email,
        password: password,
      });
      
      
      return response.data;
      
    } catch (error: any) {
      
      if (error.response?.status === 422) {
        throwValidationError(error);
      }
      
      throw error;
    }
  }

  async logout(refreshToken: string): Promise<void> {
    await client.post('/auth/logout', {
      refresh_token: refreshToken,
    });
  }

  async getCurrentUser(): Promise<any> {
    const response = await client.get('/auth/me');
    return response.data;
  }

  async updateProfile(data: {
    full_name?: string;
    avatar_url?: string;
    preferences?: Record<string, any>;
    metadata?: Record<string, any>;
  }): Promise<any> {
    const response = await client.put('/auth/profile', data);
    return response.data;
  }

  async changePassword(
    currentPassword: string,
    newPassword: string
  ): Promise<void> {
    await client.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  async forgotPassword(email: string): Promise<any> {
  try {
    const response = await client.post('/auth/forgot-password', {
      email,
    });
    return response.data;
  } catch (error: any) {
    throw error;
  }
}

  async verifyResetToken(token: string): Promise<any> {
    try {
      const response = await client.post('/auth/verify-reset-token', {
        token,
      });
      return response.data;
    } catch (error: any) {
      throw error;
    }
  }

  async resetPassword(token: string, newPassword: string): Promise<any> {
    try {
      const response = await client.post('/auth/reset-password', {
        token,
        new_password: newPassword,
      });
      return response.data;
    } catch (error: any) {
      throw error;
    }
  }

  async verifyEmail(token: string): Promise<any> {
    try {
      const response = await client.post('/auth/verify-email', {
        token,
      });
      return response.data;
    } catch (error: any) {
      throw error;
    }
  }

  async resendVerificationEmail(): Promise<any> {
    try {
      const response = await client.post('/auth/resend-verification');
      return response.data;
    } catch (error: any) {
      throw error;
    }
  }

  async getUsers(params?: {
    skip?: number;
    limit?: number;
    role?: string;
    is_active?: boolean;
    search?: string;
  }): Promise<{ total: number; users: AdminUser[] }> {
    const response = await client.get('/admin/users', { params });
    return response.data;
  }

  async getUserStats(): Promise<UserStats> {
    const response = await client.get('/admin/users/stats');
    return response.data;
  }

  async getSystemStats(): Promise<SystemStats> {
    const response = await client.get('/admin/stats/system');
    return response.data;
  }

  async createUser(data: {
    email: string;
    username: string;
    password: string;
    full_name?: string;
    role: string;
    is_active: boolean;
  }): Promise<any> {
    const response = await client.post('/admin/users', data);
    return response.data;
  }

  async getUserDetails(userId: string): Promise<any> {
    const response = await client.get(`/admin/users/${userId}`);
    return response.data;
  }

  async updateUser(
    userId: string,
    data: {
      full_name?: string;
      role?: string;
      is_active?: boolean;
      is_verified?: boolean;
    }
  ): Promise<any> {
    const response = await client.put(`/admin/users/${userId}`, data);
    return response.data;
  }

  async deleteUser(userId: string): Promise<void> {
    await client.delete(`/admin/users/${userId}`);
  }

  async resetUserPassword(userId: string, newPassword: string): Promise<void> {
    // In the body: query strings are written to access logs.
    await client.post(`/admin/users/${userId}/reset-password`, { new_password: newPassword });
  }

  async getAllDocuments(params?: {
    skip?: number;
    limit?: number;
    doc_type?: string;
    status?: string;
    user_id?: string;
  }): Promise<{ total: number; documents: any[] }> {
    const response = await client.get('/admin/documents', { params });
    return response.data;
  }

  async getDocumentInfo(documentId: string): Promise<DocumentInfo> {
    const response = await client.get(`/documents/${documentId}/info`);
    return response.data;
  }

  async getDocumentChunks(documentId: string): Promise<ChunkData[]> {
    const response = await client.get(`/documents/${documentId}/chunks`);
    return response.data;
  }

  async getTextPreview(documentId: string, maxChars: number = 5000): Promise<any> {
    const response = await client.get(`/documents/${documentId}/preview/text`, {
      params: { max_chars: maxChars }
    });
    return response.data;
  }

  async downloadDocument(documentId: string): Promise<Blob> {
    const response = await client.get(`/documents/${documentId}/download`, {
      responseType: 'blob'
    });
    return response.data;
  }

  async editChunk(chunkId: string, newContent: string, metadata?: any): Promise<ChunkData> {
    const response = await client.put(`/chunks/${chunkId}/edit`, {
      chunk_id: chunkId,
      new_content: newContent,
      metadata: metadata
    });
    return response.data;
  }

  async batchEditChunks(edits: Array<{ chunk_id: string; new_content: string }>): Promise<any> {
    const response = await client.post('/chunks/batch-edit', { edits });
    return response.data;
  }

  async revertChunk(chunkId: string): Promise<void> {
    await client.post(`/chunks/${chunkId}/revert`);
  }

  async deleteChunk(chunkId: string): Promise<void> {
    await client.delete(`/chunks/${chunkId}`);
  }

  async getChunkHistory(chunkId: string, limit: number = 10): Promise<EditHistoryItem[]> {
    const response = await client.get(`/chunks/${chunkId}/history`, {
      params: { limit }
    });
    return response.data;
  }

  async getDocumentEditStats(documentId: string): Promise<DocumentEditStats> {
    const response = await client.get(`/documents/${documentId}/edit-stats`);
    return response.data;
  }

  // ============================================================================

  // CUSTOMIZATION API

  // ============================================================================

  async getCurrentCustomization(): Promise<Customization> {
    const response = await client.get('/customization/current');
    return response.data;
  }

  async getAdminCustomization(organizationName: string = 'default'): Promise<Customization> {
    const response = await client.get('/admin/customization', {
      params: { organization_name: organizationName }
    });
    return response.data;
  }

  async updateCustomization(
    data: CustomizationUpdateRequest,
    organizationName: string = 'default'
  ): Promise<Customization> {
    const response = await client.put('/admin/customization', data, {
      params: { organization_name: organizationName }
    });
    return response.data;
  }

  async uploadLogo(
    file: File,
    logoType: 'light' | 'dark' | 'favicon' = 'light',
    organizationName: string = 'default'
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await client.post('/admin/customization/logo', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      params: {
        organization_name: organizationName,
        logo_type: logoType
      }
    });
    return response.data;
  }

  async deleteLogo(
    logoType: 'light' | 'dark' | 'favicon' = 'light',
    organizationName: string = 'default'
  ): Promise<void> {
    await client.delete('/admin/customization/logo', {
      params: {
        logo_type: logoType,
        organization_name: organizationName
      }
    });
  }

  async resetCustomization(organizationName: string = 'default'): Promise<any> {
    const response = await client.post('/admin/customization/reset', null, {
      params: { organization_name: organizationName }
    });
    return response.data;
  }

  async generateChunkTitle(chunkId: string): Promise<any> {
    const response = await client.post(`/chunks/${chunkId}/generate-title`);
    return response.data;
  }

  async generateAllTitles(documentId: string): Promise<any> {
    const response = await client.post(`/documents/${documentId}/generate-all-titles`);
    return response.data;
  }

  async updateChunkTitle(chunkId: string, title: string): Promise<any> {
    const response = await client.put(`/chunks/${chunkId}/title`, null, {
      params: { title }
    });
    return response.data;
  }

  async getThemePresets(): Promise<ThemePreset[]> {
    const response = await client.get('/admin/customization/presets');
    return response.data;
  }

  async applyThemePreset(
    presetName: string,
    organizationName: string = 'default'
  ): Promise<any> {
    const response = await client.post('/admin/customization/apply-preset', null, {
      params: {
        preset_name: presetName,
        organization_name: organizationName
      }
    });
    return response.data;
  }

  async exportCustomization(organizationName: string = 'default'): Promise<Customization> {
    const response = await client.get('/admin/customization/export', {
      params: { organization_name: organizationName }
    });
    return response.data;
  }

  async validateColorContrast(
    backgroundColor: string,
    textColor: string
  ): Promise<{ ratio: number; passes_aa: boolean; passes_aaa: boolean }> {
    // Client-side WCAG contrast calculation
    const getLuminance = (color: string): number => {
      const hex = color.replace('#', '');
      const r = parseInt(hex.substr(0, 2), 16) / 255;
      const g = parseInt(hex.substr(2, 2), 16) / 255;
      const b = parseInt(hex.substr(4, 2), 16) / 255;
      
      const [rs, gs, bs] = [r, g, b].map(c => 
        c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
      );
      
      return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
    };

    const l1 = getLuminance(backgroundColor);
    const l2 = getLuminance(textColor);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    
    return {
      ratio: Math.round(ratio * 100) / 100,
      passes_aa: ratio >= 4.5,
      passes_aaa: ratio >= 7
    };
  }


  // ── Organization membership & administration ──────────────────────────────

  async getRegistrationMode(): Promise<RegistrationMode> {
    const response = await client.get<{ mode: RegistrationMode }>('/auth/registration-mode');
    return response.data.mode;
  }

  async previewInvitation(token: string): Promise<InvitationPreview> {
    const response = await client.get<InvitationPreview>(`/auth/invitations/${encodeURIComponent(token)}`);
    return response.data;
  }

  async acceptInvitation(data: { token: string; username: string; password: string; full_name?: string }) {
    const response = await client.post('/auth/invitations/accept', data);
    return response.data;
  }

  async listInvitations(status?: Invitation['status']): Promise<Invitation[]> {
    const response = await client.get<{ items: Invitation[] }>('/organization/invitations', {
      params: { status },
    });
    return response.data.items;
  }

  async createInvitation(email: string, role: InvitableRole = 'user'): Promise<CreatedInvitation> {
    const response = await client.post<CreatedInvitation>('/organization/invitations', { email, role });
    return response.data;
  }

  async revokeInvitation(invitationId: string): Promise<Invitation> {
    const response = await client.delete<Invitation>(`/organization/invitations/${invitationId}`);
    return response.data;
  }

  async resendInvitation(invitationId: string): Promise<CreatedInvitation> {
    const response = await client.post<CreatedInvitation>(`/organization/invitations/${invitationId}/resend`);
    return response.data;
  }

  async getOrganizationUsage(): Promise<OrganizationUsage> {
    const response = await client.get<OrganizationUsage>('/organization/usage');
    return response.data;
  }

  async getAuditLog(params: {
    action?: string;
    actor_user_id?: string;
    outcome?: 'success' | 'failure' | 'denied';
    since?: string;
    until?: string;
    limit?: number;
    cursor?: string | null;
  } = {}): Promise<{ items: AuditEvent[]; next_cursor: string | null }> {
    const response = await client.get('/organization/audit-log', {
      params: { ...params, cursor: params.cursor || undefined },
    });
    return response.data;
  }

  // ── Chat history ──────────────────────────────────────────────────────────

  async listConversations(options: {
    view?: ConversationListView;
    q?: string;
    cursor?: string | null;
    limit?: number;
  } = {}): Promise<ConversationPage> {
    const view = options.view ?? 'all';
    const response = await client.get<ConversationPage>('/chat/conversations', {
      params: {
        limit: options.limit ?? 30,
        cursor: options.cursor || undefined,
        q: options.q?.trim() || undefined,
        pinned: view === 'pinned' || undefined,
        archived: view === 'archived' || undefined,
        deleted: view === 'deleted' || undefined,
      },
    });
    return response.data;
  }

  /** Most recent conversations (first page), for menus and the command palette. */
  async getConversations(limit: number = 10): Promise<ConversationSummary[]> {
    return (await this.listConversations({ limit })).items;
  }

  async getConversationStats(): Promise<ConversationStats> {
    const response = await client.get<ConversationStats>('/chat/conversations/stats');
    return response.data;
  }

  async getConversation(
    conversationId: string,
    options: { before?: number; limit?: number } = {}
  ): Promise<ConversationDetail> {
    const response = await client.get<ConversationDetail>(`/chat/conversations/${conversationId}`, {
      params: { before: options.before, limit: options.limit },
    });
    return response.data;
  }

  async updateConversation(
    conversationId: string,
    patch: { title?: string; is_pinned?: boolean; is_archived?: boolean }
  ): Promise<ConversationSummary> {
    const response = await client.patch<ConversationSummary>(
      `/chat/conversations/${conversationId}`,
      patch
    );
    return response.data;
  }

  /** Soft delete; restorable for the retention window. */
  async deleteConversation(
    conversationId: string
  ): Promise<{ conversation_id: string; restorable_until: string | null }> {
    const response = await client.delete(`/chat/conversations/${conversationId}`);
    return response.data;
  }

  async bulkDeleteConversations(ids: string[]): Promise<{ deleted: number }> {
    const response = await client.post('/chat/conversations/bulk-delete', { ids });
    return response.data;
  }

  async restoreConversation(conversationId: string): Promise<ConversationSummary> {
    const response = await client.post<ConversationSummary>(
      `/chat/conversations/${conversationId}/restore`
    );
    return response.data;
  }

  /** Irreversible; only allowed for conversations already in Recently deleted. */
  async deleteConversationPermanently(conversationId: string): Promise<void> {
    await client.delete(`/chat/conversations/${conversationId}/permanent`);
  }

  async exportConversationFile(
    conversationId: string,
    format: 'markdown' | 'pdf' | 'json'
  ): Promise<{ blob: Blob; filename: string }> {
    const response = await client.get(`/chat/conversations/${conversationId}/export`, {
      params: { format },
      responseType: 'blob',
    });
    const extension = format === 'markdown' ? 'md' : format;
    return {
      blob: response.data as Blob,
      filename: downloadFilename(
        response.headers['content-disposition'],
        `conversation_${conversationId.slice(0, 8)}.${extension}`
      ),
    };
  }

  /** Download a conversation export straight to the user's machine. */
  async downloadConversation(conversationId: string, format: 'markdown' | 'pdf' | 'json'): Promise<void> {
    const { blob, filename } = await this.exportConversationFile(conversationId, format);
    saveBlob(blob, filename);
  }

  /** @deprecated use downloadConversation; kept for existing callers. */
  async exportConversation(conversationId: string, format: 'markdown' | 'pdf' | 'json' = 'markdown'): Promise<Blob> {
    return (await this.exportConversationFile(conversationId, format)).blob;
  }

  async exportConversationPDF(conversationId: string): Promise<Blob> {
    return this.exportConversation(conversationId, 'pdf');
  }
}

export const api = new APIService();
export default api;
