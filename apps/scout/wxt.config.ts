import { defineConfig } from "wxt";

// See https://wxt.dev/api/config.html
export default defineConfig({
  extensionApi: "chrome",
  modules: ["@wxt-dev/module-react"],
  manifest: {
    name: "AegisMind Scout",
    description: "Manual page capture for AegisMind knowledge ingestion (Rule 5 compliant)",
    version: "0.1.0",
    permissions: ["activeTab", "storage"],
    action: {
      default_title: "AegisMind Scout",
    },
  },
});
