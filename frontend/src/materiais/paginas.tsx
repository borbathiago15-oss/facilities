// As páginas dos materiais na gestão (Fase 4b): cada uma busca os dados na
// API (o mesmo endereço da tela antiga abaixo de /api/v1, com a mesma query
// string) e desenha a tela. Este arquivo é o ponto de entrada do pedaço
// "materiais" do build (carregado só quando uma destas telas abre).
import { useLocation, useParams } from 'react-router';
import { Pagina } from '../cadastros/comum';
import { Catalogo, ConsumoDoMes, Custo, Estoque, Pedidos } from './Materiais';
import type { DadosDoCatalogo, DadosDoConsumoDoMes, DadosDoCusto, DadosDoEstoque, DadosDosPedidos } from './tipos';

export function PaginaCatalogo() {
  return <Pagina<DadosDoCatalogo> api="/materiais/">{(d) => <Catalogo dados={d} />}</Pagina>;
}

export function PaginaEstoque() {
  const { id } = useParams();
  return <Pagina<DadosDoEstoque> api={`/materiais/locais/${id}`}>{(d) => <Estoque dados={d} />}</Pagina>;
}

export function PaginaConsumoDoMes() {
  const { id } = useParams();
  const { search } = useLocation();
  return <Pagina<DadosDoConsumoDoMes> api={`/materiais/locais/${id}/mes${search}`}>{(d) => <ConsumoDoMes dados={d} />}</Pagina>;
}

export function PaginaCusto() {
  const { search } = useLocation();
  return <Pagina<DadosDoCusto> api={`/materiais/custo${search}`}>{(d) => <Custo dados={d} />}</Pagina>;
}

export function PaginaPedidos() {
  return <Pagina<DadosDosPedidos> api="/materiais/pedidos">{(d) => <Pedidos dados={d} />}</Pagina>;
}
