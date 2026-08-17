// Tokenade Browser Extension - Content Script
// Runs in the context of web pages

(function() {
  'use strict';

  // Chrome exposes the API on `chrome`, Firefox on `browser`.
  const runtime = (typeof browser !== 'undefined' && browser.runtime)
    ? browser.runtime
    : chrome.runtime;

  // Listen for messages from the extension
  window.addEventListener('message', (event) => {
    if (event.source !== window) return;

    if (event.data.type === 'TOKENADE_GET_COOKIES') {
      runtime.sendMessage({
        type: 'getCookies',
        options: {},
      }).then(response => {
        window.postMessage({
          type: 'TOKENADE_COOKIES_RESULT',
          cookies: response ? response.cookies : [],
        }, '*');
      }).catch(() => {
        window.postMessage({
          type: 'TOKENADE_COOKIES_RESULT',
          cookies: [],
        }, '*');
      });
    }

    if (event.data.type === 'TOKENADE_GET_LOCALSTORAGE') {
      const out = {};
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k != null) out[k] = localStorage.getItem(k);
        }
      } catch (_) { /* opaque origin */ }
      window.postMessage({
        type: 'TOKENADE_LOCALSTORAGE_RESULT',
        localStorage: out,
      }, '*');
    }

    if (event.data.type === 'TOKENADE_GET_SESSIONSTORAGE') {
      const out = {};
      try {
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          if (k != null) out[k] = sessionStorage.getItem(k);
        }
      } catch (_) { /* opaque origin */ }
      window.postMessage({
        type: 'TOKENADE_SESSIONSTORAGE_RESULT',
        sessionStorage: out,
      }, '*');
    }

    if (event.data.type === 'TOKENADE_SEND_SESSION') {
      runtime.sendMessage({
        type: 'SEND_TO_PROXY',
        session: event.data.session,
        proxyUrl: event.data.proxyUrl,
      }).then(response => {
        window.postMessage({
          type: 'TOKENADE_SEND_RESULT',
          success: !!(response && response.success),
          error: response ? response.error : 'no response from extension',
        }, '*');
      }).catch(err => {
        window.postMessage({
          type: 'TOKENADE_SEND_RESULT',
          success: false,
          error: String(err),
        }, '*');
      });
    }
  });

  // Inject helper script that pages can use
  const script = document.createElement('script');
  script.textContent = `
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
  `;
  if (document.head) {
    document.head.appendChild(script);
  } else {
    document.addEventListener('DOMContentLoaded', () => document.head.appendChild(script), { once: true });
  }
})();
