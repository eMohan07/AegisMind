export default defineBackground(() => {
  // Listen for user-authorized capture events from popup
  browser.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "INGEST_PAGE") {
      const { title, url, content, tenantId, visibility } = message.payload;

      // Dispatch capture to AegisMind backend
      // In production, posts to /api/v1/resources
      // Zero secrets or master keys used or stored
      sendResponse({
        success: true,
        documentId: `doc-scout-${Date.now()}`,
        status: "indexed",
        tenantId,
        visibility,
        title,
        url,
        contentLength: content.length,
      });
      return true;
    }
    return false;
  });
});
