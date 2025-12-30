import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { LogIn, Mail, Lock, AlertCircle, Loader2, Sun, Moon } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useCustomization } from '../contexts/CustomizationContext';
import VerificationReminder from '../components/auth/VerificationReminder';
import api from '../services/api';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const { darkMode, toggleDarkMode } = useCustomization();

  const [mounted, setMounted] = useState(false);
  const [formData, setFormData] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showVerificationReminder, setShowVerificationReminder] = useState(false);
  const [userEmail, setUserEmail] = useState('');

  const from = (location.state as any)?.from?.pathname || '/chat';

  // Apply global dark mode immediately to prevent flash
  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
    setMounted(true);
  }, [darkMode]);

  if (!mounted) return null;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(formData.email, formData.password);
      const currentUser = await api.getCurrentUser();

      if (!currentUser.is_verified) {
        setUserEmail(currentUser.email);
        setShowVerificationReminder(true);
      } else {
        navigate(from, { replace: true });
      }
    } catch (err: any) {
      let message = 'Login failed. Please check your credentials.';
      if (err.response?.data?.detail) {
        message =
          typeof err.response.data.detail === 'string'
            ? err.response.data.detail
            : err.response.data.detail.map((e: any) => e.msg).join(', ');
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4 py-12
        bg-gradient-to-br from-primary-50 via-white to-secondary-50
        dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 transition-colors duration-300"
    >
      <div className="max-w-md w-full space-y-8">

        {/* Header */}
        <div className="text-center">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center
              bg-gradient-to-br from-primary-500 to-secondary-500 shadow-lg">
              <span className="text-white font-bold text-2xl">M</span>
            </div>
          </div>

          <div className="flex justify-center items-center gap-2">
            <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
              Welcome back
            </h2>
            {/* Theme toggle */}
            <button
              type="button"
              onClick={toggleDarkMode}
              className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition"
            >
              {darkMode ? <Sun className="w-5 h-5 text-yellow-400" /> : <Moon className="w-5 h-5 text-gray-800" />}
            </button>
          </div>

          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            Sign in to your Novera account
          </p>
        </div>

        {/* Form */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8 transition-colors duration-300">
          <form onSubmit={handleSubmit} className="space-y-6">

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg
                bg-red-50 dark:bg-red-900/30
                border border-red-200 dark:border-red-700 transition-colors duration-300">
                <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}

            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Email address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
                <input
                  name="email"
                  type="email"
                  required
                  value={formData.email}
                  onChange={handleChange}
                  disabled={loading}
                  className="w-full pl-10 pr-3 py-2 rounded-lg
                    bg-white dark:bg-gray-700
                    text-gray-900 dark:text-gray-100
                    border border-gray-300 dark:border-gray-600
                    focus:ring-2 focus:ring-primary-500
                    transition-colors duration-300"
                  placeholder="you@example.com"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
                <input
                  name="password"
                  type="password"
                  required
                  value={formData.password}
                  onChange={handleChange}
                  disabled={loading}
                  className="w-full pl-10 pr-3 py-2 rounded-lg
                    bg-white dark:bg-gray-700
                    text-gray-900 dark:text-gray-100
                    border border-gray-300 dark:border-gray-600
                    focus:ring-2 focus:ring-primary-500
                    transition-colors duration-300"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {/* Remember / Forgot */}
            <div className="flex justify-between items-center text-sm">
              <label className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                <input type="checkbox" className="rounded border-gray-300 dark:border-gray-600" />
                Remember me
              </label>

              <Link to="/forgot-password" className="text-primary-600 dark:text-primary-400">
                Forgot password?
              </Link>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-lg
                bg-gradient-to-r from-primary-500 to-primary-600
                text-white font-medium shadow
                hover:from-primary-600 hover:to-primary-700
                disabled:opacity-50
                transition-colors duration-300"
            >
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <LogIn className="w-5 h-5" />}
              Sign in
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-300">
            Don’t have an account?{' '}
            <Link to="/register" className="text-primary-600 dark:text-primary-400 font-medium">
              Sign up now
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-gray-500 dark:text-gray-400">
          By signing in, you agree to our Terms & Privacy Policy
        </p>
      </div>

      {showVerificationReminder && (
        <VerificationReminder
          email={userEmail}
          onClose={() => navigate(from, { replace: true })}
        />
      )}
    </div>
  );
}
