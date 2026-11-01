import { useEffect, useState } from 'react';

/** O aparelho está com sinal? (O selo "Sem sinal" do aplicativo.) */
export function useComSinal() {
  const [online, setOnline] = useState(() => navigator.onLine !== false);
  useEffect(() => {
    const atualizar = () => setOnline(navigator.onLine !== false);
    window.addEventListener('online', atualizar);
    window.addEventListener('offline', atualizar);
    return () => {
      window.removeEventListener('online', atualizar);
      window.removeEventListener('offline', atualizar);
    };
  }, []);
  return online;
}
