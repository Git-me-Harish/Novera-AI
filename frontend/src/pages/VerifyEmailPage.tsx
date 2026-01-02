import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Mail, CheckCircle, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { useCustomization } from '../contexts/CustomizationContext';
import api from '../services/api';
import { useAuth } from '../contexts/AuthContext';

export default function VerifyEmailPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const { customization, darkMode } = useCustomization();

  const [verifying, setVerifying] = useState(true);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resending, setResending] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);

  useEffect(() => {
    if (token) {
      verifyEmail();
    } else {
      setVerifying(false);
      setError('Invalid verification link. No token provided.');
    }
  }, [token]);

  const verifyEmail = async () => {
    if (!token) return;

    try {
      await api.verifyEmail(token);
      setVerified(true);
      setError(null);

      // Redirect to login after 3 seconds
      setTimeout(() => {
        navigate('/login', { 
          replace: true,
          state: { message: 'Email verified! You can now sign in.' }
        });
      }, 3000);
    } catch (err: any) {
      console.error('Verification error:', err);

      let errorMessage = 'Email verification failed. Please try again.';

      if (err.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        }
      }

      setError(errorMessage);
      setVerified(false);
    } finally {
      setVerifying(false);
    }
  };

  const handleResendVerification = async () => {
    setResending(true);
    setResendSuccess(false);
    setError(null);

    try {
      await api.resendVerificationEmail();
      setResendSuccess(true);
    } catch (err: any) {
      console.error('Resend verification error:', err);

      let errorMessage = 'Failed to resend verification email.';

      if (err.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        }
      }

      setError(errorMessage);
    } finally {
      setResending(false);
    }
  };

  // Verifying State
  if (verifying) {
    return (
      <div className={`min-h-screen flex items-center justify-center transition-colors duration-300 ${
        darkMode 
          ? 'bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900' 
          : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50'
      }`}>
        <div className="text-center">
          <Loader2 className="w-12 h-12 text-primary-600 animate-spin mx-auto mb-4" />
          <p className={`transition-colors ${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
            Verifying your email...
          </p>
        </div>
      </div>
    );
  }

  // Success State
  if (verified) {
    return (
      <div className={`min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8 transition-colors duration-300 ${
        darkMode 
          ? 'bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900' 
          : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50'
      }`}>
        <div className="max-w-md w-full">
          <div className="text-center mb-8">
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
                Email Verified!
              </h2>

              <p className={`mb-6 transition-colors ${
                darkMode ? 'text-gray-300' : 'text-gray-600'
              }`}>
                Your email has been successfully verified. You can now access all features of {customization?.branding?.app_name || 'Novera AI'}.
              </p>

              <div className={`border rounded-lg p-4 mb-6 transition-all ${
                darkMode 
                  ? 'bg-green-900/20 border-green-800' 
                  : 'bg-green-50 border-green-200'
              }`}>
                <p className={`text-sm ${
                  darkMode ? 'text-green-300' : 'text-green-800'
                }`}>
                  Redirecting to login page in 3 seconds...
                </p>
              </div>

              <Link
                to="/login"
                className="inline-flex items-center justify-center px-6 py-3 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-lg hover:from-primary-600 hover:to-primary-700 transition-all shadow-sm"
              >
                Sign In Now
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error State
  return (
    <div className={`min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8 transition-colors duration-300 ${
      darkMode 
        ? 'bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900' 
        : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50'
    }`}>
      <div className="max-w-md w-full">
        <div className="text-center mb-8">
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
              darkMode ? 'bg-red-900/30' : 'bg-red-100'
            }`}>
              <AlertCircle className={`h-10 w-10 ${
                darkMode ? 'text-red-400' : 'text-red-600'
              }`} />
            </div>

            <h2 className={`text-2xl font-bold mb-2 transition-colors ${
              darkMode ? 'text-white' : 'text-gray-900'
            }`}>
              Verification Failed
            </h2>

            <p className={`mb-6 transition-colors ${
              darkMode ? 'text-gray-300' : 'text-gray-600'
            }`}>
              {error}
            </p>

            {/* Resend Success Message */}
            {resendSuccess && (
              <div className={`border rounded-lg p-4 mb-6 transition-all ${
                darkMode 
                  ? 'bg-green-900/20 border-green-800' 
                  : 'bg-green-50 border-green-200'
              }`}>
                <div className="flex items-center gap-2 justify-center">
                  <CheckCircle className={`w-5 h-5 ${
                    darkMode ? 'text-green-400' : 'text-green-600'
                  }`} />
                  <p className={`text-sm ${
                    darkMode ? 'text-green-300' : 'text-green-800'
                  }`}>
                    Verification email sent! Please check your inbox.
                  </p>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="space-y-3">
              {/* Resend Verification Button (only if user is logged in and not verified) */}
              {user && !user.is_verified && (
                <button
                  onClick={handleResendVerification}
                  disabled={resending}
                  className="w-full flex items-center justify-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {resending ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-5 h-5 mr-2" />
                      Resend Verification Email
                    </>
                  )}
                </button>
              )}

              {/* Back to Login Button */}
              <Link
                to="/login"
                className={`block w-full px-4 py-2 border rounded-lg transition-all text-center ${
                  darkMode 
                    ? 'border-gray-600 text-gray-300 hover:bg-gray-700' 
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                Back to Login
              </Link>
            </div>
          </div>
        </div>

        {/* Help Text */}
        <div className="mt-6 text-center">
          <p className={`text-sm transition-colors ${
            darkMode ? 'text-gray-500' : 'text-gray-500'
          }`}>
            Need help?{' '}
            <a 
              href="mailto:support@novera.ai" 
              className="text-primary-600 hover:text-primary-500 transition-colors font-medium"
            >
              Contact Support
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
