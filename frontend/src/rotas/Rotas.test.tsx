import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Dia } from './Acompanhamento';
import { nomesDosDias } from './comum';
import { Modelo } from './Modelo';
import { ImportarPlano } from './Plano';
import { Aplicar } from './Prontas';
import { Rota } from './Rota';
import type { DadosDaRota, DadosDoDia, DadosDoModelo } from './tipos';

const DIAS: [string, string][] = [['1', 'seg'], ['2', 'ter'], ['3', 'qua'], ['4', 'qui'], ['5', 'sex'], ['6', 'sáb'], ['7', 'dom']];

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Feito.' }], destino: '/novo/rotas/7' } };
beforeEach(() => {
  chamadas = [];
  respostas = {};
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    const r = respostas[String(url)] || PADRAO;
    return new Response(JSON.stringify(r.corpo), { status: r.status });
  });
});
afterEach(() => vi.restoreAllMocks());

function Onde() {
  const l = useLocation();
  return <span data-testid="onde">{l.pathname + l.search}</span>;
}

function abrir(no: React.ReactNode, url = '/') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="*" element={<>{no}<Onde /></>} /></Routes>
    </MemoryRouter>);
}

function rota(extra: Partial<DadosDaRota> = {}): DadosDaRota {
  return {
    rota: { id: 7, nome: 'Limpeza T1', turno: '1º Turno', inicio: '06:00', fim: '14:00', intervalo_inicio: '10:00',
      intervalo_fim: '10:30', tolerancia_min: 15, dias_semana: '135', ativa: true, observacoes: '',
      presencas_por_turno: 0, presenca_prazo_min: 10, funciona_em_feriado: true, local: { id: 3, nome: 'CD 1' } },
    itens: [{ id: 9, ativo: true, ponto_id: 4, ponto: 'Copa · Pia', modelo_id: 5, modelo: 'Copa', ordem: 0,
      horarios: '07:00, 09:00', frequencia_min: null, tempo_previsto_min: 20, dias_semana: '1',
      horarios_por_dia: [['sex', '08:00']], hoje: ['07:00', '09:00'] }],
    pontos: [{ id: 4, setor: 'Geral', ambiente: 'Copa', nome: 'Pia' }, { id: 6, setor: 'Geral', ambiente: 'Hall', nome: 'Porta' }],
    modelos: [{ id: 5, nome: 'Copa' }],
    pessoas: [{ id: 11, nome: 'Ana', perfil: 'Encarregado / ASG' }],
    escalas: [{ id: 12, nome: 'Ana', dias_semana: '13', desde: '01/11/2026', ate: null }],
    pode_montar: true, dias: DIAS, hoje: '2026-11-01', links: { estrutura: '/novo/cadastros/locais/3' },
    ...extra,
  };
}

