// O pedaço "campo" do build: as telas do aplicativo de campo, carregadas só
// quando uma delas abre (App.tsx). Sem sinal, o service worker entrega o
// pedaço da cópia do aparelho (/static/), como o resto da tela.
export { PaginaInicioCampo } from './PaginaInicioCampo';
export { PaginaLerQr } from './PaginaLerQr';
export { PaginaTurno } from './turno/PaginaTurno';
// Fase 1d: a equipe do dia, o material e as visitas de supervisão.
export { PaginaEquipeDoCampo, PaginaMateriaisDoCampo, PaginaVisitaDoCampo, PaginaVisitasDoCampo } from './app/paginas';
