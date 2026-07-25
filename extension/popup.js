/**
 * Tokenade Session Exporter — Popup
 *
 * Default export format: .tokenade (session packager shape).
 * Honest limits: cookies (+ optional page localStorage). No donor TLS fingerprint.
 */

document.addEventListener("DOMContentLoaded", async () => {
  const domainEl = document.getElementById("domain");
  const cookieCountEl = document.getElementById("cookie-count");
  const totalValue = document.getElementById("total-value");
  const expiredValue = document.getElementById("expired-value");
  const healthValue = document.getElementById("health-value");
  const storageValue = document.getElementById("storage-value");
  const statExpired = document.getElementById("stat-expired");
  const statHealth = document.getElementById("stat-health");
  const btnDownload = document.getElementById("btn-download");
  const btnClipboard = document.getElementById("btn-clipboard");
  const statusEl = document.getElementById("status");
  const optAllDomains = document.getElementById("opt-all-domains");
  const optLocalStorage = document.getElementById("opt-local-storage");
  const formatSelect = document.getElementById("opt-format");

  let currentTab = null;
  let currentDomain = "";
  let sessionData = null;

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTab = tab;
    if (!tab?.url || tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) {
      domainEl.textContent = "Open a normal website tab first";
      cookieCountEl.textContent = "Cannot read cookies on browser internal pages";
      return;
    }
    const url = new URL(tab.url);
    currentDomain = url.hostname;
    domainEl.textContent = currentDomain;
  } catch (e) {
    domainEl.textContent = "Error getting tab";
    return;
  }

  function getRelatedDomains(domain) {
    const domains = [domain];
    const parts = domain.split(".");
    for (let i = 0; i < parts.length - 1; i++) {
      domains.push("." + parts.slice(i).join("."));
    }
    return domains;
  }

  async function extractCookies() {
    const domain = currentDomain;
    const allDomains = optAllDomains.checked;

    let cookies;
    if (allDomains) {
      cookies = await chrome.cookies.getAll({});
    } else {
      const domains = getRelatedDomains(domain);
      const allCookies = [];
      for (const d of domains) {
        const dc = await chrome.cookies.getAll({ domain: d });
        allCookies.push(...dc);
      }
      const seen = new Set();
      cookies = allCookies.filter((c) => {
        const key = `${c.name}|${c.domain}|${c.path}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    }
    return cookies;
  }

  async function extractLocalStorage() {
    if (!optLocalStorage?.checked || !currentTab?.id) {
      return {};
    }
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: currentTab.id },
        func: () => {
          const out = {};
          try {
            for (let i = 0; i < localStorage.length; i++) {
              const k = localStorage.key(i);
              if (k != null) out[k] = localStorage.getItem(k);
            }
          } catch (_) {
            /* opaque origin */
          }
          return out;
        },
      });
      return (results && results[0] && results[0].result) || {};
    } catch (e) {
      console.warn("localStorage capture failed", e);
      return {};
    }
  }

  function mapSameSite(v) {
    if (v === "no_restriction" || v === "none") return "None";
    if (v === "lax") return "Lax";
    if (v === "strict") return "Strict";
    return "Lax";
  }

  function normalizeCookies(cookies) {
    const now = Date.now() / 1000;
    let expired = 0;
    const tokenadeCookies = cookies.map((c) => {
      let expires = c.expirationDate || 0;
      if (expires > 1e12) {
        expires = Math.floor(expires / 1000);
      } else if (expires > 0) {
        expires = Math.floor(expires);
      }
      if (expires > 0 && expires < now) expired++;
      return {
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path || "/",
        secure: !!c.secure,
        httpOnly: !!c.httpOnly,
        sameSite: mapSameSite(c.sameSite),
        ...(expires > 0 ? { expires } : {}),
      };
    });
    return { tokenadeCookies, expired, total: cookies.length };
  }

  function buildTokenadeSession(cookies, localStorageMap) {
    const { tokenadeCookies, expired, total } = normalizeCookies(cookies);
    const health = total > 0 ? ((total - expired) / total) * 100 : 0;
    const origin = currentTab?.url
      ? (() => {
          try {
            const u = new URL(currentTab.url);
            return `${u.protocol}//${u.host}`;
          } catch {
            return `https://${currentDomain}`;
          }
        })()
      : `https://${currentDomain}`;

    const lsCount = Object.keys(localStorageMap || {}).length;
    const storage = { local: {}, session: {} };
    if (lsCount > 0) {
      storage.local[origin] = { ...localStorageMap };
    }

    const flatLs = {};
    for (const [k, v] of Object.entries(localStorageMap || {})) {
      flatLs[`${currentDomain}:${k}`] = v;
    }

    return {
      version: "3.0",
      site_name: currentDomain,
      auth_status: "unknown",
      created_at: new Date().toISOString(),
      source_device: {
        browser: "chrome-extension",
        profile: "active-tab",
        platform: navigator.platform || "unknown",
        hostname: "anonymous",
      },
      cookies: tokenadeCookies,
      tokens: [],
      storage,
      local_storage: flatLs,
      fingerprint: null,
      tls_profile: null,
      metadata: {
        extraction_method: "extension",
        source: "tokenade-extension",
        source_format: "tokenade",
        domain: currentDomain,
        page_url: currentTab?.url || "",
        exported_at: new Date().toISOString(),
        cookie_count: total,
        local_storage_count: lsCount,
        notes: [
          "Exported via browser extension (no SQLite lock).",
          "fingerprint is null — extension cannot capture donor TLS/JA3; use CLI export --collect-fingerprint when needed.",
          "HttpOnly cookies are included (chrome.cookies API).",
        ],
      },
      _stats: { total, expired, health, storage: lsCount },
    };
  }

  function buildNetscape(cookies) {
    const lines = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""];
    for (const c of cookies) {
      let expires = c.expirationDate || 0;
      if (expires > 1e12) expires = Math.floor(expires / 1000);
      else expires = Math.floor(expires || 0);
      const domain = c.domain || "";
      const includeSub = domain.startsWith(".") ? "TRUE" : "FALSE";
      const secure = c.secure ? "TRUE" : "FALSE";
      lines.push(
        [domain, includeSub, c.path || "/", secure, String(expires), c.name, c.value].join("\t")
      );
    }
    return lines.join("\n") + "\n";
  }

  function buildCookieEditorJson(cookies) {
    return cookies.map((c) => {
      let expires = c.expirationDate || 0;
      if (expires > 1e12) expires = expires / 1000;
      return {
        domain: c.domain,
        expirationDate: expires || undefined,
        hostOnly: !String(c.domain || "").startsWith("."),
        httpOnly: !!c.httpOnly,
        name: c.name,
        path: c.path || "/",
        sameSite:
          c.sameSite === "no_restriction"
            ? "no_restriction"
            : c.sameSite === "strict"
              ? "strict"
              : "lax",
        secure: !!c.secure,
        session: !c.expirationDate,
        storeId: "0",
        value: c.value,
      };
    });
  }

  function serializeExport(session, cookies) {
    const fmt = (formatSelect && formatSelect.value) || "tokenade";
    if (fmt === "netscape") {
      return {
        body: buildNetscape(cookies),
        filename: `${currentDomain}.txt`,
        mime: "text/plain",
      };
    }
    if (fmt === "cookie-editor") {
      return {
        body: JSON.stringify(buildCookieEditorJson(cookies), null, 2),
        filename: `${currentDomain}.cookies.json`,
        mime: "application/json",
      };
    }
    // default: richest portable format
    const output = { ...session };
    delete output._stats;
    return {
      body: JSON.stringify(output, null, 2),
      filename: `${currentDomain}.tokenade`,
      mime: "application/json",
    };
  }

  function updateStats(session) {
    const stats = session._stats;
    totalValue.textContent = stats.total;
    expiredValue.textContent = stats.expired;
    healthValue.textContent = Math.round(stats.health) + "%";
    if (storageValue) storageValue.textContent = String(stats.storage || 0);
    cookieCountEl.textContent = `${stats.total} cookies` +
      (stats.storage ? ` · ${stats.storage} localStorage keys` : "");

    statExpired.classList.toggle("warn", stats.expired > 0);
    statHealth.classList.remove("warn", "error");
    if (stats.health < 70) statHealth.classList.add("error");
    else if (stats.health < 90) statHealth.classList.add("warn");

    btnDownload.disabled = stats.total === 0;
    btnClipboard.disabled = stats.total === 0;
  }

  function showStatus(type, message) {
    statusEl.className = `status ${type}`;
    statusEl.textContent = message;
    if (type === "success") {
      setTimeout(() => {
        statusEl.className = "status";
      }, 3000);
    }
  }

  let rawCookies = [];

  async function refresh() {
    const cookies = await extractCookies();
    rawCookies = cookies;
    const ls = await extractLocalStorage();
    sessionData = buildTokenadeSession(cookies, ls);
    updateStats(sessionData);
  }

  try {
    await refresh();
  } catch (e) {
    showStatus("error", "Failed to extract cookies: " + e.message);
  }

  btnDownload.addEventListener("click", async () => {
    if (!sessionData) return;
    try {
      const { body, filename, mime } = serializeExport(sessionData, rawCookies);
      const blob = new Blob([body], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showStatus("success", `Downloaded ${filename}`);
    } catch (e) {
      showStatus("error", "Download failed: " + e.message);
    }
  });

  btnClipboard.addEventListener("click", async () => {
    if (!sessionData) return;
    try {
      const { body } = serializeExport(sessionData, rawCookies);
      await navigator.clipboard.writeText(body);
      showStatus("success", "Copied to clipboard");
    } catch (e) {
      showStatus("error", "Clipboard failed: " + e.message);
    }
  });

  async function onOptionChange() {
    try {
      statusEl.className = "status loading";
      statusEl.textContent = "Re-scanning…";
      await refresh();
      statusEl.className = "status";
    } catch (e) {
      showStatus("error", "Failed: " + e.message);
    }
  }

  optAllDomains.addEventListener("change", onOptionChange);
  if (optLocalStorage) optLocalStorage.addEventListener("change", onOptionChange);
});
