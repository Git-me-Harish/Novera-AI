import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  UserPlus,
  Mail,
  Lock,
  User,
  AlertCircle,
  Loader2,
  CheckCircle,
  X,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useCustomization } from '../contexts/CustomizationContext';

export default function RegisterPage() {
  const { register } = useAuth();
  const { darkMode } = useCustomization(); // <-- Use global dark mode

  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    confirmPassword: '',
    fullName: '',
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registrationSuccess, setRegistrationSuccess] = useState(false);

  /* ----------------------------------------
     PASSWORD VALIDATION
  ---------------------------------------- */
  const validatePassword = (password: string) => {
    if (password.length < 8)
      return { isValid: false, message: 'Password must be at least 8 characters' };
    if (!/[A-Z]/.test(password))
      return { isValid: false, message: 'Password must contain an uppercase letter' };
    if (!/[a-z]/.test(password))
      return { isValid: false, message: 'Password must contain a lowercase letter' };
    if (!/[0-9]/.test(password))
      return { isValid: false, message: 'Password must contain a number' };
    if (!/[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(password))
      return { isValid: false, message: 'Password must contain a special character' };

    return { isValid: true, message: '' };
  };

  const passwordStrength = formData.password
    ? validatePassword(formData.password)
    : null;

  /* ----------------------------------------
     HANDLERS
  ---------------------------------------- */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (!passwordStrength?.isValid) {
      setError(passwordStrength?.message || 'Invalid password');
      return;
    }

    setLoading(true);

    try {
      await register(
        formData.email,
        formData.username,
        formData.password,
        formData.fullName || undefined
      );
      setRegistrationSuccess(true);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          'Registration failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  /* ----------------------------------------
     SUCCESS SCREEN
  ---------------------------------------- */
  if (registrationSuccess) {
    return (
      <div className={`min-h-screen flex items-center justify-center
        ${darkMode ? 'bg-gray-900' : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50'} px-4`}
      >
        <div className={`max-w-md w-full ${darkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl shadow-lg p-8 text-center`}>
          <CheckCircle className="mx-auto h-14 w-14 text-green-500 mb-4" />
          <h2 className={`text-2xl font-bold ${darkMode ? 'text-gray-100' : 'text-gray-900'}`}>
            Registration Successful!
          </h2>
          <p className={`mt-2 ${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
            Verify your email to continue.
          </p>

          <Link
            to="/login"
            className="inline-block mt-6 px-6 py-3 rounded-lg
              bg-gradient-to-r from-primary-500 to-primary-600
              text-white font-medium"
          >
            Go to Sign In
          </Link>
        </div>
      </div>
    );
  }

  /* ----------------------------------------
     MAIN FORM
  ---------------------------------------- */
  return (
    <div className={`min-h-screen flex items-center justify-center
      ${darkMode ? 'bg-gray-900' : 'bg-gradient-to-br from-primary-50 via-white to-secondary-50'} px-4`}
    >
      <div className="w-full max-w-md space-y-8">
        {/* Header */}
        <div className="text-center">
          <div className={`mx-auto mb-6 w-16 h-16 rounded-2xl
            bg-gradient-to-br from-primary-500 to-secondary-500
            flex items-center justify-center shadow-lg`}
          >
            <span className="text-white text-2xl font-bold">M</span>
          </div>

          <h2 className={`text-3xl font-bold ${darkMode ? 'text-gray-100' : 'text-gray-900'}`}>
            Create your account
          </h2>
          <p className={`${darkMode ? 'text-gray-300' : 'text-gray-600'} mt-2`}>
            Start using Novera AI
          </p>
        </div>

        {/* Form */}
        <div className={`${darkMode ? 'bg-gray-800' : 'bg-white'} rounded-xl shadow-lg p-8`}>
          <form onSubmit={handleSubmit} className="space-y-5">

            {error && (
              <div className={`flex gap-2 p-3 rounded-lg
                ${darkMode ? 'bg-red-900/30 border-red-700' : 'bg-red-50 border-red-200'}`}
              >
                <AlertCircle className={`w-5 h-5 ${darkMode ? 'text-red-400' : 'text-red-600'}`} />
                <p className={`text-sm ${darkMode ? 'text-red-300' : 'text-red-700'}`}>{error}</p>
              </div>
            )}

            <Input icon={Mail} label="Email" name="email" value={formData.email} onChange={handleChange} darkMode={darkMode} />
            <Input icon={User} label="Username" name="username" value={formData.username} onChange={handleChange} darkMode={darkMode} />
            <Input label="Full name (optional)" name="fullName" value={formData.fullName} onChange={handleChange} darkMode={darkMode} />
            <Input icon={Lock} label="Password" type="password" name="password" value={formData.password} onChange={handleChange} darkMode={darkMode} />
            <Input icon={Lock} label="Confirm Password" type="password" name="confirmPassword" value={formData.confirmPassword} onChange={handleChange} darkMode={darkMode} />

            {formData.password && (
              <div className="space-y-1">
                <PasswordRequirement met={formData.password.length >= 8} text="At least 8 characters" />
                <PasswordRequirement met={/[A-Z]/.test(formData.password)} text="One uppercase letter" />
                <PasswordRequirement met={/[a-z]/.test(formData.password)} text="One lowercase letter" />
                <PasswordRequirement met={/[0-9]/.test(formData.password)} text="One number" />
                <PasswordRequirement met={/[!@#$%^&*]/.test(formData.password)} text="One special character" />
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !passwordStrength?.isValid}
              className="w-full flex justify-center items-center gap-2 py-3 rounded-lg
                bg-gradient-to-r from-primary-500 to-primary-600
                text-white font-medium disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <UserPlus className="w-5 h-5" />}
              Create account
            </button>
          </form>

          <p className={`mt-6 text-center text-sm ${darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
            Already have an account?{' '}
            <Link to="/login" className="text-primary-600 dark:text-primary-400 font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
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
        {Icon && <Icon className="absolute left-3 top-2.5 w-5 h-5 text-gray-400" />}
        <input
          {...props}
          className={`w-full py-2 pl-10 rounded-lg
            ${darkMode ? 'bg-gray-700 text-gray-100 border-gray-600' : 'bg-white text-gray-900 border-gray-300'}
            focus:ring-2 focus:ring-primary-500`}
        />
      </div>
    </div>
  );
}

function PasswordRequirement({ met, text }: { met: boolean; text: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {met ? <CheckCircle className="w-4 h-4 text-green-500" /> : <X className="w-4 h-4 text-gray-400" />}
      <span className={met ? 'text-green-600' : 'text-gray-500'}>{text}</span>
    </div>
  );
}
