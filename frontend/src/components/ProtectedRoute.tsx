import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { EmptyState, PageLoader } from '../ui';
import { ShieldAlert } from 'lucide-react';

export default function ProtectedRoute({ children, adminOnly = false }: { children: ReactNode; adminOnly?: boolean }) {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  const location = useLocation();

  if (loading) return <PageLoader />;
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  if (adminOnly && !isAdmin) {
    return (
      <div className="mx-auto max-w-xl px-4 py-section">
        <EmptyState icon={<ShieldAlert className="h-8 w-8" />} title="Administrators only">
          This page is available to your organization's administrators.
        </EmptyState>
      </div>
    );
  }
  return <>{children}</>;
}
