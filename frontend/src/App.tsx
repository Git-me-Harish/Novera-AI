import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { BrandProvider } from './contexts/BrandContext';
import { ConversationProvider } from './contexts/ConversationContext';
import { ThemeProvider } from './contexts/ThemeContext';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import ToastContainer from './components/common/ToastContainer';
import { PageLoader } from './ui';

// Every page is its own chunk: the first load ships only what the route needs
// (the old single bundle was 719 KB).
const LoginPage = lazy(() => import('./pages/LoginPage'));
const RegisterPage = lazy(() => import('./pages/RegisterPage'));
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'));
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage'));
const AcceptInvitePage = lazy(() => import('./pages/AcceptInvitePage'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const ConversationsPage = lazy(() => import('./pages/ConversationsPage'));
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'));
const DocumentEditorPage = lazy(() => import('./pages/DocumentEditorPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const AdminOverviewPage = lazy(() => import('./pages/admin/AdminDashboard'));
const MembersPage = lazy(() => import('./pages/admin/UserManagement'));
const UsagePage = lazy(() => import('./pages/admin/UsagePage'));
const AuditLogPage = lazy(() => import('./pages/admin/AuditLogPage'));
const AISettingsPage = lazy(() => import('./pages/admin/AISettingsPage'));
const BrandingPage = lazy(() => import('./pages/admin/BrandingPage'));

const admin = (page: JSX.Element) => <ProtectedRoute adminOnly>{page}</ProtectedRoute>;

function AppRoutes() {
  return (
    <>
      <ToastContainer />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/accept-invite" element={<AcceptInvitePage />} />

          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Suspense fallback={<PageLoader />}>
                    <Routes>
                      <Route path="/" element={<Navigate to="/chat" replace />} />
                      <Route path="/chat" element={<ChatPage />} />
                      <Route path="/chat/:conversationId" element={<ChatPage />} />
                      <Route path="/conversations" element={<ConversationsPage />} />
                      <Route path="/documents" element={<DocumentsPage />} />
                      <Route path="/documents/:documentId/edit" element={<DocumentEditorPage />} />
                      <Route path="/profile" element={<ProfilePage />} />

                      <Route path="/admin" element={admin(<AdminOverviewPage />)} />
                      <Route path="/admin/members" element={admin(<MembersPage />)} />
                      <Route path="/admin/usage" element={admin(<UsagePage />)} />
                      <Route path="/admin/audit" element={admin(<AuditLogPage />)} />
                      <Route path="/admin/ai" element={admin(<AISettingsPage />)} />
                      <Route path="/admin/branding" element={admin(<BrandingPage />)} />
                      {/* Old bookmarks */}
                      <Route path="/admin/users" element={<Navigate to="/admin/members" replace />} />
                      <Route path="/admin/customization" element={<Navigate to="/admin/branding" replace />} />
                      <Route path="*" element={<Navigate to="/chat" replace />} />
                    </Routes>
                  </Suspense>
                </Layout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </Suspense>
    </>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrandProvider>
          <ConversationProvider>
            <AppRoutes />
          </ConversationProvider>
        </BrandProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
