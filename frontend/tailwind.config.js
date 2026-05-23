/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#EEF3FB',
          100: '#D6E2F4',
          200: '#ADC4E9',
          300: '#7A9FD6',
          400: '#4A79C0',
          500: '#2D5499',
          600: '#1B3A6B',
          700: '#0F2347',
          800: '#081629',
          900: '#030A14',
        },
        secondary: {
          DEFAULT: '#C8982A',
          light: '#F0C96A',
          dark: '#A07820',
        },
        gold: {
          DEFAULT: '#D4A843',
          light: '#F0C96A',
          dark: '#C8982A',
        },
      },
      fontFamily: {
        sans: ['DM Sans', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['DM Serif Display', 'Georgia', 'serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        fadeIn: 'fadeIn 0.3s ease forwards',
        slideUp: 'slideUp 0.35s ease forwards',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        fadeIn: {
          from: { opacity: 0, transform: 'translateY(6px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
        slideUp: {
          from: { opacity: 0, transform: 'translateY(16px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
      },
      borderRadius: {
        'xl': '14px',
        '2xl': '18px',
      },
      boxShadow: {
        finance: '0 2px 12px rgba(27, 58, 107, 0.07)',
        'finance-hover': '0 8px 28px rgba(27, 58, 107, 0.14)',
        'finance-lg': '0 20px 60px rgba(27, 58, 107, 0.12)',
      },
    },
  },
  plugins: [],
}
