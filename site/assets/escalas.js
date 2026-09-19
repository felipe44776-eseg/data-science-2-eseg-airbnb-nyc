/* Escalas de cor e formatação — sem DOM, sem mapa.
 *
 * Cada medida do mapa declara em resumo.json o seu "tipo" e a escala segue dele:
 *   sequencial  magnitude -> um só matiz, claro -> escuro (no escuro, inverte);
 *               classes por quantis (preço é assimétrico: quantil distribui melhor)
 *   divergente  variação -> dois matizes + neutro no zero; classes simétricas
 *   categorica  identidade -> cores fixas; LISA usa a convenção vermelho/azul
 * Paletas: rampa azul e divergente azul<->vermelho da skill de dataviz (braço
 * vermelho gerado com o mesmo L em OKLCH); cores de tipo de anúncio = as dos
 * distritos da v0, validadas para daltonismo em mapa (todas as combinações).
 */

export const PALETAS = {
  claro: {
    sequencial: ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
    divergente: ["#184f95", "#3987e5", "#9ec5f4", "#e8e4dc", "#fba9a1", "#df4e4b", "#912022"],
    lisa: { aa: "#df4e4b", bb: "#256abf", ab: "#fba9a1", ba: "#9ec5f4", ns: "#dcd6ca" },
    tipos: ["#E14F3D", "#128F7C", "#5468D9"],
    extras: ["#A24C97", "#C98A1B", "#6E6656"],
    contorno: "rgba(34, 30, 24, 0.55)",
    tinta: "#221E18",
    superficie: "#FFFFFF",
    fundo: "#F4EEE1",
  },
  escuro: {
    sequencial: ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
    divergente: ["#9ec5f4", "#3987e5", "#184f95", "#3a3630", "#912022", "#df4e4b", "#fba9a1"],
    lisa: { aa: "#ee7e77", bb: "#6da7ec", ab: "#912022", ba: "#184f95", ns: "#4a453d" },
    tipos: ["#E8604F", "#1C9C87", "#7485EC"],
    extras: ["#B866AC", "#D39B35", "#B9AF9B"],
    contorno: "rgba(243, 237, 225, 0.55)",
    tinta: "#F3EDE1",
    superficie: "#221E17",
    fundo: "#1E1A14",
  },
};

const TRANSPARENTE = "rgba(0, 0, 0, 0)";

/* ------------------------------------------------------------ formatação */

const NUM = new Map();
function nf(casas) {
  if (!NUM.has(casas)) {
    NUM.set(casas, new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: casas }));
  }
  return NUM.get(casas);
}
/** Sinal de menos tipográfico (U+2212) em vez do hífen. */
const menos = (s) => s.replace(/^-/, "\u2212");

function casasPara(v) {
  const a = Math.abs(v);
  if (a >= 100) return 0;
  if (a >= 10) return 1;
  return a >= 1 ? 1 : 2;
}

export function numero(v, casas = casasPara(v)) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return menos(nf(casas).format(v));
}

export function dolares(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (v < 0 ? "\u2212" : "") + "US$ " + nf(Math.abs(v) >= 10 ? 0 : 2).format(Math.abs(v));
}

/** Percentual já em pontos (12,5 -> "12,5%"). `sinal` força "+" nos positivos. */
export function pct(v, { sinal = false, casas } = {}) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const c = casas ?? (Math.abs(v) >= 10 ? 0 : 1);
  return (sinal && v > 0 ? "+" : "") + menos(nf(c).format(v)) + "%";
}

export function metros(m) {
  if (m >= 1000) return `${nf(1).format(m / 1000)} km`;
  return `${nf(0).format(Math.round(m / 10) * 10)} m`;
}

/** Valor de uma medida na unidade declarada em resumo.json. */
export function formatar(v, unidade, { sinal = false } = {}) {
  if (v === null || v === undefined || (typeof v === "number" && Number.isNaN(v))) return "—";
  if (typeof v !== "number") return String(v);
  switch (unidade) {
    case "US$": return (sinal && v > 0 ? "+" : "") + dolares(v);
    case "%": return pct(v, { sinal });
    case "":
    case undefined:
    case null: return (sinal && v > 0 ? "+" : "") + numero(v);
    default: return `${(sinal && v > 0 ? "+" : "") + numero(v)} ${unidade}`;
  }
}

