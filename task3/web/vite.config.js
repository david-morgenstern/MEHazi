import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  build: {
    // The Dockerfile copies this into the API image, which serves it.
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    // Only for `npm run dev` outside Docker: send /api to a locally running
    // API so the dev server and the container behave the same.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
