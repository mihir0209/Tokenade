// Tokenade Browser Extension - Content Script
// Runs in the context of web pages

(function() {
  'use strict';

  // Listen for messages from the extension
  window.addEventListener('message', (event) => {
    if (event.source !== window) return;

    if (event.data.type === 'TOKENADE_GET_COOKIES') {
      browser.runtime.sendMessage({
        type: 'GET_COOKIES',
        url: window.location.href,
      }).then(response => {
        window.postMessage({
          type: 'TOKENADE_COOKIES_RESULT',
          cookies: response.cookies,
        }, '*');
      });
    }

    if (event.data.type === 'TOKENADE_GET_LOCALSTORAGE') {
      browser.runtime.sendMessage({
        type: 'GETLocalStorage',
      }).then(response => {
        window.postMessage({
          type: 'TOKENADE_LOCALSTORAGE_RESULT',
          localStorage: response.localStorage,
        }, '*');
      });
    }

    if (event.data.type === 'TOKENADE_SEND_SESSION') {
      browser.runtime.sendMessage({
        type: 'SEND_TO_PROXY',
        session: event.data.session,
        proxyUrl: event.data.proxyUrl,
      }).then(response => {
        window.postMessage({
          type: 'TOKENADE_SEND_RESULT',
          success: response.success,
          error: response.error,
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
  document.head.appendChild(script);
})();
