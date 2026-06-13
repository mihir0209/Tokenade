// Tokenade Browser Extension - Background Script

// Listen for extension installation
browser.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('Tokenade extension installed');
    
    // Set default settings
    browser.storage.local.set({
      proxyUrl: 'http://127.0.0.1:9222',
      includeLocalstorage: false,
      encrypt: false,
    });
  }
});

// Listen for messages from content script or popup
browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_COOKIES') {
    // Get cookies for a URL
    browser.cookies.getAll({ url: message.url }).then(cookies => {
      sendResponse({ cookies });
    });
    return true; // Keep message channel open for async response
  }
  
  if (message.type === 'GETLocalStorage') {
    // Get localStorage from active tab
    browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
      if (tabs[0]) {
        browser.scripting.executeScript({
          target: { tabId: tabs[0].id },
          func: () => {
            const data = {};
            for (let i = 0; i < window.localStorage.length; i++) {
              const key = window.localStorage.key(i);
              data[key] = window.localStorage.getItem(key);
            }
            return data;
          }
        }).then(results => {
          sendResponse({ localStorage: results[0].result });
        });
      }
    });
    return true;
  }
  
  if (message.type === 'SEND_TO_PROXY') {
    // Send session to proxy server
    const proxyUrl = message.proxyUrl || 'http://127.0.0.1:9222';
    
    fetch(`${proxyUrl}/api/session/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.session),
    })
    .then(response => {
      if (!response.ok) throw new Error(`Proxy returned ${response.status}`);
      return response.json();
    })
    .then(data => {
      sendResponse({ success: true, data });
    })
    .catch(error => {
      sendResponse({ success: false, error: error.message });
    });
    return true;
  }
});

// Context menu for quick export
browser.runtime.onInstalled.addListener(() => {
  browser.contextMenus.create({
    id: 'tokenade-export',
    title: 'Export session with Tokenade',
    contexts: ['page'],
  });
  
  browser.contextMenus.create({
    id: 'tokenade-send',
    title: 'Send session to Tokenade proxy',
    contexts: ['page'],
  });
});

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'tokenade-export' || info.menuItemId === 'tokenade-send') {
    const cookies = await browser.cookies.getAll({ url: tab.url });
    const url = new URL(tab.url);
    
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
    };
    
    if (info.menuItemId === 'tokenade-export') {
      // Download as file
      const blob = new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' });
      const downloadUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `${session.site_name}.tokenade`;
      a.click();
      URL.revokeObjectURL(downloadUrl);
    } else {
      // Send to proxy
      const settings = await browser.storage.local.get(['proxyUrl']);
      const proxyUrl = settings.proxyUrl || 'http://127.0.0.1:9222';
      
      try {
        const response = await fetch(`${proxyUrl}/api/session/import`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(session),
        });
        
        if (!response.ok) throw new Error(`Proxy returned ${response.status}`);
        
        browser.notifications.create({
          type: 'basic',
          title: 'Tokenade',
          message: `Session sent to proxy (${cookies.length} cookies)`,
        });
      } catch (error) {
        browser.notifications.create({
          type: 'basic',
          title: 'Tokenade Error',
          message: `Failed to send session: ${error.message}`,
        });
      }
    }
  }
});
