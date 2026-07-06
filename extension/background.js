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
});
