import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail, ArrowLeft, Send, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useCustomization } from '../contexts/CustomizationContext';
import api from '../services/api';

export default function ForgotPasswordPage() {
  const { customization, darkMode } = useCustomization();

  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await api.forgotPassword(email);
      setSuccess(true);
    } catch (err: any) {
      console.error('Forgot password error:', err);

      let errorMessage = 'Failed to send reset email. Please try again.';

      if (err.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        } else if (Array.isArray(err.response.data.detail)) {
          errorMessage = err.response.data.detail
            .map((e: any) => `${e.loc?.join('.')}: ${e.msg}`)
            .join(', ');
        }
      } else if (err.message) {
        errorMessage = err.message;
      }

      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // Success Screen
  if (success) {
    return (
      <div className={`min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8 transition-colors duration-300 ${
        darkMode 
          ? 'bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900' 
          : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50'
      }`}>
        <div className="max-w-md w-full">
          <div className="text-center mb-8">
            <Link 
              to="/login" 
              className={`inline-flex items-center text-sm mb-6 transition-colors ${
                darkMode 
                  ? 'text-gray-400 hover:text-white' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Login
            </Link>
            <div className="flex justify-center mb-6">
              <div className="w-16 h-16 bg-gradient-to-br from-primary-500 to-secondary-500 rounded-2xl flex items-center justify-center shadow-lg">
                <span className="text-white font-bold text-2xl">
                  {customization?.branding?.app_name?.charAt(0) || 'N'}
                </span>
              </div>
            </div>
          </div>

          <div className={`rounded-xl shadow-lg p-8 transition-all duration-300 ${
            darkMode 
              ? 'bg-gray-800 border border-gray-700' 
              : 'bg-white'
          }`}>
            <div className="text-center">
              <div className={`mx-auto flex items-center justify-center h-16 w-16 rounded-full mb-4 ${
                darkMode ? 'bg-green-900/30' : 'bg-green-100'
              }`}>
                <CheckCircle className={`h-10 w-10 ${
                  darkMode ? 'text-green-400' : 'text-green-600'
                }`} />
              </div>

              <h2 className={`text-2xl font-bold mb-2 transition-colors ${
                darkMode ? 'text-white' : 'text-gray-900'
              }`}>
                Check Your Email
              </h2>

              <p className={`mb-6 transition-colors ${
                darkMode ? 'text-gray-300' : 'text-gray-600'
              }`}>
                We've sent password reset instructions to:
              </p>

              <div className={`rounded-lg p-4 mb-6 transition-colors ${
                darkMode ? 'bg-gray-700' : 'bg-gray-50'
              }`}>
                <p className="text-primary-600 font-medium break-all">{email}</p>
              </div>

              <div className={`border rounded-lg p-4 mb-6 text-left transition-all ${
                darkMode 
                  ? 'bg-blue-900/20 border-blue-800' 
                  : 'bg-blue-50 border-blue-200'
              }`}>
                <p className={`text-sm mb-2 ${
                  darkMode ? 'text-blue-300' : 'text-blue-800'
                }`}>
                  <strong>What's next?</strong>
                </p>
                <ul className={`text-sm space-y-1 list-disc list-inside ${
                  darkMode ? 'text-blue-300' : 'text-blue-700'
                }`}>
                  <li>Check your email inbox (and spam folder)</li>
                  <li>Click the reset link in the email</li>
                  <li>The link expires in 15 minutes</li>
                </ul>
              </div>

              <button
                onClick={() => {
                  setSuccess(false);
                  setEmail('');
                }}
                className="text-sm text-primary-600 hover:text-primary-500 font-medium transition-colors"
              >
                Didn't receive the email? Try again
              </button>
            </div>
          </div>

          <div className="mt-6 text-center">
            <Link
              to="/login"
              className={`text-sm font-medium transition-colors ${
                darkMode 
                  ? 'text-gray-400 hover:text-white' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Return to login
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Form Screen
  return (
    <div className={`min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8 transition-colors duration-300 ${
      darkMode 
        ? 'bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900' 
        : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50'
    }`}>
      <div className="max-w-md w-full">
        <div className="text-center mb-8">
          <Link 
            to="/login" 
            className={`inline-flex items-center text-sm mb-6 transition-colors ${
              darkMode 
                ? 'text-gray-400 hover:text-white' 
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Login
          </Link>
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 bg-gradient-to-br from-primary-500 to-secondary-500 rounded-2xl flex items-center justify-center shadow-lg">
              <span className="text-white font-bold text-2xl">
                {customization?.branding?.app_name?.charAt(0) || 'N'}
              </span>
            </div>
          </div>
          <h2 className={`text-3xl font-bold transition-colors ${
            darkMode ? 'text-white' : 'text-gray-900'
          }`}>
            Forgot Password?
          </h2>
          <p className={`mt-2 text-sm transition-colors ${
            darkMode ? 'text-gray-400' : 'text-gray-600'
          }`}>
            No worries! Enter your email and we'll send you reset instructions.
          </p>
        </div>

        <div className={`rounded-xl shadow-lg p-8 transition-all duration-300 ${
          darkMode 
            ? 'bg-gray-800 border border-gray-700' 
            : 'bg-white'
        }`}>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Error Message */}
            {error && (
              <div className={`flex items-center gap-2 p-3 rounded-lg transition-colors ${
                darkMode 
                  ? 'bg-red-900/30 border border-red-800' 
                  : 'bg-red-50 border border-red-200'
              }`}>
                <AlertCircle className={`w-5 h-5 flex-shrink-0 ${
                  darkMode ? 'text-red-400' : 'text-red-600'
                }`} />
                <p className={`text-sm ${darkMode ? 'text-red-300' : 'text-red-800'}`}>
                  {error}
                </p>
              </div>
            )}

            {/* Email Input */}
            <div>
              <label 
                htmlFor="email" 
                className={`block text-sm font-medium mb-1 transition-colors ${
                  darkMode ? 'text-gray-300' : 'text-gray-700'
                }`}
              >
                Email address
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className={`h-5 w-5 transition-colors ${
                    darkMode ? 'text-gray-500' : 'text-gray-400'
                  }`} />
                </div>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={`block w-full pl-10 pr-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all ${
                    darkMode 
                      ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400 focus:bg-gray-600' 
                      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
                  }`}
                  placeholder="you@example.com"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading || !email}
              className="w-full flex items-center justify-center px-4 py-3 border border-transparent text-base font-medium rounded-lg text-white bg-gradient-to-r from-primary-500 to-primary-600 hover:from-primary-600 hover:to-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Sending...
                </>
              ) : (
                <>
                  <Send className="w-5 h-5 mr-2" />
                  Send Reset Link
                </>
              )}
            </button>
          </form>

          {/* Security Notice */}
          <div className="mt-6">
            <div className={`rounded-lg p-4 transition-colors ${
              darkMode ? 'bg-gray-700' : 'bg-gray-50'
            }`}>
              <p className={`text-xs ${darkMode ? 'text-gray-400' : 'text-gray-600'}`}>
                <strong>Security tip:</strong> For your protection, we'll send reset instructions only if this email is registered with us.
              </p>
            </div>
          </div>
        </div>

        {/* Footer Links */}
        <div className="mt-6 text-center">
          <p className={`text-sm transition-colors ${
            darkMode ? 'text-gray-400' : 'text-gray-600'
          }`}>
            Remember your password?{' '}
            <Link
              to="/login"
              className="font-medium text-primary-600 hover:text-primary-500 transition-colors"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
