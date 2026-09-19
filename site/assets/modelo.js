/* Avaliador de modelos LightGBM no navegador — semântica EXATA do LightGBM 4.x.
 *
 * Lê o JSON gerado por `airbnb.produto.modelo_js.exportar_modelo` (formato
 * "lightgbm-js/1") e devolve o mesmo número que `booster.predict` — não uma
 * aproximação. Quem prova é `tests/paridade_js.mjs`, que importa ESTE arquivo
 * (não uma cópia) e o confere contra centenas de previsões do próprio LightGBM.
 *
 * Semântica (LightGBM 4.x, include/LightGBM/tree.h):
 *   0. |x| <= 1e-35f (kZeroThreshold) vira 0.0 ao montar a linha.
 *   1. Split numérico ("<="), conforme o missing_type do nó:
 *        None — NaN vira 0.0 e compara normalmente;
 *        Zero — NaN vira 0.0; zero segue default_left; o resto compara;
 *        NaN  — NaN segue default_left; zero compara normalmente.
 *   2. Split categórico ("==", limiar "a||b||c"): NaN ou negativo vai para a
 *      direita; senão trunca para inteiro e vai para a esquerda se a categoria
 *      está no conjunto.
 *   3. Escore bruto = soma das folhas, árvore a árvore, na ordem, + init_score.
 *   4. Previsão = transformação(bruto): identidade | exp | expm1 | sigmoide.
 *
 * Sem dependência e sem DOM: roda igual no navegador e no Node.
 */

export const FORMATO = "lightgbm-js/1";

/** kZeroThreshold do LightGBM é um float32 (1e-35f) comparado em double. */
const LIMIAR_ZERO = Math.fround(1e-35);

const AUSENTE_ZERO = 1;
const AUSENTE_NAN = 2;
const DECISAO_CATEGORICA = 1;

/* modelo (objeto do JSON) -> forma preparada; parse do limiar categórico uma vez só */
const preparados = new WeakMap();

function preparar(modelo) {
  let p = preparados.get(modelo);
  if (p) return p;
  if (!modelo || modelo.formato !== FORMATO) {
    throw new Error(`modelo em formato desconhecido: ${modelo && modelo.formato}`);
  }
  const indice = new Map(modelo.features.map((nome, i) => [nome, i]));
  const arvores = modelo.arvores.map((a) => ({
    ...a,
    categorias: a.decisao.map((d, i) => (d === DECISAO_CATEGORICA
      ? new Set(String(a.limiar[i]).split("||").filter((c) => c !== "").map(Number))
      : null)),
  }));
  p = { indice, arvores, n: modelo.features.length };
  preparados.set(modelo, p);
  return p;
}

/** null/undefined/"" -> NaN (ausente); booleano -> 1/0; texto numérico -> número. */
function paraNumero(v) {
  if (v === null || v === undefined) return NaN;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (typeof v === "string") {
    const s = v.trim();
    return s === "" ? NaN : Number(s);
  }
  return Number(v);
}

/** x: array na ordem de `features` ou objeto {nome: valor}; chave ausente = NaN. */
function linha(p, x) {
  const v = new Float64Array(p.n).fill(NaN);
  if (Array.isArray(x) || ArrayBuffer.isView(x)) {
    if (x.length !== p.n) throw new Error(`esperava ${p.n} valores, recebeu ${x.length}`);
    for (let i = 0; i < p.n; i++) v[i] = paraNumero(x[i]);
  } else if (x !== null && typeof x === "object") {
    for (const chave of Object.keys(x)) {
      const i = p.indice.get(chave);
      if (i === undefined) throw new Error(`"${chave}" não é feature do modelo`);
      v[i] = paraNumero(x[chave]);
    }
  } else {
    throw new TypeError("x tem de ser array ou objeto");
  }
  // o LightGBM descarta |x| <= kZeroThreshold ao montar a linha densa: vira 0.0
  for (let i = 0; i < p.n; i++) if (Math.abs(v[i]) <= LIMIAR_ZERO) v[i] = 0;
  return v;
}

