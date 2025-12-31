import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { LogIn, Mail, Lock, AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useCustomization } from '../contexts/CustomizationContext';
import VerificationReminder from '../components/auth/VerificationReminder';
import api from '../services/api';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const { darkMode } = useCustomization();

  const [formData, setFormData] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showVerificationReminder, setShowVerificationReminder] = useState(false);
  const [userEmail, setUserEmail] = useState('');

  const from = (location.state as any)?.from?.pathname || '/chat';

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({ ...prev, [e.target.name]: e.target.value }));
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
      className={`min-h-screen flex items-center justify-center px-4 py-12
        ${darkMode ? 'bg-gray-900 text-gray-100' : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50 text-gray-900'}`}
    >
      <div className="w-full max-w-md space-y-8">
        {/* Header */}
        <div className="text-center">
          <div
            className="mx-auto mb-6 w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-secondary-500 flex items-center justify-center shadow-lg"
          >
            <span className="text-white text-2xl font-bold">M</span>
          </div>

          <h2 className={`text-3xl font-bold ${darkMode ? 'text-gray-100' : 'text-gray-900'}`}>
            Welcome back
          </h2>
          <p className={`${darkMode ? 'text-gray-300' : 'text-gray-600'} mt-2`}>
            Sign in to your account
          </p>
        </div>

        {/* Form Card */}
        <div className={`${darkMode ? 'bg-gray-800 border-gray-600' : 'bg-white border-gray-200'} rounded-xl shadow-lg p-8 border`}>
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className={`flex gap-2 p-3 rounded-lg
                ${darkMode ? 'bg-red-900/30 border-red-700' : 'bg-red-50 border-red-200'}`}>
                <AlertCircle className={`w-5 h-5 ${darkMode ? 'text-red-400' : 'text-red-600'}`} />
                <p className={`text-sm ${darkMode ? 'text-red-300' : 'text-red-700'}`}>{error}</p>
              </div>
            )}

            <Input icon={Mail} label="Email" name="email" value={formData.email} onChange={handleChange} darkMode={darkMode} />
            <Input icon={Lock} label="Password" type="password" name="password" value={formData.password} onChange={handleChange} darkMode={darkMode} />

            {/* Remember Me + Forgot Password */}
            <div className="flex justify-between items-center text-sm">
              <label className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                <input type="checkbox" className="rounded border-gray-300 dark:border-gray-600" />
                Remember me
              </label>

              <Link to="/forgot-password" className="text-primary-600 dark:text-primary-400">
                Forgot password?
              </Link>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center items-center gap-2 py-3 rounded-lg
                bg-gradient-to-r from-primary-500 to-primary-600
                text-white font-medium disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <LogIn className="w-5 h-5" />}
              Sign in
            </button>
          </form>

          <p className={`mt-6 text-center text-sm ${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
            Don’t have an account?{' '}
            <Link to="/register" className="text-primary-600 dark:text-primary-400 font-medium">
              Sign up now
            </Link>
          </p>
        </div>
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

/* ----------------------------------------
   REUSABLE INPUT
---------------------------------------- */
function Input({ icon: Icon, label, darkMode, ...props }: any) {
  return (
    <div>
      <label className={`block text-sm font-medium mb-1 ${darkMode ? 'text-gray-300' : 'text-gray-700'}`}>
        {label}
      </label>
      <div className="relative">
        {Icon && <Icon className={`absolute left-3 top-2.5 w-5 h-5 ${darkMode ? 'text-gray-400' : 'text-gray-400'}`} />}
        <input
          {...props}
          className={`w-full py-2 pl-10 rounded-lg border
            ${darkMode ? 'bg-gray-700 text-gray-100 border-gray-600' : 'bg-white text-gray-900 border-gray-300'}
            focus:ring-2 focus:ring-primary-500`}
        />
      </div>
    </div>
  );
}
