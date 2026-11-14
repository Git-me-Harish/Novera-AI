/** @type {import('tailwindcss').Config} */

// Semantic colours backed by CSS variables (src/styles/tokens.css). The default
// palette is replaced, not extended: off-system colours such as bg-blue-500
// generate nothing, so stray colours are easy to spot in review.
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      inherit: 'inherit',
      canvas: {
        DEFAULT: token('canvas'),
        soft: token('canvas-soft'),
        tint: token('canvas-tint'),
        warm: token('canvas-warm'),
      },
      hairline: token('hairline'),
      divider: token('divider'),
      'field-border': token('field-border'),
      'ink-deep': token('ink-deep'),
      ink: { DEFAULT: token('ink'), muted: token('ink-muted') },
      link: token('link'),
      primary: { DEFAULT: token('primary'), pressed: token('primary-pressed') },
      'on-primary': token('on-primary'),
      brand: token('brand-mark'),
      gold: { DEFAULT: token('accent-gold'), soft: token('accent-gold-soft') },
      focus: token('focus'),
      error: token('error'),
      success: token('success'),
      warning: token('warning'),
      disabled: token('disabled-ink'),
      band: { teal: token('band-teal'), forest: token('band-forest') },
      highlight: token('highlight'),
    },
    // Design.md breakpoints.
    screens: {
      sm: '451px',
      md: '601px',
      lg: '771px',
      xl: '975px',
      '2xl': '1345px',
      '3xl': '1744px',
    },
    fontFamily: {
      // Inter stands in for Oracle Sans (variable 300–800 axis).
      sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      serif: ['Georgia', 'Gelasio', 'Cambria', 'Times New Roman', 'serif'],
      mono: ['JetBrains Mono', 'Consolas', 'ui-monospace', 'monospace'],
    },
    fontSize: {
      // [size, { lineHeight }] — headings 1.2, body 1.4–1.5, zero tracking.
      'display-xl': ['56px', { lineHeight: '67.2px' }],
      'display-lg': ['40px', { lineHeight: '48px' }],
      'display-md': ['36px', { lineHeight: '43.2px' }],
      'display-sm': ['28px', { lineHeight: '33.6px' }],
      'heading-xl': ['28px', { lineHeight: '33.6px' }],
      'heading-lg': ['24px', { lineHeight: '28.8px' }],
      'heading-md': ['20px', { lineHeight: '24px' }],
      'heading-sm': ['18px', { lineHeight: '21.6px' }],
      lead: ['20px', { lineHeight: '28px' }],
      body: ['16px', { lineHeight: '22.4px' }],
      'body-loose': ['16px', { lineHeight: '24px' }],
      label: ['14px', { lineHeight: '16.8px' }],
      small: ['14px', { lineHeight: '20px' }],
      caption: ['12px', { lineHeight: '18px' }],
    },
    fontWeight: {
      light: '300',
      book: '350',
      normal: '400',
      medium: '500',
      semibold: '600',
      bold: '700',
      heavy: '800',
    },
    letterSpacing: { normal: '0' },
    borderRadius: {
      none: '0',
      xs: '4px', // buttons
      sm: '6px', // fields
      md: '8px', // cards, media
      lg: '12px',
      xl: '15px',
      full: '9999px',
    },
    // No shadows: depth comes from the neutral ladder.
    boxShadow: { none: 'none' },
    extend: {
      spacing: {
        section: '48px',
        gutter: '72px',
      },
      maxWidth: {
        content: '1600px',
        outer: '1744px',
        prose: '72ch',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'rise-in': { from: { opacity: '0', transform: 'translateY(4px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { from: { backgroundPosition: '200% 0' }, to: { backgroundPosition: '-200% 0' } },
        pulse: { '0%, 100%': { opacity: '0.25' }, '50%': { opacity: '1' } },
      },
      animation: {
        'fade-in': 'fade-in 160ms ease-out both',
        'rise-in': 'rise-in 200ms ease-out both',
        shimmer: 'shimmer 1.8s linear infinite',
        pulse: 'pulse 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [
    // Touch-sized targets on coarse pointers (WCAG 2.5.8): pointer-coarse:min-h-[44px].
    function ({ addVariant }) {
      addVariant('pointer-coarse', '@media (pointer: coarse)');
    },
  ],
};
