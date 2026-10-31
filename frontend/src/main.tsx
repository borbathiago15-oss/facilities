import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { App } from './App';

// O mesmo service worker do site (static/pwa/sw.js): página "Sem conexão"
// e os avisos no celular. Sem ele o sistema funciona igual.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  });
}

const cliente = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById('raiz')!).render(
  <StrictMode>
    <QueryClientProvider client={cliente}>
      <BrowserRouter basename="/novo">
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
