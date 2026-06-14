document.addEventListener('DOMContentLoaded', async () => {
  const siteNameEl = document.getElementById('site-name');
  const cookieCountEl = document.getElementById('cookie-count');
  const proxyUrlInput = document.getElementById('proxy-url');
  const includeLocalstorageCheckbox = document.getElementById('include-localstorage');
  const encryptCheckbox = document.getElementById('encrypt');
  const passwordGroup = document.getElementById('password-group');
  const passwordInput = document.getElementById('password');
  const exportBtn = document.getElementById('export-btn');
  const sendProxyBtn = document.getElementById('send-proxy-btn');
  const refreshBtn = document.getElementById('refresh-btn');
  const statusEl = document.getElementById('status');
  const proxyDot = document.getElementById('proxy-dot');
  const proxyStatusText = document.getElementById('proxy-status-text');
  const historySection = document.getElementById('history-section');
  const historyList = document.getElementById('history-list');

  // Load saved settings
  const settings = await browser.storage.local.get(['proxyUrl', 'includeLocalstorage', 'encrypt']);
  if (settings.proxyUrl) proxyUrlInput.value = settings.proxyUrl;
  if (settings.includeLocalstorage) includeLocalstorageCheckbox.checked = settings.includeLocalstorage;
  if (settings.encrypt) encryptCheckbox.checked = settings.encrypt;

  // Toggle password field
  encryptCheckbox.addEventListener('change', () => {
    passwordGroup.classList.toggle('hidden', !encryptCheckbox.checked);
  });

  // Check proxy connection
  async function checkProxy() {
    try {
      const response = await fetch(`${proxyUrlInput.value}/api/health`, { method: 'GET' });
      if (response.ok) {
        const data = await response.json();
        proxyDot.classList.add('connected');
        proxyStatusText.textContent = `Proxy connected (v${data.version || '?'})`;
        return true;
      }
    } catch (e) {
      // Proxy not running
    }
    proxyDot.classList.remove('connected');
    proxyStatusText.textContent = 'Proxy not running';
    return false;
  }

  // Show status
  function showStatus(message, type = 'info') {
    statusEl.innerHTML = message;
    statusEl.className = `status status-${type}`;
    statusEl.classList.remove('hidden');
  }

  function showStatusLoading(message) {
    showStatus(`<span class="spinner"></span>${message}`, 'info');
  }

  // Hide status
  function hideStatus() {
    statusEl.classList.add('hidden');
  }

  // Save settings
  async function saveSettings() {
    await browser.storage.local.set({
      proxyUrl: proxyUrlInput.value,
      includeLocalstorage: includeLocalstorageCheckbox.checked,
      encrypt: encryptCheckbox.checked,
    });
  }

  // Get current tab info
  let currentTab;
  let currentUrl;
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    currentTab = tab;
    currentUrl = new URL(tab.url);
    siteNameEl.textContent = currentUrl.hostname;

    // Get cookie count
    const cookies = await browser.cookies.getAll({ url: tab.url });
    cookieCountEl.textContent = cookies.length;
  } catch (e) {
    siteNameEl.textContent = 'Unable to detect';
    cookieCountEl.textContent = '0';
  }

  // Load export history
  const history = await browser.storage.local.get(['exportHistory']);
  if (history.exportHistory && history.exportHistory.length > 0) {
    historySection.classList.remove('hidden');
    const recent = history.exportHistory.slice(-5).reverse();
    historyList.innerHTML = recent.map(h =>
      `<div class="history-item"><span class="history-site">${h.site}</span><span class="history-time">${h.time}</span></div>`
    ).join('');
  }

  // Add to history
  async function addToHistory(site, cookieCount) {
    const hist = (await browser.storage.local.get(['exportHistory'])).exportHistory || [];
    hist.push({ site, cookies: cookieCount, time: new Date().toLocaleTimeString() });
    if (hist.length > 20) hist.splice(0, hist.length - 20);
    await browser.storage.local.set({ exportHistory: hist });
  }

  // Extract session data from current tab
  async function extractSession() {
    const cookies = await browser.cookies.getAll({ url: currentTab.url });

    let localStorage = null;
    if (includeLocalstorageCheckbox.checked) {
      try {
        const results = await browser.scripting.executeScript({
          target: { tabId: currentTab.id },
          func: () => {
            const data = {};
            for (let i = 0; i < window.localStorage.length; i++) {
              const key = window.localStorage.key(i);
              data[key] = window.localStorage.getItem(key);
            }
            return data;
          }
        });
        localStorage = results[0].result;
      } catch (e) {
        console.warn('Failed to get localStorage:', e);
      }
    }

    return {
      version: '3.0',
      created_at: new Date().toISOString(),
      site_name: currentUrl.hostname.replace(/\./g, '_'),
      source_device: {
        browser: 'chrome',
        platform: 'linux',
        browser_version: 'extension-export',
      },
      tls_profile: {
        browser: 'chrome',
        version: '131.0',
        platform: 'linux',
      },
      cookies: cookies.map(c => ({
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path,
        secure: c.secure,
        httpOnly: c.httpOnly,
        sameSite: c.sameSite,
        expires: c.expirationDate,
      })),
      local_storage: localStorage,
      auth_status: 'unknown',
    };
  }

  // Export session
  exportBtn.addEventListener('click', async () => {
    try {
      await saveSettings();
      showStatusLoading('Extracting cookies...');

      const session = await extractSession();
      const cookieCount = session.cookies.length;

      // Download as file
      const blob = new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' });
      const downloadUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `${session.site_name}.tokenade`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(downloadUrl);

      await addToHistory(session.site_name, cookieCount);
      showStatus(`Exported ${cookieCount} cookies`, 'success');
    } catch (error) {
      showStatus(`Export failed: ${error.message}`, 'error');
    }
  });

  // Send to proxy
  sendProxyBtn.addEventListener('click', async () => {
    try {
      await saveSettings();
      showStatusLoading('Sending to proxy...');

      const proxyConnected = await checkProxy();
      if (!proxyConnected) {
        showStatus('Proxy not running — start with <code>tokenade proxy -s session.tokenade</code>', 'error');
        return;
      }

      const session = await extractSession();
      const proxyUrl = proxyUrlInput.value;

      const response = await fetch(`${proxyUrl}/api/session/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(session),
      });

      if (!response.ok) {
        throw new Error(`Proxy returned ${response.status}`);
      }

      await addToHistory(session.site_name, session.cookies.length);
      showStatus(`Sent ${session.cookies.length} cookies to proxy`, 'success');
    } catch (error) {
      showStatus(`Send failed: ${error.message}`, 'error');
    }
  });

  // Refresh button
  refreshBtn.addEventListener('click', async () => {
    try {
      if (!currentTab) return;
      const cookies = await browser.cookies.getAll({ url: currentTab.url });
      cookieCountEl.textContent = cookies.length;
      await checkProxy();
      showStatus('Refreshed', 'info');
      setTimeout(hideStatus, 1500);
    } catch (e) {
      showStatus(`Refresh failed: ${e.message}`, 'error');
    }
  });

  // Auto-check proxy on load
  await checkProxy();
});
