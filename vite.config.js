import { defineConfig } from 'vite';
export default defineConfig({
  clearScreen: false,
  optimizeDeps: { entries: ['index.html', 'src/index.js'], include: ['dompurify', 'fflate', 'mammoth/mammoth.browser', 'rtf.js', 'pdfjs-dist/build/pdf.mjs'] },
  server: { port: 1440, strictPort: true, watch: { ignored: ['**/public/pdf-assets/**', '**/public/licenses/**', '**/framework-dist/**', '**/integrations/**/target/**', '**/src-tauri/target/**'] } },
  build: { target: 'es2022', chunkSizeWarningLimit: 1500 },
});
