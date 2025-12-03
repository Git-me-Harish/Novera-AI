/**
 * API Service for communicating with the backend
 */
import axios, { AxiosInstance } from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_VERSION = '/api/v1';

// Types
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  metadata?: any;
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
  metadata: any;
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

export interface Conversation {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
  metadata: any;
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

class ApiService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: `${API_BASE_URL}${API_VERSION}`,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 60000, // 60 seconds
    });

    // Request interceptor for adding auth tokens
    this.api.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor for error handling and token refresh
    this.api.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;

        // If 401 and we haven't tried to refresh yet
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;

          try {
            const refreshToken = localStorage.getItem('refresh_token');
            if (refreshToken) {
              const response = await axios.post(
                `${API_BASE_URL}${API_VERSION}/auth/refresh`,
                { refresh_token: refreshToken }
              );

              const { access_token } = response.data;
              localStorage.setItem('access_token', access_token);

              // Retry original request with new token
              originalRequest.headers.Authorization = `Bearer ${access_token}`;
              return this.api(originalRequest);
            }
          } catch (refreshError) {
            // Refresh failed, clear tokens and redirect to login
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/login';
            return Promise.reject(refreshError);
          }
        }

        console.error('API Error:', error.response?.data || error.message);
        return Promise.reject(error);
      }
    );
  }

  // Health check
  async healthCheck() {
    const response = await this.api.get('/health');
    return response.data;
  }

  // Chat endpoints
  async sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
    const response = await this.api.post('/chat', request);
    return response.data;
  }

  async getConversations(limit: number = 10): Promise<Conversation[]> {
    const response = await this.api.get('/chat/conversations', {
      params: { limit },
    });
    return response.data;
  }

  async getConversation(conversationId: string): Promise<Conversation> {
    const response = await this.api.get(`/chat/conversations/${conversationId}`);
    return response.data;
  }

  async deleteConversation(conversationId: string): Promise<void> {
    await this.api.delete(`/chat/conversations/${conversationId}`);
  }

  // Document endpoints
  async uploadDocument(
    file: File,
    docType: string,
    department?: string
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    const params: any = { doc_type: docType };
    if (department) params.department = department;

    const response = await this.api.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
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
    const response = await this.api.get('/documents', { params });
    return response.data;
  }

  async getDocumentStatus(documentId: string): Promise<any> {
    const response = await this.api.get(`/documents/${documentId}/status`);
    return response.data;
  }

  async deleteDocument(documentId: string): Promise<void> {
    await this.api.delete(`/documents/${documentId}`);
  }

  // Search endpoints
  async search(query: string, topK: number = 5, docType?: string) {
    const response = await this.api.post('/search', null, {
      params: { query, top_k: topK, doc_type: docType },
    });
    return response.data;
  }

  // Authentication endpoints
  async register(
    email: string,
    username: string,
    password: string,
    fullName?: string
  ): Promise<any> {
    const response = await this.api.post('/auth/register', {
      email,
      username,
      password,
      full_name: fullName,
    });
    return response.data;
  }

  async login(email: string, password: string): Promise<any> {
    const response = await this.api.post('/auth/login', {
      email,
      password,
    });
    return response.data;
  }

  async logout(refreshToken: string): Promise<void> {
    await this.api.post('/auth/logout', {
      refresh_token: refreshToken,
    });
  }

  async getCurrentUser(): Promise<any> {
    const response = await this.api.get('/auth/me');
    return response.data;
  }

  async updateProfile(data: {
    full_name?: string;
    avatar_url?: string;
    preferences?: Record<string, any>;
    metadata?: Record<string, any>;
  }): Promise<any> {
    const response = await this.api.put('/auth/profile', data);
    return response.data;
  }

  async changePassword(
    currentPassword: string,
    newPassword: string
  ): Promise<void> {
    await this.api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  // Admin endpoints
  async getUsers(params?: {
    skip?: number;
    limit?: number;
    role?: string;
    is_active?: boolean;
    search?: string;
  }): Promise<{ total: number; users: AdminUser[] }> {
    const response = await this.api.get('/admin/users', { params });
    return response.data;
  }

  async getUserStats(): Promise<UserStats> {
    const response = await this.api.get('/admin/users/stats');
    return response.data;
  }

  async getSystemStats(): Promise<SystemStats> {
    const response = await this.api.get('/admin/stats');
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
    const response = await this.api.post('/admin/users', data);
    return response.data;
  }

  async getUserDetails(userId: string): Promise<any> {
    const response = await this.api.get(`/admin/users/${userId}`);
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
    const response = await this.api.put(`/admin/users/${userId}`, data);
    return response.data;
  }

  async deleteUser(userId: string): Promise<void> {
    await this.api.delete(`/admin/users/${userId}`);
  }

  async resetUserPassword(userId: string, newPassword: string): Promise<void> {
    await this.api.post(`/admin/users/${userId}/reset-password`, null, {
      params: { new_password: newPassword },
    });
  }

  async getAllDocuments(params?: {
    skip?: number;
    limit?: number;
    doc_type?: string;
    status?: string;
    user_id?: string;
  }): Promise<{ total: number; documents: any[] }> {
    const response = await this.api.get('/admin/documents', { params });
    return response.data;
  }
}

// Export singleton instance
export const api = new ApiService();
export default api;