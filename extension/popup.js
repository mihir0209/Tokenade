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
  const optSessionStorage = document.getElementById("opt-session-storage");
  const formatSelect = document.getElementById("opt-format");
  const domainPicker = document.getElementById("domain-picker");
  const domainSearch = document.getElementById("domain-search");
  const domainList = document.getElementById("domain-list");
  const pickerSelectAll = document.getElementById("picker-select-all");
  const pickerSelectNone = document.getElementById("picker-select-none");

  let currentTab = null;
  let currentDomain = "";
  let sessionData = null;
  // Domain selection mode: "all" (empty selection, everything included) or
  // "selected" (only the domains listed in selectedDomains).
  let domainFilter = "all";
  let selectedDomains = new Set();

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

  function domainOf(cookie) {
    const d = cookie.domain || "";
    return d.startsWith(".") ? d.slice(1) : d;
  }

  function renderDomainPicker(allCookies) {
    const counts = new Map();
    for (const c of allCookies) {
      const d = domainOf(c);
      counts.set(d, (counts.get(d) || 0) + 1);
    }
    const query = (domainSearch.value || "").trim().toLowerCase();
    const domains = Array.from(counts.keys())
      .filter((d) => !query || d.includes(query))
      .sort();
    domainList.textContent = "";
    if (domains.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = query ? "No domains match the filter" : "No cookies found";
      domainList.appendChild(empty);
      return;
    }
    for (const d of domains) {
      const label = document.createElement("label");
      label.className = "picker-item";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = d;
      cb.checked = domainFilter === "all" || selectedDomains.has(d);
      const span = document.createElement("span");
      span.textContent = d;
      const count = document.createElement("span");
      count.className = "count";
      count.textContent = String(counts.get(d));
      label.appendChild(cb);
      label.appendChild(span);
      label.appendChild(count);
      domainList.appendChild(label);
    }
  }

  function allListedDomains() {
    return Array.from(
      domainList.querySelectorAll("input[type='checkbox']")
    ).map((i) => i.value);
  }

  async function extractCookies() {
    const domain = currentDomain;
    const allDomains = optAllDomains.checked;

    let cookies;
    if (allDomains) {
      cookies = await chrome.cookies.getAll({});
      renderDomainPicker(cookies);
      if (domainFilter === "selected" && selectedDomains.size > 0) {
        cookies = cookies.filter((c) => selectedDomains.has(domainOf(c)));
      }
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

  async function extractSessionStorage() {
    if (!optSessionStorage?.checked || !currentTab?.id) {
      return {};
    }
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: currentTab.id },
        func: () => {
          const out = {};
          try {
            for (let i = 0; i < sessionStorage.length; i++) {
              const k = sessionStorage.key(i);
              if (k != null) out[k] = sessionStorage.getItem(k);
            }
          } catch (_) {
            /* opaque origin */
          }
          return out;
        },
      });
      return (results && results[0] && results[0].result) || {};
    } catch (e) {
      console.warn("sessionStorage capture failed", e);
      return {};
    }
  }

  async function extractIndexedDB() {
    if (!currentTab?.id) return {};
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: currentTab.id },
        func: async () => {
          if (!window.indexedDB || !indexedDB.databases) return {};
          const out = {};
          try {
            const dbs = await indexedDB.databases();
            for (const dbInfo of dbs) {
              if (!dbInfo.name) continue;
              await new Promise((resolve) => {
                const req = indexedDB.open(dbInfo.name, dbInfo.version);
                req.onsuccess = async (e) => {
                  const db = e.target.result;
                  const storeNames = Array.from(db.objectStoreNames);
                  if (storeNames.length === 0) { db.close(); resolve(); return; }
                  out[dbInfo.name] = { version: dbInfo.version, stores: {} };
                  try {
                    const tx = db.transaction(storeNames, "readonly");
                    for (const sName of storeNames) {
                      const store = tx.objectStore(sName);
                      const records = {};
                      const cursorReq = store.openCursor();
                      cursorReq.onsuccess = (ev) => {
                        const cursor = ev.target.result;
                        if (cursor) {
                          try { records[String(cursor.key)] = cursor.value; } catch(_) {}
                          cursor.continue();
                        }
                      };
                    }
                    tx.oncomplete = () => { db.close(); resolve(); };
                    tx.onerror = () => { db.close(); resolve(); };
                  } catch(_) { db.close(); resolve(); }
                };
                req.onerror = () => resolve();
              });
            }
          } catch(_) {}
          return out;
        }
      });
      return (results && results[0] && results[0].result) || {};
    } catch(e) {
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

  function buildTokenadeSession(cookies, localStorageMap, sessionStorageMap, indexedDBMap) {
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
    const ssCount = Object.keys(sessionStorageMap || {}).length;
    const idbCount = Object.keys(indexedDBMap || {}).length;
    const storage = { local: {}, session: {}, indexeddb: {} };
    if (lsCount > 0) {
      storage.local[origin] = { ...localStorageMap };
    }
    if (ssCount > 0) {
      storage.session[origin] = { ...sessionStorageMap };
    }
    if (idbCount > 0) {
      storage.indexeddb[origin] = { ...indexedDBMap };
    }

    const flatLs = {};
    for (const [k, v] of Object.entries(localStorageMap || {})) {
      flatLs[`${currentDomain}:${k}`] = v;
    }

    const selectedDomainCount = optAllDomains.checked
      ? (domainFilter === "all"
          ? domainList.querySelectorAll("input[type='checkbox']").length || 1
          : selectedDomains.size || 1)
      : 1;

    // Heuristic: a session with valid (non-expired) cookies is treated as
    // logged in; anything weaker stays "unknown" rather than claiming health.
    const authStatus = total > 0 && health >= 50 ? "logged_in" : "unknown";

    return {
      version: "3.0",
      site_name: optAllDomains.checked ? "all-domains" : currentDomain,
      auth_status: authStatus,
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
        session_storage_count: ssCount,
        notes: [
          "Exported via browser extension (no SQLite lock).",
          "fingerprint is null — extension cannot capture donor TLS/JA3; use CLI export --collect-fingerprint when needed.",
          "HttpOnly cookies are included (chrome.cookies API).",
          "Web storage includes both localStorage and sessionStorage.",
          "auth_status is a cookie-health heuristic (logged_in only when valid cookies exist).",
        ],
      },
      _stats: { total, expired, health, storage: lsCount + ssCount, domains: selectedDomainCount },
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
    const domainNote = optAllDomains.checked
      ? ` · ${stats.domains} domains selected`
      : "";
    cookieCountEl.textContent = `${stats.total} cookies` +
      (stats.storage ? ` · ${stats.storage} storage keys` : "") + domainNote;

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
    const allDomains = optAllDomains.checked;
    domainPicker.classList.toggle("visible", allDomains);
    if (allDomains) {
      domainEl.textContent = domainFilter === "all"
        ? "All domains"
        : selectedDomains.size === 1
          ? Array.from(selectedDomains)[0]
          : `${selectedDomains.size} domains`;
    } else {
      domainEl.textContent = currentDomain;
    }
    const cookies = await extractCookies();
    rawCookies = cookies;
    const ls = await extractLocalStorage();
    const ss = await extractSessionStorage();
    const idb = await extractIndexedDB();
    sessionData = buildTokenadeSession(cookies, ls, ss, idb);
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

  optAllDomains.addEventListener("change", () => {
    if (!optAllDomains.checked) {
      domainFilter = "all";
      selectedDomains = new Set();
      domainSearch.value = "";
    }
    onOptionChange();
  });
  if (optLocalStorage) optLocalStorage.addEventListener("change", onOptionChange);
  if (optSessionStorage) optSessionStorage.addEventListener("change", onOptionChange);

  domainSearch.addEventListener("input", () => {
    if (rawCookies.length > 0) renderDomainPicker(rawCookies);
  });

  domainList.addEventListener("change", (e) => {
    const cb = e.target;
    if (!cb.matches("input[type='checkbox']")) return;
    if (domainFilter === "all" && !cb.checked) {
      // First manual deselection: switch to explicit selection seeded with
      // every listed domain, then drop the one the user uncheckd.
      domainFilter = "selected";
      selectedDomains = new Set(allListedDomains());
      selectedDomains.delete(cb.value);
    } else if (domainFilter === "selected") {
      if (cb.checked) {
        selectedDomains.add(cb.value);
      } else {
        selectedDomains.delete(cb.value);
      }
    }
    onOptionChange();
  });

  pickerSelectAll.addEventListener("click", () => {
    domainFilter = "all";
    selectedDomains = new Set();
    onOptionChange();
  });

  pickerSelectNone.addEventListener("click", () => {
    domainFilter = "selected";
    selectedDomains = new Set(allListedDomains());
    onOptionChange();
  });
});
