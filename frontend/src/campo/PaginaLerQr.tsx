import { useQuery } from '@tanstack/react-query';
import { chamar, type Eu } from '../api';
import { CascaCampo } from './CascaCampo';
import { LerQr } from './LerQr';
import type { LinksDoCampo } from './turno/tipos';

export function PaginaLerQr({ eu }: { eu: Eu }) {
  // O leitor não tem dado de ninguém: só os endereços da moldura.
  const links = useQuery({ queryKey: ['campo', 'links'], queryFn: () => chamar<LinksDoCampo>('/campo/links') });
  return (
    <CascaCampo eu={eu} links={links.data ?? null}>
      <LerQr />
    </CascaCampo>
  );
}
