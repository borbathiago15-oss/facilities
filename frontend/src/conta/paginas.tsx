// As páginas da conta, dos avisos e do Início (Fase 6a): cada uma busca os
// dados na API (o mesmo endereço da tela antiga abaixo de /api/v1) e desenha
// a tela. Ponto de entrada do pedaço "conta" do build.
import { Pagina } from '../cadastros/comum';
import { Avisos, InicioDaGestao, Seguranca, TrocarSenha } from './Conta';
import type { DadosDaSeguranca, DadosDaTrocaDeSenha, DadosDoInicio, DadosDosAvisos } from './tipos';

export function PaginaInicio() {
  return <Pagina<DadosDoInicio> api="/inicio">{(d) => <InicioDaGestao dados={d} />}</Pagina>;
}

export function PaginaAvisos() {
  return <Pagina<DadosDosAvisos> api="/avisos">{(d) => <Avisos dados={d} />}</Pagina>;
}

export function PaginaSeguranca() {
  return <Pagina<DadosDaSeguranca> api="/conta/seguranca">{(d) => <Seguranca dados={d} />}</Pagina>;
}

export function PaginaTrocarSenha() {
  return <Pagina<DadosDaTrocaDeSenha> api="/trocar-senha">{(d) => <TrocarSenha dados={d} />}</Pagina>;
}
