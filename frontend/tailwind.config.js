/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: '#070a12',
        panel: '#0f1626',
        line: '#263145',
        muted: '#9aa7bd'
      },
      boxShadow: {
        soft: '0 18px 50px rgba(0, 0, 0, 0.28)'
      }
    }
  },
  plugins: []
};

