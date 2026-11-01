import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { App } from './App';

// O mesmo service worker do site (static/pwa/sw.js): página "Sem conexão",
// a cópia das telas do campo para abrir sem sinal e os avisos no celular.
// Sem ele o sistema funciona igual.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  });
}

const cliente = new QueryClient({
  // ``networkMode: 'always'``: sem sinal a busca acontece mesmo assim — o
  // service worker responde com a cópia do aparelho (telas do campo) ou a
  // tela diz "Sem conexão"; no padrão, ficaria "Carregando…" para sempre.
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, networkMode: 'always' } },
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
