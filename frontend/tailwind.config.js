/** @type {import('tailwindcss').Config} */
module.exports = {
  // On dit à Tailwind de scanner TOUT le projet, y compris les sous-dossiers.
  content: [
    "./**/*.{html,js}"
  ],
  theme: {
    extend: {
      colors: {
        'primary-color': '#4f46e5',
        'primary-hover': '#4338ca',
        'secondary-color': '#7c3aed',
        'light-bg': '#f9fafb',
        'card-bg': '#ffffff',
        'text-dark': '#1f2937',
        'text-medium': '#4b5563',
        'border-color': '#e5e7eb',
        'success-color': '#22c55e',
        'error-color': '#ef4444',
      }
    },
  },
  plugins: [],
}