/**
 * Tokenade Browser Extension v1.4 — Popup Controller
 *
 * Provides full UI/UX and feature parity with the Tokenade CLI:
 * - Tabbed workspace (Export, Import/Inject, Inspect, Settings)
 * - Bidirectional session flow: Export active session or Inject .tokenade session into browser
 * - Native WebCrypto AES-256-GCM encryption/decryption matching TokenadeEncryptor
 * - Known site handler detection (Google, Discord, Telegram, X, GitHub, ChatGPT)
 * - Persistent preferences via chrome.storage.local
 */

const KNOWN_SITES = {
  "google.com": {
    name: "Google",
    badge: "GOOGLE",
    critical: ["SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-3PSID"],
    storage_origins: ["https://accounts.google.com", "https://myaccount.google.com", "https://mail.google.com", "https://google.com"],
  },
  "mail.google.com": {
    name: "Gmail",
    badge: "GMAIL",
    critical: ["SID", "HSID", "SSID", "__Secure-3PSID"],
    storage_origins: ["https://mail.google.com", "https://accounts.google.com"],
  },
  "discord.com": {
    name: "Discord",
    badge: "DISCORD",
    critical: ["__dcfduid", "__sdcfduid"],
    storage: ["token"],
    storage_origins: ["https://discord.com", "https://discordapp.com"],
  },
  "telegram.org": {
    name: "Telegram",
    badge: "TELEGRAM",
    critical: ["stel_ssid"],
    storage: ["user_auth"],
    storage_origins: ["https://web.telegram.org", "https://telegram.org"],
  },
  "web.telegram.org": {
    name: "Telegram Web",
    badge: "TELEGRAM",
    critical: ["stel_ssid"],
    storage: ["user_auth"],
    storage_origins: ["https://web.telegram.org", "https://telegram.org"],
  },
  "twitter.com": {
    name: "Twitter / X",
    badge: "X / TWITTER",
    critical: ["auth_token", "ct0", "twid", "kdt"],
    storage_origins: ["https://x.com", "https://twitter.com"],
  },
  "x.com": {
    name: "Twitter / X",
    badge: "X / TWITTER",
    critical: ["auth_token", "ct0", "twid", "kdt"],
    storage_origins: ["https://x.com", "https://twitter.com"],
  },
  "github.com": {
    name: "GitHub",
    badge: "GITHUB",
    critical: ["user_session", "__Host-user_session_same_site", "dotcom_user"],
    storage_origins: ["https://github.com"],
  },
  "openai.com": {
    name: "OpenAI / ChatGPT",
    badge: "CHATGPT",
    critical: ["__Secure-next-auth.session-token", "cf_clearance"],
    storage_origins: ["https://chatgpt.com", "https://openai.com"],
  },
  "chatgpt.com": {
    name: "OpenAI / ChatGPT",
    badge: "CHATGPT",
    critical: ["__Secure-next-auth.session-token", "cf_clearance"],
    storage_origins: ["https://chatgpt.com", "https://openai.com"],
  },
};

