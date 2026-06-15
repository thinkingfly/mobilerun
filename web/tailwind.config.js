/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary:     'rgb(var(--bg-primary) / <alpha-value>)',
          secondary:   'rgb(var(--bg-secondary) / <alpha-value>)',
          tertiary:    'rgb(var(--bg-tertiary) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--border) / <alpha-value>)',
          light:   'rgb(var(--border-light) / <alpha-value>)',
        },
        text: {
          primary:   'rgb(var(--text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
          muted:     'rgb(var(--text-muted) / <alpha-value>)',
        },
        accent: {
          blue:   'rgb(var(--accent-blue) / <alpha-value>)',
          green:  'rgb(var(--accent-green) / <alpha-value>)',
          red:    'rgb(var(--accent-red) / <alpha-value>)',
          yellow: 'rgb(var(--accent-yellow) / <alpha-value>)',
          cyan:   'rgb(var(--accent-cyan) / <alpha-value>)',
          purple: 'rgb(var(--accent-purple) / <alpha-value>)',
        },
        terminal: {
          bg:   'rgb(var(--terminal-bg) / <alpha-value>)',
          text: 'rgb(var(--terminal-text) / <alpha-value>)',
        },
      },
    },
  },
  plugins: [],
};
