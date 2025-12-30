import { useState, useEffect } from 'react';
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

export default function RegisterPage() {
  const { register } = useAuth();

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
  const [themeReady, setThemeReady] = useState(false);

  /* ----------------------------------------
     APPLY DARK MODE BEFORE FIRST PAINT
  ---------------------------------------- */
  useEffect(() => {
    const storedTheme = localStorage.getItem('theme');
    const prefersDark =
      storedTheme === 'dark' ||
      (!storedTheme &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);

    if (prefersDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }

    setThemeReady(true);
  }, []);

  if (!themeReady) return null;

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
      <div className="min-h-screen flex items-center justify-center
        bg-gradient-to-br from-primary-50 via-white to-secondary-50
        dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 px-4"
      >
        <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8 text-center">
          <CheckCircle className="mx-auto h-14 w-14 text-green-500 mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Registration Successful!
          </h2>
          <p className="text-gray-600 dark:text-gray-300 mt-2">
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
    <div className="min-h-screen flex items-center justify-center
      bg-gradient-to-br from-primary-50 via-white to-secondary-50
      dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 px-4"
    >
      <div className="w-full max-w-md space-y-8">

        {/* Header */}
        <div className="text-center">
          <div className="mx-auto mb-6 w-16 h-16 rounded-2xl
            bg-gradient-to-br from-primary-500 to-secondary-500
            flex items-center justify-center shadow-lg"
          >
            <span className="text-white text-2xl font-bold">M</span>
          </div>

          <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            Create your account
          </h2>
          <p className="text-gray-600 dark:text-gray-300 mt-2">
            Start using Novera AI
          </p>
        </div>

        {/* Form */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8">
          <form onSubmit={handleSubmit} className="space-y-5">

            {error && (
              <div className="flex gap-2 p-3 rounded-lg
                bg-red-50 dark:bg-red-900/30
                border border-red-200 dark:border-red-700"
              >
                <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}

            <Input icon={Mail} label="Email" name="email" value={formData.email} onChange={handleChange} />
            <Input icon={User} label="Username" name="username" value={formData.username} onChange={handleChange} />
            <Input label="Full name (optional)" name="fullName" value={formData.fullName} onChange={handleChange} />
            <Input icon={Lock} label="Password" type="password" name="password" value={formData.password} onChange={handleChange} />
            <Input icon={Lock} label="Confirm Password" type="password" name="confirmPassword" value={formData.confirmPassword} onChange={handleChange} />

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

          <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-300">
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
function Input({ icon: Icon, label, ...props }: any) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        {label}
      </label>
      <div className="relative">
        {Icon && <Icon className="absolute left-3 top-2.5 w-5 h-5 text-gray-400" />}
        <input
          {...props}
          className="w-full py-2 pl-10 rounded-lg
            bg-white dark:bg-gray-700
            text-gray-900 dark:text-gray-100
            border border-gray-300 dark:border-gray-600
            focus:ring-2 focus:ring-primary-500"
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
