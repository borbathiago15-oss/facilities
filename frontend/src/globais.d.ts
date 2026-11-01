// Os scripts de sempre que as telas novas reaproveitam (carregados pela
// casca, templates/telas/casca.html): a fila do aparelho sem internet
// (static/js/fila-offline.js), a redução das fotos (static/js/foto-leve.js)
// o leitor de QR de qualquer navegador (static/vendor/jsqr/jsQR.js) e os
// gráficos do painel da passagem (static/vendor/chart/chart.umd.min.js).

type ItemDaFila = {
  id?: string;
  tipo: string;
  rotulo: string;
  corpo: unknown;
  tarefa_id?: number | null;
  fotos?: { campo: string; arquivo: File }[];
  // A passagem de turno: o turno já gravado (só faltam as fotos) e os grupos.
  turno_id?: number | null;
  anexos?: { envio: string; atividade: string; arquivos: File[]; feito: boolean }[];
};

type DetectorDeQr = { detect(fonte: CanvasImageSource): Promise<{ rawValue: string }[]> };

interface Window {
  TrinoFila?: {
    novoId(): string;
    guardar(item: ItemDaFila): Promise<unknown>;
    enviarAgora(): void;
    ehFalhaDeConexao(r: Response | null): boolean;
  };
  TrinoFoto?: {
    reduzirTodos(arquivos: File[]): Promise<(File | Blob)[]>;
    /** Reduz as fotos do campo no próprio campo; devolve o resumo ("1 foto · 2 MB → 300 KB"). */
    prepararEntrada(entrada: HTMLInputElement): Promise<string>;
  };
  jsQR?: (dados: Uint8ClampedArray, largura: number, altura: number,
          opcoes?: { inversionAttempts?: string }) => { data: string } | null;
  BarcodeDetector?: new (opcoes: { formats: string[] }) => DetectorDeQr;
  Chart?: {
    new (alvo: HTMLCanvasElement, config: unknown): { destroy(): void };
    defaults: { font: { family: string }; color: string };
  };
}
