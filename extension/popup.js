/**
 * Tokenade Session Exporter — Popup Script
 * 
 * Extracts cookies from the current tab and generates .tokenade files.
 */

document.addEventListener('DOMContentLoaded', async () => {
  const domainEl = document.getElementById('domain');
  const cookieCountEl = document.getElementById('cookie-count');
  const totalValue = document.getElementById('total-value');
  const expiredValue = document.getElementById('expired-value');
  const healthValue = document.getElementById('health-value');
  const statExpired = document.getElementById('stat-expired');
  const statHealth = document.getElementById('stat-health');
  const btnDownload = document.getElementById('btn-download');
  const btnClipboard = document.getElementById('btn-clipboard');
  const statusEl = document.getElementById('status');
  const optAllDomains = document.getElementById('opt-all-domains');

  let currentTab = null;
  let currentDomain = '';
  let sessionData = null;

  // Get current tab
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTab = tab;
    const url = new URL(tab.url);
    currentDomain = url.hostname;
    domainEl.textContent = currentDomain;
  } catch (e) {
    domainEl.textContent = 'Error getting tab';
    return;
  }

  // Extract cookies
  async function extractCookies() {
    const domain = currentDomain;
    const allDomains = optAllDomains.checked;

    let cookies;
    if (allDomains) {
      cookies = await chrome.cookies.getAll({});
    } else {
      // Get cookies for current domain and parent domains
      const domains = getRelatedDomains(domain);
      const allCookies = [];
      for (const d of domains) {
        const dc = await chrome.cookies.getAll({ domain: d });
        allCookies.push(...dc);
      }
      // Deduplicate
      const seen = new Set();
      cookies = allCookies.filter(c => {
        const key = `${c.name}|${c.domain}|${c.path}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    }

    return cookies;
  }

  // Get related domains (e.g., .google.com, mail.google.com)
  function getRelatedDomains(domain) {
    const domains = [domain];
    const parts = domain.split('.');
    for (let i = 0; i < parts.length - 1; i++) {
      domains.push('.' + parts.slice(i).join('.'));
    }
    return domains;
  }

  // Convert Chrome cookies to .tokenade format
  function buildSession(cookies) {
    const now = Date.now() / 1000;
    let expired = 0;

    const tokenadeCookies = cookies.map(c => {
      // Chrome uses milliseconds, tokenade uses seconds
      let expires = c.expirationDate || 0;
      if (expires > 1262304000000) {
        expires = Math.floor(expires);
      }

      if (expires > 0 && expires < now) {
        expired++;
      }

      return {
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path,
        secure: c.secure,
        httpOnly: c.httpOnly,
        sameSite: c.sameSite === 'no_restriction' ? 'None' : 
                  c.sameSite === 'lax' ? 'Lax' : 
                  c.sameSite === 'strict' ? 'Strict' : 'None',
        expires: expires,
      };
    });

    const total = cookies.length;
    const health = total > 0 ? ((total - expired) / total * 100) : 0;

    return {
      version: '2.0',
      site_name: currentDomain,
      auth_status: 'unknown',
      created_at: new Date().toISOString(),
      cookies: tokenadeCookies,
      local_storage: {},
      metadata: {
        source: 'tokenade-extension',
        domain: currentDomain,
        exported_at: new Date().toISOString(),
      },
      _stats: { total, expired, health }
    };
  }

  // Update UI with stats
  function updateStats(session) {
    const stats = session._stats;
    totalValue.textContent = stats.total;
    expiredValue.textContent = stats.expired;
    healthValue.textContent = Math.round(stats.health) + '%';
    cookieCountEl.textContent = `${stats.total} cookies found`;

    if (stats.expired > 0) {
      statExpired.classList.add('warn');
    }
    if (stats.health < 70) {
      statHealth.classList.add('error');
    } else if (stats.health < 90) {
      statHealth.classList.add('warn');
    }

    btnDownload.disabled = stats.total === 0;
    btnClipboard.disabled = stats.total === 0;
  }

  // Show status message
  function showStatus(type, message) {
    statusEl.className = `status ${type}`;
    statusEl.textContent = message;
    if (type === 'success') {
      setTimeout(() => { statusEl.className = 'status'; }, 3000);
    }
  }

  // Initial extraction
  try {
    const cookies = await extractCookies();
    sessionData = buildSession(cookies);
    updateStats(sessionData);
  } catch (e) {
    showStatus('error', 'Failed to extract cookies: ' + e.message);
  }

  // Download button
  btnDownload.addEventListener('click', async () => {
    if (!sessionData) return;
    try {
      // Remove _stats before saving
      const output = { ...sessionData };
      delete output._stats;
      const json = JSON.stringify(output, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      
      const a = document.createElement('a');
      a.href = url;
      a.download = `${currentDomain}.tokenade`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      showStatus('success', `✅ Downloaded ${currentDomain}.tokenade`);
    } catch (e) {
      showStatus('error', 'Download failed: ' + e.message);
    }
  });

  // Clipboard button
  btnClipboard.addEventListener('click', async () => {
    if (!sessionData) return;
    try {
      const output = { ...sessionData };
      delete output._stats;
      const json = JSON.stringify(output, null, 2);
      await navigator.clipboard.writeText(json);
      showStatus('success', '✅ Copied to clipboard');
    } catch (e) {
      showStatus('error', 'Clipboard failed: ' + e.message);
    }
  });

  // All domains checkbox
  optAllDomains.addEventListener('change', async () => {
    try {
      statusEl.className = 'status loading';
      statusEl.textContent = '⏳ Re-scanning...';
      const cookies = await extractCookies();
      sessionData = buildSession(cookies);
      updateStats(sessionData);
      statusEl.className = 'status';
    } catch (e) {
      showStatus('error', 'Failed: ' + e.message);
    }
  });
});