/**
 * Multiplicador de exibição de uma medida. "%" é ambíguo na prática (o mesmo
 * resumo traz variações em pontos, -100 a +393, e fatias em fração, 0 a 1):
 * unidade "fração" -> ×100; "%" com todos os |v| <= 1 -> fração -> ×100; senão 1.
 */
export function fatorExibicao(metrica, valores) {
  if (metrica.unidade === "fração") return 100;
  if (metrica.unidade !== "%") return 1;
  const nums = valores.filter((v) => typeof v === "number" && Number.isFinite(v));
  return nums.length && nums.every((v) => Math.abs(v) <= 1) ? 100 : 1;
}

/** Formata um valor de medida com o fator de exibição anotado em `metrica.fator`. */
export function formatarMetrica(metrica, v, { sinal = metrica.tipo === "divergente", semUnidade = false } = {}) {
  if (typeof v !== "number") return formatar(v, metrica.unidade);
  const unidade = metrica.unidade === "fração" ? "%" : metrica.unidade;
  // na legenda, unidade por extenso ("anúncios", "m") fica só no título
  const u = semUnidade && unidade !== "US$" && unidade !== "%" ? "" : unidade;
  return formatar(v * (metrica.fator ?? 1), u, { sinal });
}

/* ------------------------------------------------------------ classes */

function quantil(ordenados, q) {
  if (ordenados.length === 0) return NaN;
  const pos = (ordenados.length - 1) * q;
  const i = Math.floor(pos);
  const f = pos - i;
  return i + 1 < ordenados.length ? ordenados[i] + f * (ordenados[i + 1] - ordenados[i]) : ordenados[i];
}

/** Arredonda para 2 algarismos significativos (legenda legível). */
function bonito(x) {
  if (x === 0 || !Number.isFinite(x)) return x;
  const e = Math.floor(Math.log10(Math.abs(x))) - 1;
  const p = 10 ** e;
  return Number((Math.round(x / p) * p).toPrecision(12)); // sem 4,6000000000000005
}

function estritamenteCrescente(cortes) {
  const saida = [];
  for (const c of cortes) if (Number.isFinite(c) && (saida.length === 0 || c > saida[saida.length - 1])) saida.push(c);
  return saida;
}

/** Escolhe n cores espalhadas numa paleta ordenada. */
function espalhar(paleta, n) {
  if (n <= 1) return [paleta[Math.floor(paleta.length / 2)]];
  return Array.from({ length: n }, (_, i) => paleta[Math.round((i * (paleta.length - 1)) / (n - 1))]);
}

function normalizar(s) {
  return String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");
}

const LISA = {
  altoalto: "aa", highhigh: "aa", hh: "aa",
  baixobaixo: "bb", lowlow: "bb", ll: "bb",
  altobaixo: "ab", highlow: "ab", hl: "ab",
  baixoalto: "ba", lowhigh: "ba", lh: "ba",
};

/**
 * Escala de uma medida (entrada de resumo.metricas_celula) sobre os valores das
 * células. Devolve {tipo, expressao, classes, cor(v)}: `expressao` vai para
 * fill-color da MapLibre; `classes` alimenta a legenda.
 */
