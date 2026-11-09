import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  root: path.resolve(__dirname),
  plugins: [tailwindcss(), react()],
  base: "./",
  build: {
    target: "chrome140",
    outDir: "../ui",
    emptyOutDir: true,
    assetsDir: "assets",
    // Bundled fonts are inlined into the reviewed stylesheet: the packaging gate only accepts
    // approved ui/assets files, and fonts must never load from the network.
    assetsInlineLimit: (file) => (file.endsWith(".woff2") ? true : undefined),
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (
            id.includes("react-markdown") ||
            id.includes("remark-gfm") ||
            id.includes("rehype-highlight") ||
            id.includes("highlight.js")
          )
            return "markdown";
          if (
            id.includes("motion") ||
            id.includes("lucide-react") ||
            id.includes("@base-ui")
          )
            return "desktopUi";
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
