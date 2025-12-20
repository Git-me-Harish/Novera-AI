import { useState } from 'react';
import { Mail, X, RefreshCw, Loader2, CheckCircle } from 'lucide-react';
import api from '../../services/api';

interface VerificationReminderProps {
  email: string;
  onClose: () => void;
}

export default function VerificationReminder({ email, onClose }: VerificationReminderProps) {
  const [resending, setResending] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleResend = async () => {
    setResending(true);
    setError(null);

    try {
      await api.resendVerificationEmail();
      setSuccess(true);
      
      setTimeout(() => {
        onClose();
      }, 3000);
    } catch (err: any) {
      console.error('Resend error:', err);
      
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

  if (success) {
    return (
      <div className="fixed bottom-4 right-4 max-w-md bg-white rounded-lg shadow-lg border border-green-200 p-4 animate-slide-up z-50">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">
            <CheckCircle className="w-6 h-6 text-green-600" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-gray-900 mb-1">
              Verification Email Sent!
            </h3>
            <p className="text-sm text-gray-600">
              Check your inbox at <strong>{email}</strong>
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 max-w-md bg-white rounded-lg shadow-lg border border-yellow-200 p-4 animate-slide-up z-50">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <Mail className="w-6 h-6 text-yellow-600" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">
            Verify Your Email
          </h3>
          <p className="text-sm text-gray-600 mb-3">
            Please check your inbox at <strong>{email}</strong> and click the verification link.
          </p>
          
          {error && (
            <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-800">
              {error}
            </div>
          )}
          
          <button
            onClick={handleResend}
            disabled={resending}
            className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center disabled:opacity-50"
          >
            {resending ? (
              <>
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                Sending...
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4 mr-1" />
                Resend verification email
              </>
            )}
          </button>
        </div>
        <button
          onClick={onClose}
          className="flex-shrink-0 text-gray-400 hover:text-gray-600"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}