describe('a rota', () => {
  it('mostra o turno e as atividades como a tela antiga escreve', () => {
    abrir(<Rota dados={rota()} />);
    expect(screen.getByText(/1º Turno · 06:00 às 14:00 · intervalo 10:00 às 10:30 · tolerância de 15 min · seg, qua, sex/)).toBeInTheDocument();
    expect(screen.getByText('Horários: 07:00, 09:00 · 20 min previstos · só seg · sex: 08:00 · hoje: 07:00, 09:00')).toBeInTheDocument();
    expect(screen.getByText('seg, qua · desde 01/11/2026')).toBeInTheDocument();
  });

  it('inclui vários pontos com o mesmo formulário da tela antiga', async () => {
    abrir(<Rota dados={rota()} />, '/rotas/7');
    await userEvent.click(screen.getByText('+ Incluir pontos na rota'));
    await userEvent.click(screen.getByRole('checkbox', { name: /Copa · Pia/ }));
    await userEvent.click(screen.getByRole('checkbox', { name: /Hall · Porta/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Incluir' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/rotas/7/itens');
    const corpo = chamadas[0].init!.body as FormData;
    expect(corpo.getAll('ponto_id')).toEqual(['4', '6']);
    expect(corpo.get('modelo_id')).toBe('5');
    expect(screen.getByTestId('onde')).toHaveTextContent('/rotas/7');
  });

  it('sem ponto com QR, leva à estrutura do local (já na tela nova)', () => {
    abrir(<Rota dados={rota({ pontos: [] })} />);
    expect(screen.getByRole('link', { name: 'pontos com QR' })).toHaveAttribute('href', '/cadastros/locais/3');
  });

  it('quem só lê não recebe os formulários', () => {
    abrir(<Rota dados={rota({ pode_montar: false })} />);
    expect(screen.queryByText('+ Escalar pessoa')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Encerrar escala' })).toBeNull();
  });
});

function modelo(extra: Partial<DadosDoModelo> = {}): DadosDoModelo {
  return {
    modelo: { id: 5, nome: 'Copa', descricao: 'Limpe a pia', local: { id: 3, nome: 'CD 1' }, exige_foto_antes: false, exige_foto_depois: true },
    versao: { numero: 2, publicada_em: '01/11/2026 08:00', materiais: 'Pano', epi: 'Luva' },
    itens: [{ codigo: 'pia', texto: 'Pia limpa?', tipo: 'sim_nao', obrigatorio: true, exige_foto: false, opcoes: '',
      minimo: '', maximo: '', problema_se: 'nao', mostrar_se: '', como_fazer: 'Esfregue', referencia: '/rotas/referencias/1/pia', foto_ref: 'refs/1.jpg' }],
    linhas_em_branco: 4, tipos: [['sim_nao', 'Sim / não'], ['texto', 'Texto']], pode_montar: true,
    documentos: [], limite_docs: 10, ...extra,
  };
}

describe('o checklist', () => {
  it('publica o formulário de sempre, com a chave da foto guardada', async () => {
    const { container } = abrir(<Modelo dados={modelo()} />);
    expect(container.querySelectorAll('input[name=texto]')).toHaveLength(5);
    await userEvent.click(screen.getByRole('button', { name: 'Publicar nova versão' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/rotas/modelos/5');
    const corpo = chamadas[0].init!.body as FormData;
    expect(corpo.getAll('foto_ref')[0]).toBe('refs/1.jpg');
    expect(corpo.getAll('codigo')).toEqual(['pia', '', '', '', '']);
    expect(corpo.getAll('ordem')).toEqual(['1', '', '', '', '']);
    expect(corpo.getAll('obrigatorio')).toEqual(['0']);
    expect(corpo.get('exige_foto_depois')).toBe('1');
  });

  it('quem só lê vê as perguntas, sem formulário', () => {
    const { container } = abrir(<Modelo dados={modelo({ pode_montar: false })} />);
    expect(container.querySelector('form')).toBeNull();
    expect(screen.getByText('(Sim / não, obrigatória)')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Como deve ficar: Pia limpa?' })).toHaveAttribute('src', '/rotas/referencias/1/pia');
  });
});

describe('o dia', () => {
  const dia: DadosDoDia = {
    local: { id: 3, nome: 'CD 1' }, data: '2026-11-01', data_br: '01/11/2026', data_curta: '01/11',
    aderencia: { no_prazo: 1, base: 2, pct: 50 },
    tarefas: [{ id: 1, hora: '07:00', ambiente: 'Copa', ponto: 'Pia', modelo: 'Copa', rota: 'T1', situacao: 'feita',
      situacao_rotulo: 'Feita', pessoa: 'Ana', nao_realizada: null,
      execucao: { id: 8, pessoa: 'Ana', inicio: '07:02', fim: '07:10', sem_sinal: true, nao_conformes: 1,
        gps: { situacao: 'fora', texto: 'Fora do local (1,1 km)', precisao: 25 }, adiantada: false, motivo_troca: '', motivo_troca_texto: '' } }],
    ocorrencias: [{ id: 4, hora: '08:00', ambiente: 'Copa', ponto: 'Pia', titulo: 'Sujo', responsavel: null, texto: '',
      foto: null, status: 'aberta', situacao: 'Aberta', atrasada: false, prazo: null, resolvida: null }],
    elogios: [], chegadas: [], extras: [],
    presencas: [{ id: 2, hora: '09:00', pessoa: 'Ana', rota: 'T1', status: 'sem_resposta', respondida: '09:20' }],
    pode_atender: true,
  };

  it('mostra a tarefa feita, o GPS e a presença como a tela antiga', () => {
    abrir(<Dia dados={dia} />);
    expect(screen.getByRole('link', { name: 'Ana · 07:02–07:10 · hora do celular · 1 não conforme(s)' })).toHaveAttribute('href', '/rotas/execucoes/8');
    expect(screen.getByText('Fora do local (1,1 km)')).toHaveAttribute('title', 'Precisão do celular: 25 m');
    expect(screen.getByText('Sem resposta (respondeu às 09:20)')).toHaveClass('text-bg-danger');
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('resolve a ocorrência do público pelo mesmo caminho', async () => {
    respostas['/api/v1/rotas/ocorrencias/4/resolver'] = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Ocorrência resolvida.' }], destino: '/novo/rotas/locais/3/dia' } };
    abrir(<Dia dados={dia} />, '/rotas/locais/3/dia?data=2026-10-30');
    await userEvent.type(screen.getByLabelText('O que foi feito'), 'Limpei');
    await userEvent.click(screen.getByRole('button', { name: 'Resolvida' }));
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/rotas/locais/3/dia'));
    expect((chamadas[0].init!.body as FormData).get('resolucao')).toBe('Limpei');
  });

  it('"Ver o dia" muda o endereço, como o formulário GET da antiga', async () => {
    abrir(<Dia dados={dia} />, '/rotas/locais/3/dia');
    await userEvent.click(screen.getByRole('button', { name: 'Ver o dia' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/rotas/locais/3/dia?data=2026-11-01');
  });
});

describe('aplicar rota pronta e a planilha', () => {
  it('"Ver a prévia" leva ao endereço com o modelo escolhido', async () => {
    abrir(<Aplicar dados={{ local: { id: 3, nome: 'CD 1' }, opcoes: [{ id: 2, segmento: 'Loja', nome: 'Padrão' }], modelo: null, linhas: [], dias: DIAS }} />);
    await userEvent.selectOptions(screen.getByLabelText('Rota pronta'), '2');
    await userEvent.click(screen.getByRole('button', { name: 'Ver a prévia' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/rotas/locais/3/rota-pronta?modelo=2');
  });

  it('a planilha volta como prévia e o "Criar" leva a chave', async () => {
    respostas['/api/v1/rotas/locais/3/importar-plano'] = { status: 200, corpo: {
      chave: 'planos/3/abc.xlsx', ja_existem: ['Rota 1'], recados: [],
      previa: { avisos: ['Linha 3 ignorada'], blocos: [{ setor: 'Galpão', nome: 'Doca', atividades: 2, existe: false }],
        checklists: [{ nome: 'Varrer', itens: ['Varrido'], materiais: '', epi: '', existe: false }],
        rotas: [{ nome: 'Rota 1', existe: true, turno: 'Diurno', hora_inicio: '06:00', hora_fim: '14:00', intervalo_inicio: '',
          intervalo_fim: '', dias_semana: '12345', tolerancia_min: 30, responsavel: 'ROSA', observacoes: '',
          itens: [{ ordem: 1, horario: '06:00', tempo_previsto_min: 30, bloco: 'Galpão — Doca', checklist: 'Varrer', dias_semana: '', horarios_por_dia: [['6', '07:00']] }] }] } } };
    respostas['/api/v1/rotas/locais/3/importar-plano/criar'] = { status: 200, corpo: { recados: [], destino: '/novo/rotas/locais/3' } };
    abrir(<ImportarPlano dados={{ local: { id: 3, nome: 'CD 1' }, dias: DIAS }} />, '/rotas/locais/3/importar-plano');
    await userEvent.upload(screen.getByLabelText('Planilha do plano (.xlsx, até 5 MB)'), new File(['x'], 'plano.xlsx'));
    // (o jsdom não conta o arquivo do ``upload`` no ``required``: envia direto)
    fireEvent.submit(screen.getByRole('button', { name: 'Ver a prévia' }).closest('form')!);
    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain('/api/v1/rotas/locais/3/importar-plano'));
    expect(await screen.findByText('Linha 3 ignorada')).toBeInTheDocument();
    expect(screen.getByText('todos · sáb às 07:00')).toBeInTheDocument();
    expect(screen.getByText('Responsável: ROSA')).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('Substituir as rotas que já existem'));
    await userEvent.click(screen.getByRole('button', { name: /Criar blocos, checklists e rotas/ }));
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/rotas/locais/3'));
    const corpo = chamadas[1].init!.body as FormData;
    expect(corpo.get('chave')).toBe('planos/3/abc.xlsx');
    expect(corpo.get('substituir')).toBe('1');
  });
});

describe('as regras pequenas', () => {
  it('os dias na ordem do código', () => {
    expect(nomesDosDias('7135', DIAS)).toBe('dom, seg, qua, sex');
    expect(nomesDosDias('', DIAS)).toBe('');
  });
});

describe('a tela abre pelo seu pedaço do build', () => {
  it('a rotina dos locais carrega sob demanda, dentro da casca', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    respostas['/api/v1/rotas/inicio'] = { status: 200, corpo: { pode_montar: true, locais: [
      { id: 3, nome: 'CD 1', cliente: 'Grupo GL', links: { preventiva: '/preventiva/locais/3', equipe: '/e', visitas: '/v', estrutura: '/novo/cadastros/locais/3' } }] } };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/rotas/']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Rotina dos locais' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Hoje' })).toHaveAttribute('href', '/rotas/locais/3/dia');
    expect(screen.getByRole('link', { name: 'Preventivas' })).toHaveAttribute('href', '/preventiva/locais/3');
  });
});