/** Índice da folha em que a linha cai (Tree::GetLeaf). */
function folha(a, x) {
  if (a.feature.length === 0) return 0; // árvore de uma folha só
  let no = 0;
  while (no >= 0) {
    let v = x[a.feature[no]];
    if (a.decisao[no] === DECISAO_CATEGORICA) {
      // CategoricalDecision: NaN ou negativo -> direita
      if (Number.isNaN(v)) { no = a.direita[no]; continue; }
      const c = Math.trunc(v);
      if (c < 0) { no = a.direita[no]; continue; }
      no = a.categorias[no].has(c) ? a.esquerda[no] : a.direita[no];
      continue;
    }
    // NumericalDecision
    const m = a.ausente[no];
    if (Number.isNaN(v) && m !== AUSENTE_NAN) v = 0;
    if ((m === AUSENTE_ZERO && v >= -LIMIAR_ZERO && v <= LIMIAR_ZERO)
        || (m === AUSENTE_NAN && Number.isNaN(v))) {
      no = a.padrao_esquerda[no] ? a.esquerda[no] : a.direita[no];
    } else {
      no = v <= a.limiar[no] ? a.esquerda[no] : a.direita[no];
    }
  }
  return ~no;
}

/** Escore bruto (o que `booster.predict(raw_score=True)` devolve, + init_score). */
export function preverBruto(modelo, x) {
  const p = preparar(modelo);
  const v = linha(p, x);
  let s = 0;
  for (const a of p.arvores) s += a.folhas[folha(a, v)];
  return s + (modelo.init_score ?? 0);
}

/** Leva o escore bruto à unidade publicada. */
export function transformar(modelo, bruto) {
  switch (modelo.transformacao) {
    case "identidade": return bruto;
    case "exp": return Math.exp(bruto);
    case "expm1": return Math.expm1(bruto);
    case "sigmoide": return 1 / (1 + Math.exp(-(modelo.sigmoide ?? 1) * bruto));
    default: throw new Error(`transformação desconhecida: ${modelo.transformacao}`);
  }
}

/** Previsão na unidade publicada (dólares, noites...). */
export function prever(modelo, x) {
  return transformar(modelo, preverBruto(modelo, x));
}

/** Valor de uma feature em x (array na ordem do modelo ou objeto). */
function valorDe(modelo, x, nome) {
  if (Array.isArray(x) || ArrayBuffer.isView(x)) {
    const i = preparar(modelo).indice.get(nome);
    return i === undefined ? undefined : x[i];
  }
  return x ? x[nome] : undefined;
}

/**
 * Quantis do intervalo para esta entrada. `intervalo_por_grupo` ({chave,
 * grupos: {"0": {q_inf, q_sup}, ...}}) vence o global quando o valor da chave
 * tem grupo — o intervalo global cobre 80% no total, não em cada grupo.
 * Devolve {q_inf, q_sup, nivel, grupo} ou null se o modelo não traz intervalo.
 */
export function intervaloDe(modelo, x) {
  const global = modelo.intervalo ?? null;
  const pg = modelo.intervalo_por_grupo;
  if (pg && pg.grupos) {
    const v = paraNumero(valorDe(modelo, x, pg.chave));
    const par = Number.isNaN(v) ? undefined : pg.grupos[String(v)];
    if (par) return { q_inf: par.q_inf, q_sup: par.q_sup, nivel: par.nivel ?? global?.nivel ?? null, grupo: String(v) };
  }
  return global ? { q_inf: global.q_inf, q_sup: global.q_sup, nivel: global.nivel ?? null, grupo: null } : null;
}

/** `teto` do JSON (ex.: 255 noites/ano): política de apresentação, não do modelo. */
function limitar(modelo, v) {
  return typeof modelo.teto === "number" ? Math.min(v, modelo.teto) : v;
}

/**
 * Previsão para exibir: valor, intervalo e teto. Os quantis são resíduos na
 * escala do escore bruto (o log, no modelo de preço): [T(bruto + q_inf),
 * T(bruto + q_sup)]. Sem intervalo, inf/sup vêm null. `prever()` continua sem
 * teto — é ele que a paridade confere contra o LightGBM.
 */
export function preverComIntervalo(modelo, x) {
  const bruto = preverBruto(modelo, x);
  const semTeto = transformar(modelo, bruto);
  const iv = intervaloDe(modelo, x);
  return {
    bruto,
    valor: limitar(modelo, semTeto),
    valorSemTeto: semTeto,
    limitadoPeloTeto: typeof modelo.teto === "number" && semTeto > modelo.teto,
    inf: iv ? limitar(modelo, transformar(modelo, bruto + iv.q_inf)) : null,
    sup: iv ? limitar(modelo, transformar(modelo, bruto + iv.q_sup)) : null,
    nivel: iv ? iv.nivel : null,
    grupo: iv ? iv.grupo : null,
  };
}
