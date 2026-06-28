/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0f0f14',
          raised: '#16161f',
          glass: 'rgba(22, 22, 31, 0.7)',
        },
        accent: {
          DEFAULT: '#8b5cf6',
          hover: '#a78bfa',
          muted: '#6d28d9',
        },
      },
      backdropBlur: {
        glass: '16px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};
