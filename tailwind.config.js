/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './portfolios/**/*.py',
    './core/**/*.py'
  ],
  theme: {
    fontFamily: {
      sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Arial'],
    },
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      bg: '#F8FAFC',
      surface: '#FFFFFF',
      text: '#0F172A',
      muted: '#64748B',
      border: '#E2E8F0',
      brand: '#2563EB',
      brandHover: '#1D4ED8',
      success: '#16A34A',
      danger: '#DC2626',
      warning: '#F59E0B',
      white: '#FFFFFF',
      black: '#000000',
    },
    extend: {},
  },
  plugins: [],
};
