// Tokenade Browser Extension — Page-facing API (MAIN world)
// Registered via chrome.scripting.registerContentScripts with world: "MAIN"
// so it is file-based rather than inline and immune to page CSP blocks.
// Communicates with content.js (isolated world) via window.postMessage.

(function() {
  'use strict';

  if (window.Tokenade) return; // never double-define

  window.Tokenade = {
    getCookies: function() {
      return new Promise((resolve) => {
        window.addEventListener('message', function handler(event) {
          if (event.data.type === 'TOKENADE_COOKIES_RESULT') {
            window.removeEventListener('message', handler);
            resolve(event.data.cookies);
          }
        });
        window.postMessage({ type: 'TOKENADE_GET_COOKIES' }, '*');
      });
    },

    getLocalStorage: function() {
      return new Promise((resolve) => {
        window.addEventListener('message', function handler(event) {
          if (event.data.type === 'TOKENADE_LOCALSTORAGE_RESULT') {
            window.removeEventListener('message', handler);
            resolve(event.data.localStorage);
          }
        });
        window.postMessage({ type: 'TOKENADE_GET_LOCALSTORAGE' }, '*');
      });
    },

    getSessionStorage: function() {
      return new Promise((resolve) => {
        window.addEventListener('message', function handler(event) {
          if (event.data.type === 'TOKENADE_SESSIONSTORAGE_RESULT') {
            window.removeEventListener('message', handler);
            resolve(event.data.sessionStorage);
          }
        });
        window.postMessage({ type: 'TOKENADE_GET_SESSIONSTORAGE' }, '*');
      });
    },

    sendSession: function(session, proxyUrl) {
      return new Promise((resolve) => {
        window.addEventListener('message', function handler(event) {
          if (event.data.type === 'TOKENADE_SEND_RESULT') {
            window.removeEventListener('message', handler);
            resolve({ success: event.data.success, error: event.data.error });
          }
        });
        window.postMessage({
          type: 'TOKENADE_SEND_SESSION',
          session: session,
          proxyUrl: proxyUrl,
        }, '*');
      });
    }
  };

  window.dispatchEvent(new CustomEvent('tokenade-ready'));
})();