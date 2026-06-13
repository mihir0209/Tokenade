// Tokenade Browser Extension - Content Script
// This script runs in the context of web pages

(function() {
  'use strict';
  
  // Listen for messages from the extension
  window.addEventListener('message', (event) => {
    if (event.source !== window) return;
    
    if (event.data.type === 'TOKENADE_GET_COOKIES') {
      // Request cookies from background script
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
    
    if (event.data.type === 'TOKENADE_GETLocalStorage') {
      // Request localStorage from background script
      browser.runtime.sendMessage({
        type: 'GETLocalStorage',
      }).then(response => {
        window.postMessage({
          type: 'TOKENADE_LocalStorage_RESULT',
          localStorage: response.localStorage,
        }, '*');
      });
    }
    
    if (event.data.type === 'TOKENADE_SEND_SESSION') {
      // Send session to proxy
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
  
  // Inject a helper script that pages can use
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
            if (event.data.type === 'TOKENADE_LocalStorage_RESULT') {
              window.removeEventListener('message', handler);
              resolve(event.data.localStorage);
            }
          });
          window.postMessage({ type: 'TOKENADE_GETLocalStorage' }, '*');
        });
      },
      
      sendSession: function(session, proxyUrl) {
        return new Promise((resolve) => {
          window.addEventListener('message', function handler(event) {
            if (event.data.type === 'TOKENADE_SEND_RESULT') {
              window.removeEventListener('message', handler);
              if (event.data.success) {
                resolve({ success: true });
              } else {
                resolve({ success: false, error: event.data.error });
              }
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
