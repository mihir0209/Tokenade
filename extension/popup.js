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
  const statusEl = document.getElementById('status');
  
  // Load saved settings
  const settings = await browser.storage.local.get(['proxyUrl', 'includeLocalstorage', 'encrypt']);
  if (settings.proxyUrl) proxyUrlInput.value = settings.proxyUrl;
  if (settings.includeLocalstorage) includeLocalstorageCheckbox.checked = settings.includeLocalstorage;
  if (settings.encrypt) encryptCheckbox.checked = settings.encrypt;
  
  // Toggle password field
  encryptCheckbox.addEventListener('change', () => {
    passwordGroup.classList.toggle('hidden', !encryptCheckbox.checked);
  });
  
  // Get current tab info
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  const url = new URL(tab.url);
  siteNameEl.textContent = url.hostname;
  
  // Get cookie count
  const cookies = await browser.cookies.getAll({ url: tab.url });
  cookieCountEl.textContent = cookies.length;
  
  // Show status
  function showStatus(message, type = 'info') {
    statusEl.textContent = message;
    statusEl.className = `status status-${type}`;
    statusEl.classList.remove('hidden');
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
  
  // Export session
  exportBtn.addEventListener('click', async () => {
    try {
      await saveSettings();
      showStatus('Exporting session...', 'info');
      
      // Get all cookies for current tab
      const cookies = await browser.cookies.getAll({ url: tab.url });
      
      // Get localStorage if enabled
      let localStorage = null;
      if (includeLocalstorageCheckbox.checked) {
        try {
          const results = await browser.scripting.executeScript({
            target: { tabId: tab.id },
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
      
      // Build session object
      const session = {
        version: '2.0',
        created_at: new Date().toISOString(),
        site_name: url.hostname.replace(/\./g, '_'),
        source_device: {
          browser: 'chrome',
          platform: navigator.platform,
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
      };
      
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
      
      showStatus(`Exported ${cookies.length} cookies`, 'success');
      
    } catch (error) {
      showStatus(`Export failed: ${error.message}`, 'error');
    }
  });
  
  // Send to proxy
  sendProxyBtn.addEventListener('click', async () => {
    try {
      await saveSettings();
      showStatus('Sending to proxy...', 'info');
      
      // Get all cookies for current tab
      const cookies = await browser.cookies.getAll({ url: tab.url });
      
      // Get localStorage if enabled
      let localStorage = null;
      if (includeLocalstorageCheckbox.checked) {
        try {
          const results = await browser.scripting.executeScript({
            target: { tabId: tab.id },
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
      
      // Build session object
      const session = {
        version: '2.0',
        created_at: new Date().toISOString(),
        site_name: url.hostname.replace(/\./g, '_'),
        source_device: {
          browser: 'chrome',
          platform: navigator.platform,
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
      };
      
      // Send to proxy
      const proxyUrl = proxyUrlInput.value;
      const response = await fetch(`${proxyUrl}/api/session/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(session),
      });
      
      if (!response.ok) {
        throw new Error(`Proxy returned ${response.status}`);
      }
      
      showStatus(`Sent ${cookies.length} cookies to proxy`, 'success');
      
    } catch (error) {
      showStatus(`Send failed: ${error.message}`, 'error');
    }
  });
});
