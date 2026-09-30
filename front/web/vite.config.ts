import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Deux entrées : site.ts pour les pages rendues par le serveur (accueil, films, borne)
// et main.tsx pour l'application React. Le serveur lit le manifest pour les inclure.
export default defineConfig({
  plugins: [react()],
  build: {
    manifest: true,
    rolldownOptions: {
      input: ['src/site.ts', 'src/main.tsx'],
    },
  },
})
