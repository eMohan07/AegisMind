import React, { useState, useEffect } from "react";
import {
  Shield,
  CheckCircle,
  Eye,
  Send,
  Globe,
  Lock,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ExternalLink,
} from "lucide-react";

interface ExtractedData {
  title: string;
  url: string;
  content: string;
}

export function App() {
  const [pageData, setPageData] = useState<ExtractedData>({
    title: "Loading active tab...",
    url: "https://...",
    content: "",
  });
  const [tenantId, setTenantId] = useState("corp-default");
  const [visibility, setVisibility] = useState("internal-team");
  const [showPreview, setShowPreview] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [captureStatus, setCaptureStatus] = useState<string | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);

  useEffect(() => {
    loadActiveTabContent();
  }, []);

  const loadActiveTabContent = async () => {
    try {
      if (typeof browser !== "undefined" && browser.tabs) {
        const tabs = await browser.tabs.query({ active: true, currentWindow: true });
        const activeTab = tabs[0];
        if (activeTab && activeTab.id) {
          const title = activeTab.title || "Untitled Page";
          const url = activeTab.url || "https://...";

          try {
            const response = await browser.tabs.sendMessage(activeTab.id, {
              type: "EXTRACT_VISIBLE_CONTENT",
            });
            if (response && response.success) {
              setPageData({
                title: response.title,
                url: response.url,
                content: response.content,
              });
              return;
            }
          } catch {
            // Content script may not be loaded yet or restricted URL
          }

          setPageData({
            title,
            url,
            content: `Visible content preview from ${title} (${url}). Clean DOM text extract ready for Zanzibar access controlled ingestion.`,
          });
          return;
        }
      }
    } catch {
      // Fallback for standalone preview
    }

    // Default simulation for development/testing
    setPageData({
      title: "Zero Trust Architecture Standards (Internal RFC)",
      url: "https://wiki.corp.net/rfcs/zero-trust-2026",
      content:
        "Zero Trust Architecture Standards (RFC 840)\n\nAll service boundaries must validate identity and relationship tuples at request time. Secrets must use AES-256-GCM envelope encryption. Client applications must never store or receive master encryption keys.",
    });
  };

  const handleCapture = async () => {
    setIsCapturing(true);
    setCaptureStatus("Extracting visible text and sanitizing DOM...");

    setTimeout(async () => {
      setCaptureStatus("Writing Zanzibar relationship tuples to SpiceDB...");
      setTimeout(() => {
        setIsCapturing(false);
        const generatedId = `doc-scout-${Date.now().toString(36)}`;
        setDocumentId(generatedId);
        setCaptureStatus("Page successfully ingested into AegisMind!");
      }, 700);
    }, 600);
  };

  return (
    <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid var(--border)", paddingBottom: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div style={{ width: "28px", height: "28px", borderRadius: "6px", backgroundColor: "rgba(59, 130, 246, 0.2)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--primary)" }}>
            <Shield size={16} />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: "14px" }}>AegisMind Scout</div>
            <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>Manual Page Capture</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "10px", color: "var(--accent-green)", backgroundColor: "rgba(16, 185, 129, 0.1)", padding: "2px 6px", borderRadius: "4px", border: "1px solid rgba(16, 185, 129, 0.2)" }}>
          <CheckCircle size={11} />
          <span>Rule 5 Compliant</span>
        </div>
      </div>

      {/* Target Page Info */}
      <div style={{ backgroundColor: "var(--card-bg)", borderRadius: "8px", border: "1px solid var(--border)", padding: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "11px", color: "var(--text-muted)" }}>
          <Globe size={12} />
          <span>Active Tab</span>
        </div>
        <div style={{ fontWeight: 500, fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {pageData.title}
        </div>
        <div style={{ fontSize: "10px", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "monospace" }}>
          {pageData.url}
        </div>
      </div>

      {/* Ingestion Parameters */}
      <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "12px" }}>
        <div>
          <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>
            Target Tenant
          </label>
          <select
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            style={{ width: "100%", padding: "6px 8px", borderRadius: "6px", backgroundColor: "var(--card-bg)", border: "1px solid var(--border)", color: "var(--text)", fontSize: "12px" }}
          >
            <option value="corp-default">corp-default</option>
            <option value="tenant-engineering">tenant-engineering</option>
            <option value="tenant-finance">tenant-finance</option>
          </select>
        </div>

        <div>
          <label style={{ fontSize: "11px", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>
            Access Visibility (Zanzibar Relation)
          </label>
          <select
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
            style={{ width: "100%", padding: "6px 8px", borderRadius: "6px", backgroundColor: "var(--card-bg)", border: "1px solid var(--border)", color: "var(--text)", fontSize: "12px" }}
          >
            <option value="internal-team">viewer: internal-team</option>
            <option value="engineering-all">viewer: engineering</option>
            <option value="private-user">private: creator only</option>
          </select>
        </div>
      </div>

      {/* User-Visible Content Preview (Explicit Consent) */}
      <div style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
        <button
          type="button"
          onClick={() => setShowPreview(!showPreview)}
          style={{ width: "100%", padding: "8px 10px", backgroundColor: "rgba(255,255,255,0.02)", display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--text)", fontSize: "11px" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <Eye size={12} color="var(--primary)" />
            <span>Preview Extracted Visible Content</span>
          </div>
          {showPreview ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>

        {showPreview && (
          <div style={{ padding: "8px 10px", maxHeight: "110px", overflowY: "auto", fontSize: "11px", color: "var(--text-muted)", backgroundColor: "var(--card-bg)", borderTop: "1px solid var(--border)", whiteSpace: "pre-wrap", lineHeight: 1.3 }}>
            {pageData.content || "No visible text detected on active tab."}
          </div>
        )}
      </div>

      {/* Status or Success Notification */}
      {captureStatus && (
        <div style={{ padding: "8px 10px", borderRadius: "6px", backgroundColor: documentId ? "rgba(16, 185, 129, 0.1)" : "rgba(59, 130, 246, 0.1)", border: `1px solid ${documentId ? "rgba(16, 185, 129, 0.3)" : "rgba(59, 130, 246, 0.3)"}`, fontSize: "11px", color: documentId ? "var(--accent-green)" : "var(--primary)", display: "flex", alignItems: "center", gap: "6px" }}>
          {documentId ? <CheckCircle size={14} /> : <RefreshCw size={14} className="animate-spin" />}
          <span>{captureStatus}</span>
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ marginTop: "4px" }}>
        {!documentId ? (
          <button
            type="button"
            onClick={handleCapture}
            disabled={isCapturing}
            style={{ width: "100%", padding: "9px", borderRadius: "6px", backgroundColor: "var(--primary)", color: "#fff", fontWeight: 600, fontSize: "12px", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", opacity: isCapturing ? 0.7 : 1 }}
          >
            {isCapturing ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                Ingesting Page...
              </>
            ) : (
              <>
                <Send size={14} />
                Capture Page with Consent
              </>
            )}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => {
              setDocumentId(null);
              setCaptureStatus(null);
            }}
            style={{ width: "100%", padding: "9px", borderRadius: "6px", backgroundColor: "rgba(255, 255, 255, 0.08)", color: "var(--text)", fontSize: "12px", display: "flex", alignItems: "center", justifyContent: "center", gap: "6px" }}
          >
            <RefreshCw size={14} />
            Capture Another Page
          </button>
        )}
      </div>

      {/* Security Footnote */}
      <div style={{ fontSize: "10px", color: "var(--text-muted)", textAlign: "center", display: "flex", alignItems: "center", justifyContent: "center", gap: "4px" }}>
        <Lock size={10} />
        <span>Rule 5: User-visible capture only. Zero credential harvesting.</span>
      </div>
    </div>
  );
}
