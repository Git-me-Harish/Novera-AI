import { useState, useEffect } from 'react';
import { Users, FileText, HardDrive, Activity, TrendingUp, Shield } from 'lucide-react';
import api, { SystemStats, UserStats } from '../../services/api';

export default function AdminDashboard() {
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null);
  const [userStats, setUserStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const [system, users] = await Promise.all([
        api.getSystemStats(),
        api.getUserStats(),
      ]);
      setSystemStats(system);
      setUserStats(users);
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-8 h-8 text-primary-600" />
            <h1 className="text-3xl font-bold text-gray-900">Admin Dashboard</h1>
          </div>
          <p className="text-gray-600">System overview and analytics</p>
        </div>

        {/* System Stats */}
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">System Statistics</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              icon={Users}
              label="Total Users"
              value={systemStats?.total_users || 0}
              color="blue"
            />
            <StatCard
              icon={FileText}
              label="Total Documents"
              value={systemStats?.total_documents || 0}
              color="green"
            />
            <StatCard
              icon={Activity}
              label="Total Chunks"
              value={systemStats?.total_chunks || 0}
              color="purple"
            />
            <StatCard
              icon={HardDrive}
              label="Storage Used"
              value={`${systemStats?.storage_used_mb.toFixed(2) || 0} MB`}
              color="orange"
            />
          </div>
        </div>

        {/* User Stats */}
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">User Analytics</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              icon={Users}
              label="Active Users"
              value={userStats?.active_users || 0}
              color="green"
              subtitle={`${userStats?.total_users || 0} total`}
            />
            <StatCard
              icon={Shield}
              label="Admin Users"
              value={userStats?.admin_users || 0}
              color="red"
            />
            <StatCard
              icon={Users}
              label="Regular Users"
              value={userStats?.regular_users || 0}
              color="blue"
            />
            <StatCard
              icon={TrendingUp}
              label="Verified Users"
              value={userStats?.verified_users || 0}
              color="purple"
            />
          </div>
        </div>

        {/* Quick Actions */}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <QuickActionCard
              title="User Management"
              description="Manage users, roles, and permissions"
              link="/admin/users"
              icon={Users}
            />
            <QuickActionCard
              title="View All Documents"
              description="Browse and manage all documents"
              link="/documents"
              icon={FileText}
            />
            <QuickActionCard
              title="System Settings"
              description="Configure system settings"
              link="/admin/settings"
              icon={Activity}
              disabled
            />
          </div>
        </div>
      </div>
    </div>
  );
}

interface StatCardProps {
  icon: any;
  label: string;
  value: string | number;
  color: 'blue' | 'green' | 'purple' | 'orange' | 'red';
  subtitle?: string;
}

function StatCard({ icon: Icon, label, value, color, subtitle }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    purple: 'bg-purple-50 text-purple-600',
    orange: 'bg-orange-50 text-orange-600',
    red: 'bg-red-50 text-red-600',
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
      <h3 className="text-2xl font-bold text-gray-900 mb-1">{value}</h3>
      <p className="text-sm text-gray-600">{label}</p>
      {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
    </div>
  );
}

interface QuickActionCardProps {
  title: string;
  description: string;
  link: string;
  icon: any;
  disabled?: boolean;
}

function QuickActionCard({ title, description, link, icon: Icon, disabled }: QuickActionCardProps) {
  return (
    <a
      href={disabled ? '#' : link}
      className={`block bg-white rounded-lg border border-gray-200 p-6 transition-all ${
        disabled
          ? 'opacity-50 cursor-not-allowed'
          : 'hover:shadow-md hover:border-primary-300'
      }`}
      onClick={(e) => disabled && e.preventDefault()}
    >
      <div className="flex items-start space-x-4">
        <div className="p-2 bg-primary-50 rounded-lg">
          <Icon className="w-6 h-6 text-primary-600" />
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900 mb-1">{title}</h3>
          <p className="text-sm text-gray-600">{description}</p>
          {disabled && (
            <span className="inline-block mt-2 text-xs text-gray-500">Coming soon</span>
          )}
        </div>
      </div>
    </a>
  );
}