/**
 * Tokenade Session Exporter — Background Service Worker
 * 
 * Handles extension lifecycle and background tasks.
 */

// Register the MAIN-world page API. File-based scripts in the MAIN world are
// immune to page Content Security Policies that would block inline injection.
const MAIN_WORLD_SCRIPT_ID = 'tokenade-main-world';

async function registerMainWorldBridge() {
  try {
    await chrome.scripting.unregisterContentScripts({ ids: [MAIN_WORLD_SCRIPT_ID] });
  } catch (_) { /* not registered yet */ }
  try {
    await chrome.scripting.registerContentScripts([{
      id: MAIN_WORLD_SCRIPT_ID,
      matches: ['<all_urls>'],
      js: ['content-main.js'],
      runAt: 'document_start',
      world: 'MAIN',
    }]);
  } catch (err) {
    console.error('registerMainWorldBridge failed:', err);
  }
}

chrome.runtime.onInstalled.addListener(registerMainWorldBridge);
registerMainWorldBridge();

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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    fetch(message.proxyUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.session || {}),
      signal: controller.signal,
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
      .catch((err) => sendResponse({ success: false, error: String(err) }))
      .finally(() => clearTimeout(timeoutId));
    return true; // Keep channel open for async response
  }
});