document.addEventListener("DOMContentLoaded", async () => {
  // Elements
  const activeDomainEl = document.getElementById("active-domain");
  const activeSummaryEl = document.getElementById("active-summary");
  const siteBadgeEl = document.getElementById("site-badge");
  const bridgeStatusDot = document.getElementById("bridge-status-dot");
  const bridgeStatusText = document.getElementById("bridge-status-text");
  const btnPopoutWindow = document.getElementById("btn-popout-window");
  const btnClosePopup = document.getElementById("btn-close-popup");

  // Export elements
  const statCookiesCount = document.getElementById("stat-cookies-count");
  const statExpiredCount = document.getElementById("stat-expired-count");
  const statHealthScore = document.getElementById("stat-health-score");
  const statStorageCount = document.getElementById("stat-storage-count");
  const exportFormatSelect = document.getElementById("export-format");
  const exportPasswordInput = document.getElementById("export-password");
  const optAllDomains = document.getElementById("opt-all-domains");
  const optLocalStorage = document.getElementById("opt-local-storage");
  const optSessionStorage = document.getElementById("opt-session-storage");
  const btnExportDownload = document.getElementById("btn-export-download");
  const btnExportCopy = document.getElementById("btn-export-copy");
  const exportStatusEl = document.getElementById("export-status");

  // Import elements
  const importDropzone = document.getElementById("import-dropzone");
  const importFileInput = document.getElementById("import-file-input");
  const importPreviewCard = document.getElementById("import-preview-card");
  const importSiteName = document.getElementById("import-site-name");
  const importDetails = document.getElementById("import-details");
  const importTypeBadge = document.getElementById("import-type-badge");
  const importPassGroup = document.getElementById("import-pass-group");
  const importPasswordInput = document.getElementById("import-password");
  const optCleanInject = document.getElementById("opt-clean-inject");
  const optAutoReload = document.getElementById("opt-auto-reload");
  const btnInjectSession = document.getElementById("btn-inject-session");
  const importStatusEl = document.getElementById("import-status");

  // Inspect elements
  const cookieSearchInput = document.getElementById("cookie-search");
  const cookieTableBody = document.getElementById("cookie-table-body");
  const btnInspectRefresh = document.getElementById("btn-inspect-refresh");
  const btnInspectCopyAll = document.getElementById("btn-inspect-copy-all");

  // Settings elements
  const settingProxyUrl = document.getElementById("setting-proxy-url");
  const settingTheme = document.getElementById("setting-theme");
  const btnSendToProxy = document.getElementById("btn-send-to-proxy");
  const btnResetPreferences = document.getElementById("btn-reset-preferences");
  const settingsStatusEl = document.getElementById("settings-status");

  // Vault elements
  const vaultSearchInput = document.getElementById("vault-search");
  const vaultSessionsList = document.getElementById("vault-sessions-list");
  const btnStoreActiveToVault = document.getElementById("btn-store-active-to-vault");
  const btnRefreshVault = document.getElementById("btn-refresh-vault");
  const vaultStatusEl = document.getElementById("vault-status");

  // Health elements
  const healthSiteName = document.getElementById("health-site-name");
  const healthAuthVerdict = document.getElementById("health-auth-verdict");
  const healthGradeBadge = document.getElementById("health-grade-badge");
  const healthCriticalBody = document.getElementById("health-critical-body");
  const healthOriginsList = document.getElementById("health-origins-list");

  let currentTab = null;
  let currentDomain = "";
  let extractedSession = null;
  let activeCookiesList = [];
  let importedRawBytes = null;
  let importedParsedSession = null;
  let activeMatchedSite = null;
  let vaultStoredSessions = [];

  // ── Navigation Tab Switching ─────────────────────────────────────────────

  document.querySelectorAll(".nav-item").forEach((nav) => {
    nav.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
      document.querySelectorAll(".view-tab").forEach((t) => t.classList.remove("active"));
      nav.classList.add("active");
      const targetTab = document.getElementById(nav.getAttribute("data-tab"));
      if (targetTab) {
        targetTab.classList.add("active");
        if (targetTab.id === "tab-vault") fetchVaultSessions();
        if (targetTab.id === "tab-health") renderHealthDiagnostics();
      }
    });
  });

  // ── Load & Save Preferences ──────────────────────────────────────────────

  async function loadPreferences() {
    try {
      const prefs = await chrome.storage.local.get([
        "exportFormat",
        "optLocalStorage",
        "optSessionStorage",
        "optCleanInject",
        "optAutoReload",
        "proxyUrl",
        "themePreference",
      ]);
      if (prefs.exportFormat) exportFormatSelect.value = prefs.exportFormat;
      if (typeof prefs.optLocalStorage === "boolean") optLocalStorage.checked = prefs.optLocalStorage;
      if (typeof prefs.optSessionStorage === "boolean") optSessionStorage.checked = prefs.optSessionStorage;
      if (typeof prefs.optCleanInject === "boolean") optCleanInject.checked = prefs.optCleanInject;
      if (typeof prefs.optAutoReload === "boolean") optAutoReload.checked = prefs.optAutoReload;
      if (prefs.proxyUrl) settingProxyUrl.value = prefs.proxyUrl;
      if (prefs.themePreference) {
        settingTheme.value = prefs.themePreference;
        applyTheme(prefs.themePreference);
      }
    } catch (_) {}
  }

  function applyTheme(theme) {
    if (theme === "light") {
      document.body.classList.add("light-theme");
    } else if (theme === "dark") {
      document.body.classList.remove("light-theme");
    } else {
      // System
      const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
      document.body.classList.toggle("light-theme", prefersLight);
    }
  }

  function savePreference(key, val) {
    try {
      chrome.storage.local.set({ [key]: val });
    } catch (_) {}
  }

  exportFormatSelect.addEventListener("change", () => savePreference("exportFormat", exportFormatSelect.value));
  optLocalStorage.addEventListener("change", () => savePreference("optLocalStorage", optLocalStorage.checked));
  optSessionStorage.addEventListener("change", () => savePreference("optSessionStorage", optSessionStorage.checked));
  optCleanInject.addEventListener("change", () => savePreference("optCleanInject", optCleanInject.checked));
  optAutoReload.addEventListener("change", () => savePreference("optAutoReload", optAutoReload.checked));
  settingProxyUrl.addEventListener("change", () => savePreference("proxyUrl", settingProxyUrl.value.trim()));
  settingTheme.addEventListener("change", () => {
    savePreference("themePreference", settingTheme.value);
    applyTheme(settingTheme.value);
  });

  btnResetPreferences.addEventListener("click", async () => {
    try {
      await chrome.storage.local.clear();
      showStatus(settingsStatusEl, "Saved preferences reset to defaults.", "success");
      setTimeout(() => window.location.reload(), 800);
    } catch (e) {
      showStatus(settingsStatusEl, `Failed to reset: ${e.message}`, "error");
    }
  });

  // ── Tab Discovery & Known Site Diagnostics ───────────────────────────────

  function detectKnownSite() {
    let matched = null;
    for (const [domainKey, meta] of Object.entries(KNOWN_SITES)) {
      if (currentDomain === domainKey || currentDomain.endsWith("." + domainKey)) {
        matched = meta;
        break;
      }
    }
    activeMatchedSite = matched;
    if (matched) {
      siteBadgeEl.textContent = matched.badge;
      siteBadgeEl.className = "site-badge known";
    } else {
      siteBadgeEl.textContent = "SITE";
      siteBadgeEl.className = "site-badge";
    }
  }

  async function initTab() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const paramTabId = urlParams.get("tabId");
      const paramDomain = urlParams.get("domain");

      if (paramTabId && paramDomain) {
        try {
          const t = await chrome.tabs.get(parseInt(paramTabId, 10));
          if (t && t.url) {
            currentTab = t;
            currentDomain = paramDomain;
            activeDomainEl.textContent = currentDomain;
            detectKnownSite();
            return true;
          }
        } catch (_) {}
      }

      // Query active tab in the focused non-extension window
      const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      let tab = tabs[0];
      if (!tab || tab.url?.startsWith("chrome-extension://")) {
        const allTabs = await chrome.tabs.query({ active: true });
        tab = allTabs.find((t) => !t.url?.startsWith("chrome-extension://")) || tab;
      }
      currentTab = tab;
      if (!tab?.url || tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
        activeDomainEl.textContent = "Internal browser page";
        activeSummaryEl.textContent = "Open a website tab to inspect and export sessions";
        siteBadgeEl.textContent = "SYSTEM";
        return false;
      }
      const url = new URL(tab.url);
      currentDomain = url.hostname;
      activeDomainEl.textContent = currentDomain;
      detectKnownSite();
      return true;
    } catch (e) {
      activeDomainEl.textContent = "Error reading active tab";
      activeSummaryEl.textContent = String(e);
      return false;
    }
  }

  // ── Helper: Domain Matching ──────────────────────────────────────────────

  function domainOf(cookie) {
    const d = cookie.domain || "";
    return d.startsWith(".") ? d.slice(1) : d;
  }

  function getRelatedDomains(domain) {
    const domains = [domain];
    const parts = domain.split(".");
    for (let i = 0; i < parts.length - 1; i++) {
      domains.push("." + parts.slice(i).join("."));
    }
    return domains;
  }

  // ── Extraction Logic ─────────────────────────────────────────────────────

  async function fetchCookies() {
    if (optAllDomains.checked) {
      return await chrome.cookies.getAll({});
    }
    const domains = getRelatedDomains(currentDomain);
    const all = [];
    for (const d of domains) {
      const list = await chrome.cookies.getAll({ domain: d });
      all.push(...list);
    }
    const seen = new Set();
    return all.filter((c) => {
      const key = `${c.name}|${c.domain}|${c.path}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  async function fetchMultiOriginStorage(storageType = "localStorage") {
    const isLocal = storageType === "localStorage";
    const isEnabled = isLocal ? optLocalStorage.checked : optSessionStorage.checked;
    if (!isEnabled || !currentTab?.id) return {};

    const storageByOrigin = {};
    const primaryOrigin = currentTab?.url ? new URL(currentTab.url).origin : `https://${currentDomain}`;

    const scrapeScript = isLocal
      ? () => {
          const out = {};
          try {
            for (let i = 0; i < localStorage.length; i++) {
              const k = localStorage.key(i);
              if (k != null) out[k] = localStorage.getItem(k);
            }
          } catch (_) {}
          return out;
        }
      : () => {
          const out = {};
          try {
            for (let i = 0; i < sessionStorage.length; i++) {
              const k = sessionStorage.key(i);
              if (k != null) out[k] = sessionStorage.getItem(k);
            }
          } catch (_) {}
          return out;
        };

    // 1. Scrape active tab
    try {
      const activeRes = await chrome.scripting.executeScript({
        target: { tabId: currentTab.id },
        func: scrapeScript,
      });
      const activeData = activeRes?.[0]?.result || {};
      if (Object.keys(activeData).length > 0) {
        storageByOrigin[primaryOrigin] = activeData;
      }
    } catch (_) {}

    // 2. Scrape matching open tabs for declared secondary origins (e.g. web.telegram.org vs telegram.org)
    if (activeMatchedSite?.storage_origins?.length) {
      for (const originUrl of activeMatchedSite.storage_origins) {
        if (originUrl === primaryOrigin) continue;
        try {
          const matchingTabs = await chrome.tabs.query({ url: `${originUrl}/*` });
          for (const sTab of matchingTabs) {
            if (!sTab.id || sTab.id === currentTab.id) continue;
            try {
              const secRes = await chrome.scripting.executeScript({
                target: { tabId: sTab.id },
                func: scrapeScript,
              });
              const secData = secRes?.[0]?.result || {};
              if (Object.keys(secData).length > 0) {
                storageByOrigin[originUrl] = secData;
                break; // One successful scrape per origin is sufficient
              }
            } catch (_) {}
          }
        } catch (_) {}
      }
    }

    return storageByOrigin;
  }

  async function refreshSessionData() {
    if (!currentDomain) return;

    try {
      const cookies = await fetchCookies();
      activeCookiesList = cookies;
      const localStorageMap = await fetchMultiOriginStorage("localStorage");
      const sessionStorageMap = await fetchMultiOriginStorage("sessionStorage");

      const now = Date.now() / 1000;
      const expired = cookies.filter((c) => c.expirationDate && c.expirationDate < now).length;
      const valid = cookies.length - expired;
      const health = cookies.length ? Math.round((valid / cookies.length) * 100) : 0;

      let totalStorageKeys = 0;
      for (const map of Object.values(localStorageMap)) totalStorageKeys += Object.keys(map).length;
      for (const map of Object.values(sessionStorageMap)) totalStorageKeys += Object.keys(map).length;

      statCookiesCount.textContent = String(cookies.length);
      statExpiredCount.textContent = String(expired);
      statHealthScore.textContent = `${health}%`;
      statStorageCount.textContent = String(totalStorageKeys);

      activeSummaryEl.textContent = `${cookies.length} cookies · ${totalStorageKeys} storage keys across ${
        new Set([...Object.keys(localStorageMap), ...Object.keys(sessionStorageMap)]).size || 1
      } origin(s)`;

      // Package native .tokenade format
      extractedSession = {
        version: "3.0.0",
        site_name: currentDomain,
        created_at: new Date().toISOString(),
        auth_status: health > 50 ? "authenticated" : "anonymous",
        cookies: cookies.map((c) => ({
          name: c.name,
          value: c.value,
          domain: c.domain,
          path: c.path || "/",
          secure: Boolean(c.secure),
          httpOnly: Boolean(c.httpOnly),
          sameSite: c.sameSite || "Lax",
          expirationDate: c.expirationDate || null,
        })),
        local_storage: localStorageMap,
        session_storage: sessionStorageMap,
        storage: {
          local: localStorageMap,
          session: sessionStorageMap,
        },
        metadata: {
          exported_by: "tokenade-extension-v1.4",
          health_score: health / 100,
          cookie_count: cookies.length,
          storage_origins: Array.from(new Set([...Object.keys(localStorageMap), ...Object.keys(sessionStorageMap)])),
          target_origin: currentDomain,
        },
      };

      btnExportDownload.disabled = false;
      btnExportCopy.disabled = false;

      renderInspectTable();
    } catch (err) {
      showStatus(exportStatusEl, `Extraction error: ${err.message}`, "error");
    }
  }

  // ── Status Message Utility ───────────────────────────────────────────────

  function showStatus(element, text, type = "loading") {
    element.textContent = text;
    element.className = `status-msg ${type}`;
    element.style.display = "block";
    if (type !== "loading") {
      setTimeout(() => {
        if (element.textContent === text) {
          element.style.display = "none";
        }
      }, 4000);
    }
  }

  // ── Export Handling ──────────────────────────────────────────────────────

  function formatOutput(format, session) {
    if (format === "cookie-editor") {
      return JSON.stringify(
        session.cookies.map((c) => ({
          name: c.name,
          value: c.value,
          domain: c.domain,
          path: c.path,
          secure: c.secure,
          httpOnly: c.httpOnly,
          sameSite: (c.sameSite || "Lax").toLowerCase(),
          expirationDate: c.expirationDate,
        })),
        null,
        2
      );
    }
    if (format === "netscape") {
      const lines = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""];
      for (const c of session.cookies) {
        const includeSubdomains = c.domain.startsWith(".") ? "TRUE" : "FALSE";
        const isSecure = c.secure ? "TRUE" : "FALSE";
        const expiry = c.expirationDate ? Math.round(c.expirationDate) : 0;
        lines.push(`${c.domain}\t${includeSubdomains}\t${c.path}\t${isSecure}\t${expiry}\t${c.name}\t${c.value}`);
      }
      return lines.join("\n");
    }
    // Default native .tokenade JSON
    return JSON.stringify(session, null, 2);
  }

  btnExportDownload.addEventListener("click", async () => {
    if (!extractedSession) return;
    const format = exportFormatSelect.value;
    const password = exportPasswordInput.value;

    try {
      const rawText = formatOutput(format, extractedSession);
      let blob;
      let filename;

      if (password && format === "tokenade") {
        showStatus(exportStatusEl, "Encrypting session with AES-256-GCM...", "loading");
        const encryptedBytes = await TokenadeWebCrypto.encrypt(rawText, password);
        blob = new Blob([encryptedBytes], { type: "application/octet-stream" });
        filename = `${currentDomain}.tokenade.enc`;
      } else {
        blob = new Blob([rawText], { type: "application/json" });
        filename = format === "netscape" ? `${currentDomain}_cookies.txt` : `${currentDomain}.tokenade`;
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);

      showStatus(exportStatusEl, `Saved ${filename} successfully!`, "success");
    } catch (e) {
      showStatus(exportStatusEl, `Export error: ${e.message}`, "error");
    }
  });

  btnExportCopy.addEventListener("click", async () => {
    if (!extractedSession) return;
    try {
      const rawText = formatOutput(exportFormatSelect.value, extractedSession);
      await navigator.clipboard.writeText(rawText);
      showStatus(exportStatusEl, "Session copied to clipboard!", "success");
    } catch (e) {
      showStatus(exportStatusEl, `Clipboard error: ${e.message}`, "error");
    }
  });

  // ── Header Actions (Pop-out Window & Close) ──────────────────────────────

  if (btnPopoutWindow) {
    btnPopoutWindow.addEventListener("click", () => {
      if (chrome.windows?.create) {
        chrome.windows.create({
          url: chrome.runtime.getURL("popup.html"),
          type: "popup",
          width: 620,
          height: 600,
          focused: true,
        });
      } else {
        chrome.tabs.create({ url: chrome.runtime.getURL("popup.html") });
      }
    });
  }

  if (btnClosePopup) {
    btnClosePopup.addEventListener("click", () => window.close());
  }

  // ── Import & Injection Flow ──────────────────────────────────────────────

  const togglePasteInput = document.getElementById("toggle-paste-input");
  const pasteGroup = document.getElementById("paste-group");
  const pasteTextarea = document.getElementById("paste-textarea");

  if (togglePasteInput && pasteGroup && pasteTextarea) {
    togglePasteInput.addEventListener("click", () => {
      const isVisible = pasteGroup.style.display !== "none";
      pasteGroup.style.display = isVisible ? "none" : "block";
      togglePasteInput.textContent = isVisible
        ? "Or paste raw session JSON / text payload"
        : "Hide raw text input";
    });

    pasteTextarea.addEventListener("input", () => {
      const text = pasteTextarea.value.trim();
      if (text && (text.startsWith("{") || text.startsWith("["))) {
        parseAndPreviewSession(text, "pasted-session.tokenade");
      }
    });
  }

  window.addEventListener("paste", (e) => {
    if (document.getElementById("tab-import")?.classList.contains("active")) {
      const text = e.clipboardData?.getData("text");
      if (text && (text.trim().startsWith("{") || text.trim().startsWith("["))) {
        parseAndPreviewSession(text.trim(), "clipboard-session.tokenade");
      }
    }
  });

  importDropzone.addEventListener("click", () => importFileInput.click());
  importDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    importDropzone.classList.add("dragover");
  });
  importDropzone.addEventListener("dragleave", () => importDropzone.classList.remove("dragover"));
  importDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    importDropzone.classList.remove("dragover");
    if (e.dataTransfer.files?.length) {
      handleImportFile(e.dataTransfer.files[0]);
    }
  });
  importFileInput.addEventListener("change", () => {
    if (importFileInput.files?.length) {
      handleImportFile(importFileInput.files[0]);
    }
  });

  async function handleImportFile(file) {
    try {
      const buffer = await file.arrayBuffer();
      importedRawBytes = new Uint8Array(buffer);

      if (TokenadeWebCrypto.isEncrypted(importedRawBytes)) {
        importPassGroup.style.display = "block";
        importTypeBadge.textContent = "ENCRYPTED";
        importTypeBadge.className = "site-badge known";
        importSiteName.textContent = file.name;
        importDetails.textContent = "Encrypted Tokenade v2 format — enter password to decrypt";
        importPreviewCard.style.display = "block";
        btnInjectSession.disabled = false;
      } else {
        importPassGroup.style.display = "none";
        importTypeBadge.textContent = "PLAINTEXT";
        importTypeBadge.className = "site-badge";
        const text = new TextDecoder().decode(importedRawBytes);
        parseAndPreviewSession(text, file.name);
      }
    } catch (e) {
      showStatus(importStatusEl, `File load error: ${e.message}`, "error");
    }
  }

  function parseAndPreviewSession(text, filename) {
    try {
      const parsed = JSON.parse(text);
      let cookies = [];
      let siteName = "Imported Session";

      if (Array.isArray(parsed)) {
        // Cookie-Editor array
        cookies = parsed;
      } else if (parsed.cookies && Array.isArray(parsed.cookies)) {
        // Native .tokenade format
        cookies = parsed.cookies;
        siteName = parsed.site_name || filename;
      }

      importedParsedSession = parsed;
      importSiteName.textContent = siteName;
      importDetails.textContent = `${cookies.length} cookies · ready to inject`;
      importPreviewCard.style.display = "block";
      btnInjectSession.disabled = false;
      showStatus(importStatusEl, "Session loaded! Ready to inject into browser.", "success");
    } catch (e) {
      showStatus(importStatusEl, `Parse error: file is not valid session JSON: ${e.message}`, "error");
    }
  }

  btnInjectSession.addEventListener("click", async () => {
    try {
      showStatus(importStatusEl, "Decrypting and preparing session...", "loading");

      let session = importedParsedSession;
      if (importedRawBytes && TokenadeWebCrypto.isEncrypted(importedRawBytes)) {
        const password = importPasswordInput.value;
        if (!password) {
          showStatus(importStatusEl, "Please enter the decryption password", "error");
          return;
        }
        const decryptedText = await TokenadeWebCrypto.decrypt(importedRawBytes, password);
        session = JSON.parse(decryptedText);
      }

      if (!session) {
        showStatus(importStatusEl, "No valid session to inject", "error");
        return;
      }

      const cookies = Array.isArray(session) ? session : session.cookies || [];
      const cleanInject = optCleanInject.checked;

      showStatus(importStatusEl, `Injecting ${cookies.length} cookies into browser...`, "loading");

      // Optional: Clear existing cookies for target domains
      if (cleanInject && currentDomain) {
        const existing = await fetchCookies();
        for (const c of existing) {
          try {
            const protocol = c.secure ? "https:" : "http:";
            const d = c.domain.startsWith(".") ? c.domain.slice(1) : c.domain;
            await chrome.cookies.remove({ url: `${protocol}//${d}${c.path}`, name: c.name });
          } catch (_) {}
        }
      }

      // Inject cookies
      let injected = 0;
      for (const c of cookies) {
        try {
          const domain = c.domain || currentDomain;
          const cleanDomain = domain.startsWith(".") ? domain.slice(1) : domain;
          const protocol = c.secure ? "https:" : "http:";
          const url = `${protocol}//${cleanDomain}${c.path || "/"}`;

          const cookieDetails = {
            url: url,
            name: c.name,
            value: c.value || "",
            path: c.path || "/",
            secure: Boolean(c.secure),
            httpOnly: Boolean(c.httpOnly),
          };

          if (c.domain && !c.domain.startsWith("localhost") && !c.domain.startsWith("127.0.0.1")) {
            cookieDetails.domain = c.domain;
          }
          if (c.sameSite) {
            const ss = String(c.sameSite).toLowerCase();
            if (ss.includes("lax")) cookieDetails.sameSite = "lax";
            else if (ss.includes("strict")) cookieDetails.sameSite = "strict";
            else if (ss.includes("no") || ss.includes("none")) {
              cookieDetails.sameSite = "no_restriction";
              cookieDetails.secure = true;
            }
          }
          if (c.expirationDate && c.expirationDate > Date.now() / 1000) {
            cookieDetails.expirationDate = Math.round(c.expirationDate);
          }

          await chrome.cookies.set(cookieDetails);
          injected++;
        } catch (err) {
          console.warn("Cookie inject fail", c.name, err);
        }
      }

      // Inject storage if present and current tab is active
      const storage = session.storage || { local: session.local_storage || {}, session: session.session_storage || {} };
      if (currentTab?.id && (storage.local || storage.session)) {
        try {
          await chrome.scripting.executeScript({
            target: { tabId: currentTab.id },
            func: (stor) => {
              try {
                if (stor.local) {
                  for (const [, map] of Object.entries(stor.local)) {
                    if (map && typeof map === "object") {
                      for (const [k, v] of Object.entries(map)) localStorage.setItem(k, v);
                    }
                  }
                }
                if (stor.session) {
                  for (const [, map] of Object.entries(stor.session)) {
                    if (map && typeof map === "object") {
                      for (const [k, v] of Object.entries(map)) sessionStorage.setItem(k, v);
                    }
                  }
                }
              } catch (_) {}
            },
            args: [storage],
          });
        } catch (_) {}
      }

      showStatus(importStatusEl, `Injected ${injected}/${cookies.length} cookies successfully!`, "success");

      if (optAutoReload.checked && currentTab?.id) {
        setTimeout(() => {
          chrome.tabs.reload(currentTab.id);
          window.close();
        }, 1000);
      }
    } catch (e) {
      showStatus(importStatusEl, `Injection error: ${e.message}`, "error");
    }
  });

  // ── Cookie Inspector Table ───────────────────────────────────────────────

  function renderInspectTable() {
    const query = (cookieSearchInput.value || "").trim().toLowerCase();
    const filtered = activeCookiesList.filter(
      (c) => !query || c.name.toLowerCase().includes(query) || (c.value && c.value.toLowerCase().includes(query))
    );

    cookieTableBody.innerHTML = "";
    if (!filtered.length) {
      cookieTableBody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:var(--text-muted); padding:12px;">${
        query ? "No cookies match search query" : "No cookies found for domain"
      }</td></tr>`;
      return;
    }

    const now = Date.now() / 1000;
    for (const c of filtered) {
      const tr = document.createElement("tr");
      const isExpired = c.expirationDate && c.expirationDate < now;

      const tdName = document.createElement("td");
      tdName.style.fontWeight = "600";
      tdName.textContent = c.name;
      if (isExpired) tdName.style.color = "var(--error-text)";

      const tdValue = document.createElement("td");
      tdValue.textContent = c.value.length > 28 ? c.value.slice(0, 28) + "…" : c.value;
      tdValue.title = "Click to copy value";
      tdValue.style.cursor = "pointer";
      tdValue.addEventListener("click", async () => {
        await navigator.clipboard.writeText(c.value);
        tdValue.textContent = "Copied!";
        setTimeout(() => (tdValue.textContent = c.value.length > 28 ? c.value.slice(0, 28) + "…" : c.value), 1000);
      });

      const tdFlags = document.createElement("td");
      if (c.secure) tdFlags.innerHTML += '<span class="tag sec">SEC</span>';
      if (c.httpOnly) tdFlags.innerHTML += '<span class="tag http">HTTP</span>';
      if (c.sameSite) tdFlags.innerHTML += `<span class="tag">${c.sameSite}</span>`;

      tr.appendChild(tdName);
      tr.appendChild(tdValue);
      tr.appendChild(tdFlags);
      cookieTableBody.appendChild(tr);
    }
  }

  cookieSearchInput.addEventListener("input", renderInspectTable);
  btnInspectRefresh.addEventListener("click", async () => {
    await refreshSessionData();
  });
  btnInspectCopyAll.addEventListener("click", async () => {
    const query = (cookieSearchInput.value || "").trim().toLowerCase();
    const filtered = activeCookiesList.filter(
      (c) => !query || c.name.toLowerCase().includes(query) || (c.value && c.value.toLowerCase().includes(query))
    );
    await navigator.clipboard.writeText(JSON.stringify(filtered, null, 2));
    btnInspectCopyAll.textContent = "Copied!";
    setTimeout(() => (btnInspectCopyAll.textContent = "Copy Filtered"), 1200);
  });

  // ── Vault / Library Operations ──────────────────────────────────────────

  async function fetchVaultSessions() {
    const proxyUrl = settingProxyUrl.value.trim() || "http://127.0.0.1:9222";
    vaultSessionsList.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:16px; font-size:11px;">Loading stored sessions from ${proxyUrl}...</div>`;
    try {
      const resp = await fetch(`${proxyUrl}/api/sessions`, { method: "GET", signal: AbortSignal.timeout(2000) });
      if (resp.ok) {
        const data = await resp.json();
        vaultStoredSessions = data.stored_sessions || [];
        renderVaultList();
      } else {
        vaultSessionsList.innerHTML = `<div style="text-align:center; color:var(--error-text); padding:16px; font-size:11px;">Proxy returned HTTP ${resp.status}</div>`;
      }
    } catch (e) {
      vaultSessionsList.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:16px; font-size:11px;">Proxy offline (${e.message}). Start \`tokenade proxy\` or \`tokenade gateway\` to view Vault.</div>`;
    }
  }

  function renderVaultList() {
    const query = (vaultSearchInput.value || "").trim().toLowerCase();
    const filtered = vaultStoredSessions.filter(
      (s) => !query || s.site_name.toLowerCase().includes(query) || s.name.toLowerCase().includes(query)
    );

    vaultSessionsList.innerHTML = "";
    if (!filtered.length) {
      vaultSessionsList.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:16px; font-size:11px;">${
        query ? "No sessions match search query" : "No stored sessions found in ~/.tokenade/sessions/"
      }</div>`;
      return;
    }

    for (const s of filtered) {
      const card = document.createElement("div");
      card.className = "site-card";
      card.style.marginBottom = "6px";
      card.style.padding = "8px 10px";

      const meta = document.createElement("div");
      meta.className = "site-meta";

      const title = document.createElement("div");
      title.className = "site-domain";
      title.textContent = s.site_name || s.name;

      const sub = document.createElement("div");
      sub.className = "site-sub";
      sub.textContent = s.is_encrypted ? "AES-256-GCM encrypted" : `${s.cookies_count || 0} cookies · ${s.auth_status || "saved"}`;

      meta.appendChild(title);
      meta.appendChild(sub);

      const btnInject = document.createElement("button");
      btnInject.className = "icon-btn";
      btnInject.style.marginLeft = "auto";
      btnInject.textContent = "Inject";
      btnInject.addEventListener("click", async () => {
        const proxyUrl = settingProxyUrl.value.trim() || "http://127.0.0.1:9222";
        showStatus(vaultStatusEl, `Loading ${s.name} from proxy...`, "loading");
        try {
          const resp = await fetch(`${proxyUrl}/api/session/inject`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: s.name }),
          });
          if (resp.ok) {
            const sessData = await resp.json();
            importedParsedSession = sessData;
            document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
            document.querySelectorAll(".view-tab").forEach((t) => t.classList.remove("active"));
            document.getElementById("nav-import").classList.add("active");
            document.getElementById("tab-import").classList.add("active");
            parseAndPreviewSession(JSON.stringify(sessData), s.filename || `${s.name}.tokenade`);
          } else {
            showStatus(vaultStatusEl, "Failed to load session from proxy", "error");
          }
        } catch (err) {
          showStatus(vaultStatusEl, `Error: ${err.message}`, "error");
        }
      });

      card.appendChild(meta);
      card.appendChild(btnInject);
      vaultSessionsList.appendChild(card);
    }
  }

  vaultSearchInput.addEventListener("input", renderVaultList);
  btnRefreshVault.addEventListener("click", fetchVaultSessions);

  btnStoreActiveToVault.addEventListener("click", async () => {
    if (!extractedSession) {
      showStatus(vaultStatusEl, "No active session to store", "error");
      return;
    }
    const proxyUrl = settingProxyUrl.value.trim() || "http://127.0.0.1:9222";
    showStatus(vaultStatusEl, "Packaging and storing session via proxy...", "loading");
    try {
      const resp = await fetch(`${proxyUrl}/api/session/store`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(extractedSession),
      });
      if (resp.ok) {
        const res = await resp.json();
        showStatus(vaultStatusEl, `Session stored to ${res.path}!`, "success");
        setTimeout(fetchVaultSessions, 800);
      } else {
        showStatus(vaultStatusEl, `Store failed: HTTP ${resp.status}`, "error");
      }
    } catch (e) {
      showStatus(vaultStatusEl, `Could not connect to proxy: ${e.message}`, "error");
    }
  });

  // ── Health Diagnostics Rendering ─────────────────────────────────────────

  function renderHealthDiagnostics() {
    healthSiteName.textContent = currentDomain ? `${currentDomain} Diagnostics` : "Session Health";
    const now = Date.now() / 1000;
    const cookies = activeCookiesList || [];
    const cookieNames = new Set(cookies.map((c) => c.name));

    healthCriticalBody.innerHTML = "";
    if (activeMatchedSite && activeMatchedSite.critical?.length) {
      let presentCount = 0;
      for (const name of activeMatchedSite.critical) {
        const tr = document.createElement("tr");
        const tdName = document.createElement("td");
        tdName.textContent = name;
        tdName.style.fontWeight = "600";

        const tdStatus = document.createElement("td");
        const isPresent = cookieNames.has(name);
        if (isPresent) {
          presentCount++;
          tdStatus.innerHTML = '<span class="tag sec" style="color:var(--success-text);">PRESENT</span>';
        } else {
          tdStatus.innerHTML = '<span class="tag http" style="color:var(--error-text);">MISSING</span>';
        }

        tr.appendChild(tdName);
        tr.appendChild(tdStatus);
        healthCriticalBody.appendChild(tr);
      }

      const score = Math.round((presentCount / activeMatchedSite.critical.length) * 100);
      healthGradeBadge.textContent = `${score}%`;
      healthGradeBadge.className = score >= 50 ? "site-badge known" : "site-badge";
      healthAuthVerdict.textContent = score >= 50
        ? `Authenticated session (${presentCount}/${activeMatchedSite.critical.length} critical cookies present)`
        : `Unauthenticated / Expired (${presentCount}/${activeMatchedSite.critical.length} critical cookies)`;
    } else {
      healthCriticalBody.innerHTML = '<tr><td colspan="2" style="text-align:center; color:var(--text-muted); padding:10px;">Generic site — heuristics applied</td></tr>';
      const expired = cookies.filter((c) => c.expirationDate && c.expirationDate < now).length;
      const valid = cookies.length - expired;
      const score = cookies.length ? Math.round((valid / cookies.length) * 100) : 0;
      healthGradeBadge.textContent = `${score}%`;
      healthAuthVerdict.textContent = `${valid} valid, ${expired} expired cookies`;
    }

    // Partition Map
    healthOriginsList.innerHTML = "";
    const storageOrigins = extractedSession?.metadata?.storage_origins || [];
    if (storageOrigins.length) {
      for (const orig of storageOrigins) {
        const div = document.createElement("div");
        div.style.marginBottom = "4px";
        div.innerHTML = `<span class="tag sec">ORIGIN</span> <strong>${orig}</strong>`;
        healthOriginsList.appendChild(div);
      }
    } else {
      healthOriginsList.innerHTML = `<span style="color:var(--text-muted);">No secondary storage origins</span>`;
    }
  }

  async function checkProxyBridge() {
    const proxyUrl = settingProxyUrl.value.trim() || "http://127.0.0.1:9222";
    try {
      const resp = await fetch(`${proxyUrl}/api/status`, { method: "GET", signal: AbortSignal.timeout(1500) });
      if (resp.ok) {
        bridgeStatusDot.className = "status-dot";
        bridgeStatusText.textContent = "Proxy Online";
        return;
      }
    } catch (_) {}
    bridgeStatusDot.className = "status-dot offline";
    bridgeStatusText.textContent = "Proxy Offline";
  }

  btnSendToProxy.addEventListener("click", async () => {
    if (!extractedSession) return;
    const proxyUrl = settingProxyUrl.value.trim() || "http://127.0.0.1:9222";
    showStatus(settingsStatusEl, `Sending session to ${proxyUrl}...`, "loading");
    try {
      const resp = await fetch(`${proxyUrl}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(extractedSession),
        signal: AbortSignal.timeout(3000),
      });
      if (resp.ok) {
        showStatus(settingsStatusEl, "Active session sent to Tokenade proxy successfully!", "success");
      } else {
        showStatus(settingsStatusEl, `Proxy returned error status: ${resp.status}`, "error");
      }
    } catch (e) {
      showStatus(settingsStatusEl, `Could not connect to proxy at ${proxyUrl}: ${e.message}`, "error");
    }
  });

  // ── Programmatic & Test Bridge ──────────────────────────────────────────

  window.TokenadePopup = {
    handleImportFile,
    parseAndPreviewSession,
    loadEncryptedBytes: (bytes, filename = "encrypted.tokenade") => {
      importedRawBytes = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
      importPassGroup.style.display = "block";
      importTypeBadge.textContent = "ENCRYPTED";
      importTypeBadge.className = "site-badge known";
      importSiteName.textContent = filename;
      importDetails.textContent = "Encrypted Tokenade v2 format — enter password to decrypt";
      importPreviewCard.style.display = "block";
      btnInjectSession.disabled = false;
    },
    refreshSessionData,
    renderVaultList,
    setVaultStoredSessions: (list) => {
      vaultStoredSessions = list;
      renderVaultList();
    },
    renderHealthDiagnostics,
    getExtractedSession: () => extractedSession,
    getActiveCookies: () => activeCookiesList,
  };

  // ── Initialize ───────────────────────────────────────────────────────────

  await loadPreferences();
  const ok = await initTab();
  if (ok) {
    await refreshSessionData();
  }
  checkProxyBridge();
});
