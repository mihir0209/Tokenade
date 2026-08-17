/**
 * Tokenade Session Exporter — Background Service Worker
 * 
 * Handles extension lifecycle and background tasks.
 */

// Extension install handler
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('Tokenade Session Exporter installed');
  }
});

// Handle messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'getCookies') {
    chrome.cookies.getAll(message.options || {}, (cookies) => {
      sendResponse({ cookies });
    });
    return true; // Keep channel open for async response
  }

  if (message.type === 'SEND_TO_PROXY') {
    // Fetched from the service worker so HTTPS pages can reach the local
    // (http://127.0.0.1) Tokenade proxy without mixed-content blocking.
    if (!message.proxyUrl) {
      sendResponse({ success: false, error: 'missing proxyUrl' });
      return false;
    }
    fetch(message.proxyUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.session || {}),
    })
      .then(async (resp) => {
        let data = null;
        try {
          data = await resp.json();
        } catch (_) { /* non-JSON body */ }
        sendResponse({
          success: resp.ok,
          error: resp.ok ? null : ((data && (data.error || data.message)) || `HTTP ${resp.status}`),
        });
      })
      .catch((err) => sendResponse({ success: false, error: String(err) }));
    return true; // Keep channel open for async response
  }
});
