// Os scripts de sempre que as telas novas reaproveitam (carregados pela
// casca, templates/telas/casca.html): a fila do aparelho sem internet
// (static/js/fila-offline.js), a redução das fotos (static/js/foto-leve.js)
// e o leitor de QR de qualquer navegador (static/vendor/jsqr/jsQR.js).

type ItemDaFila = {
  tipo: string;
  rotulo: string;
  corpo: unknown;
  tarefa_id?: number | null;
  fotos?: { campo: string; arquivo: File }[];
};

type DetectorDeQr = { detect(fonte: CanvasImageSource): Promise<{ rawValue: string }[]> };

interface Window {
  TrinoFila?: {
    novoId(): string;
    guardar(item: ItemDaFila): Promise<unknown>;
    enviarAgora(): void;
    ehFalhaDeConexao(r: Response | null): boolean;
  };
  TrinoFoto?: { reduzirTodos(arquivos: File[]): Promise<(File | Blob)[]> };
  jsQR?: (dados: Uint8ClampedArray, largura: number, altura: number,
          opcoes?: { inversionAttempts?: string }) => { data: string } | null;
  BarcodeDetector?: new (opcoes: { formats: string[] }) => DetectorDeQr;
}
