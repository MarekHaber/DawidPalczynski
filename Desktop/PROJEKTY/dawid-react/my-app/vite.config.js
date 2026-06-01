import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/DawidPalczynski/', // DOKŁADNIE TAKA SAMA NAZWA JAK TWOJE REPOZYTORIUM Z GITU
})