export function escalaDaMetrica(metrica, valores, tema) {
  const pal = PALETAS[tema] ?? PALETAS.claro;
  const chave = metrica.chave;
  const get = ["get", chave];

  if (metrica.tipo === "categorica") {
    const cats = (metrica.categorias ?? [...new Set(valores.filter((v) => v !== null && v !== undefined))])
      .map((c) => (typeof c === "object" && c !== null ? c : { valor: c, rotulo: String(c) }));
    let extra = 0;
    const itens = cats.map((c) => {
      const lisa = LISA[normalizar(c.valor)];
      const naoSig = /^(nao|not|ns$|naosignificativo)/.test(normalizar(c.valor));
      const cor = c.cor ?? (lisa ? pal.lisa[lisa] : naoSig ? pal.lisa.ns
        : [...pal.tipos, ...pal.extras][extra++ % (pal.tipos.length + pal.extras.length)]);
      return { valor: c.valor, rotulo: c.rotulo ?? String(c.valor), cor };
    });
    const expressao = ["match", ["to-string", get]];
    for (const it of itens) expressao.push(String(it.valor), it.cor);
    expressao.push(TRANSPARENTE);
    const mapa = new Map(itens.map((it) => [String(it.valor), it.cor]));
    return {
      tipo: "categorica",
      expressao,
      classes: itens.map((it) => ({ cor: it.cor, rotulo: it.rotulo })),
      cor: (v) => mapa.get(String(v)) ?? null,
    };
  }

  const nums = valores.filter((v) => typeof v === "number" && Number.isFinite(v)).sort((a, b) => a - b);
  let cortes;
  let cores;
  if (metrica.tipo === "divergente") {
    // neutro no centro, sempre; cada braço com os próprios quantis. Escala simétrica
    // quebrava em variação percentual: o lado negativo não passa de -100% e o
    // positivo pode ir a +300%, e o simétrico desenhava faixas impossíveis.
    const absolutos = nums.map(Math.abs).sort((a, b) => a - b);
    // meia-largura da classe neutra ("praticamente sem variação"): a declarada na
    // métrica (resumo.json -> "neutro") ou 5% do p95 de |v| — nunca um quantil dos
    // próprios dados, que num mercado quase todo em alta viraria ±56%
    const neutro = metrica.neutro ?? (bonito(0.05 * quantil(absolutos, 0.95)) || 1e-9);
    const neg = nums.filter((v) => v < -neutro).map((v) => -v).sort((a, b) => a - b);
    const pos = nums.filter((v) => v > neutro);
    // classes por braço conforme o tamanho do braço: tercis (3 classes), mediana
    // (2) ou uma classe só — 2 células não sustentam uma faixa "−18% a −16%"
    const braco = (arr) => {
      if (arr.length >= 30) return [bonito(quantil(arr, 1 / 3)), bonito(quantil(arr, 2 / 3))];
      if (arr.length >= 10) return [bonito(quantil(arr, 0.5))];
      return [];
    };
    const cortesNeg = estritamenteCrescente(braco(neg).map((c) => -c).sort((a, b) => a - b)).filter((c) => c < -neutro);
    const cortesPos = estritamenteCrescente(braco(pos)).filter((c) => c > neutro);
    // k classes num braço de 3 cores: 3 -> todas; 2 -> forte e fraca; 1 -> a do meio
    const escolher = (tres, k) => (k >= 3 ? tres : k === 2 ? [tres[0], tres[2]] : [tres[1]]);
    const coresNeg = escolher(pal.divergente.slice(0, 3), cortesNeg.length + 1);
    const coresPos = escolher(pal.divergente.slice(4, 7).reverse(), cortesPos.length + 1).reverse();
    cortes = [...cortesNeg, -neutro, neutro, ...cortesPos];
    cores = [...coresNeg, pal.divergente[3], ...coresPos];
  } else {
    const brutos = [1, 2, 3, 4, 5, 6].map((k) => quantil(nums, k / 7));
    // corte igual ao mínimo criaria a classe vazia "abaixo de 0%" (muitas células em 0)
    cortes = estritamenteCrescente(brutos.map(bonito)).filter((c) => c > nums[0]);
    cores = espalhar(pal.sequencial, cortes.length + 1);
  }

  const passo = ["step", get, cores[0]];
  cortes.forEach((c, i) => passo.push(c, cores[i + 1]));
  const expressao = cortes.length
    ? ["case", ["==", ["typeof", get], "number"], passo, TRANSPARENTE]
    : ["case", ["==", ["typeof", get], "number"], cores[0], TRANSPARENTE];

  const f = (v) => formatarMetrica(metrica, v, { semUnidade: true });
  const classes = cores.map((cor, i) => {
    let rotulo;
    if (cortes.length === 0) rotulo = "todas as áreas";
    else if (i === 0) rotulo = `abaixo de ${f(cortes[0])}`;
    else if (i === cortes.length) rotulo = `${f(cortes[i - 1])} ou mais`;
    else rotulo = `${f(cortes[i - 1])} a ${f(cortes[i])}`;
    return { cor, rotulo };
  });

  const cor = (v) => {
    if (typeof v !== "number" || !Number.isFinite(v)) return null;
    let i = 0;
    while (i < cortes.length && v >= cortes[i]) i++;
    return cores[i];
  };
  return { tipo: metrica.tipo === "divergente" ? "divergente" : "sequencial", expressao, classes, cor };
}

/** Cores dos anúncios por grupo: 0 inteiro, 1 quarto privativo, 2 outros. */
export function coresTipos(tema) {
  return (PALETAS[tema] ?? PALETAS.claro).tipos;
}
