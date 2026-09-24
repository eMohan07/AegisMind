export default defineContentScript({
  matches: ["<all_urls>"],
  main() {
    // Rule 5 Compliance: Content script only acts upon explicit user-initiated message.
    browser.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (message.type === "EXTRACT_VISIBLE_CONTENT") {
        try {
          const visibleText = extractUserVisibleContent();
          sendResponse({
            success: true,
            title: document.title,
            url: window.location.href,
            content: visibleText,
          });
        } catch (error) {
          sendResponse({
            success: false,
            error: error instanceof Error ? error.message : "Extraction failed",
          });
        }
        return true;
      }
      return false;
    });
  },
});

/**
 * Extracts visible text content strictly from rendered DOM.
 * Strips script tags, style tags, hidden elements, inputs, and credentials.
 */
function extractUserVisibleContent(): string {
  const clone = document.body.cloneNode(true) as HTMLElement;

  // Remove non-content elements and potential credential fields
  const removableSelectors = [
    "script",
    "style",
    "noscript",
    "iframe",
    "input",
    "textarea",
    "select",
    "button",
    "form",
    "[aria-hidden='true']",
    "[style*='display: none']",
    "[style*='visibility: hidden']",
  ];

  for (const selector of removableSelectors) {
    const elements = clone.querySelectorAll(selector);
    elements.forEach((el) => el.remove());
  }

  // Extract clean text content preserving headings and linebreaks
  const text = clone.innerText || clone.textContent || "";
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .join("\n\n");
}
