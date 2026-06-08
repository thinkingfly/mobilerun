/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0f',
          secondary: '#12121a',
          tertiary: '#1a1a26',
        },
        border: {
          DEFAULT: '#2a2a3a',
          light: '#3a3a4a',
        },
        text: {
          primary: '#e4e4e7',
          secondary: '#a1a1aa',
          muted: '#71717a',
        },
        accent: {
          blue: '#6366f1',
          green: '#22c55e',
          red: '#ef4444',
          yellow: '#f59e0b',
          cyan: '#06b6d4',
          purple: '#a855f7',
        },
      },
    },
  },
  plugins: [],
};
