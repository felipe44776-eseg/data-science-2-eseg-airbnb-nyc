/* Paridade Python <-> JavaScript do avaliador LightGBM do site (invariante 10).
 *
 * Lê o modelo exportado por `airbnb.produto.modelo_js.exportar_modelo` e os
 * casos de `gerar_casos_paridade` (entradas + escore bruto e previsão calculados
 * pelo PRÓPRIO LightGBM) e confere que `site/assets/modelo.js` — importado daqui,
 * o MESMO arquivo que a página carrega, não uma cópia — devolve o mesmo número.
 *
 * Por que isto existe: o site é o entregável público. Se o JavaScript divergir
 * do Python, o preço mostrado no "Teste de localização" não é o do modelo
 * validado — e nada no HTML denuncia isso.
 *
 * Reprova (exit 1) se: o escore bruto diverge mais que 1e-9 em algum caso; a
 * previsão transformada diverge mais que 1e-9 relativo; a entrada como objeto
 * {nome: valor} dá número diferente da entrada como array; não há caso com NaN
 * ou com zero; features ou transformação dos dois arquivos não batem.
 *
 * Uso: node tests/paridade_js.mjs [modelo.json casos.json]
 *      (padrão: site/data/modelo_preco.json e site/data/_casos_paridade_preco.json)
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const { preverBruto, prever, preverComIntervalo, transformar, FORMATO } = await import(
  pathToFileURL(resolve(RAIZ, "site/assets/modelo.js")).href);

const TOLERANCIA_BRUTO = 1e-9;
const TOLERANCIA_PREVISAO = 1e-9; // relativa: |js - py| <= tol * max(1, |py|)

const [argModelo, argCasos] = process.argv.slice(2);
const caminhoModelo = argModelo ? resolve(argModelo) : resolve(RAIZ, "site/data/modelo_preco.json");
const caminhoCasos = argCasos ? resolve(argCasos) : resolve(RAIZ, "site/data/_casos_paridade_preco.json");

function reprovar(msg, detalhe) {
  console.error(`\nREPROVADO — ${msg}`);
  if (detalhe !== undefined) console.error(JSON.stringify(detalhe, null, 2));
  process.exit(1);
}

let M, C;
try {
  M = JSON.parse(readFileSync(caminhoModelo, "utf8"));
  C = JSON.parse(readFileSync(caminhoCasos, "utf8"));
} catch (e) {
  reprovar(`não consegui ler os arquivos: ${e.message}`);
}

if (M.formato !== FORMATO) reprovar(`modelo em formato ${M.formato}, esperado ${FORMATO}`);
if (C.formato !== "lightgbm-js-casos/1") reprovar(`casos em formato ${C.formato}`);
if (JSON.stringify(M.features) !== JSON.stringify(C.features)) {
  reprovar("as features dos casos não são as do modelo (nome ou ordem)",
    { modelo: M.features, casos: C.features });
}
if (M.transformacao !== C.transformacao) {
  reprovar(`transformação dos casos (${C.transformacao}) difere da do modelo (${M.transformacao})`);
}
if (!Array.isArray(C.casos) || C.casos.length === 0) reprovar("nenhum caso para conferir");

let piorBruto = 0, casoBruto = null;
let piorPrev = 0, casoPrev = null;
let divergenciaObjeto = null;
let comNaN = 0, comZero = 0;

C.casos.forEach((caso, i) => {
  const b = preverBruto(M, caso.x);
  const p = prever(M, caso.x);
  if (!Number.isFinite(b) || !Number.isFinite(p)) reprovar(`caso ${i}: o JavaScript produziu valor não finito`, caso);
  if (!Number.isFinite(caso.bruto) || !Number.isFinite(caso.pred)) reprovar(`caso ${i}: referência do Python não finita`, caso);

  const db = Math.abs(b - caso.bruto);
  if (db > piorBruto) { piorBruto = db; casoBruto = { i, js: b, ...caso }; }
  const dp = Math.abs(p - caso.pred) / Math.max(1, Math.abs(caso.pred));
  if (dp > piorPrev) { piorPrev = dp; casoPrev = { i, js: p, ...caso }; }

  // a página passa objeto {nome: valor}; tem de dar exatamente o mesmo número
  const obj = Object.fromEntries(M.features.map((f, k) => [f, caso.x[k]]));
  if (preverBruto(M, obj) !== b && divergenciaObjeto === null) divergenciaObjeto = { i, ...caso };

  if (caso.x.some((v) => v === null)) comNaN++;
  if (caso.x.some((v) => v === 0)) comZero++;
});

console.log([
  `modelo                 ${caminhoModelo}`,
  `árvores                ${M.n_arvores} · ${M.features.length} features · ${M.transformacao}`,
  `casos verificados      ${C.casos.length}`,
  `  com NaN (null)       ${comNaN}`,
  `  com zero             ${comZero}`,
  `erro máx. bruto        ${piorBruto.toExponential(3)}   (tolerância ${TOLERANCIA_BRUTO.toExponential(0)})`,
  `erro máx. previsão     ${piorPrev.toExponential(3)}   (relativo; tolerância ${TOLERANCIA_PREVISAO.toExponential(0)})`,
].join("\n"));

// `!(a <= b)` e não `a > b`: um NaN no erro também reprova
if (!(piorBruto <= TOLERANCIA_BRUTO)) reprovar("o escore bruto do JavaScript diverge do LightGBM.", casoBruto);
if (!(piorPrev <= TOLERANCIA_PREVISAO)) reprovar("a previsão transformada diverge do LightGBM.", casoPrev);
if (divergenciaObjeto) reprovar("entrada como objeto dá número diferente da entrada como array.", divergenciaObjeto);
if (comNaN === 0) reprovar("nenhum caso com valor ausente (NaN) foi testado.");
if (comZero === 0) reprovar("nenhum caso com zero foi testado.");

/* --- intervalo e teto (o que o simulador exibe) ---------------------------
 * Não vêm do LightGBM, mas são rederivados aqui de forma independente: o par de
 * quantis do grupo da entrada (intervalo_por_grupo) ou o global, aplicado ao
 * escore bruto, com o teto do JSON. */
if (M.intervalo || M.intervalo_por_grupo || typeof M.teto === "number") {
  const pg = M.intervalo_por_grupo;
  const iGrupo = pg ? M.features.indexOf(pg.chave) : -1;
  if (pg && iGrupo < 0) reprovar(`intervalo_por_grupo.chave "${pg.chave}" não é feature do modelo`);
  const limitar = (v) => (typeof M.teto === "number" ? Math.min(v, M.teto) : v);
  let usaramGrupo = 0;
  C.casos.forEach((caso, i) => {
    const r = preverComIntervalo(M, caso.x);
    const b = preverBruto(M, caso.x);
    let q = M.intervalo ?? null;
    const g = iGrupo >= 0 && caso.x[iGrupo] !== null ? pg.grupos[String(caso.x[iGrupo])] : undefined;
    if (g) { q = g; usaramGrupo++; }
    const esperado = {
      valor: limitar(transformar(M, b)),
      inf: q ? limitar(transformar(M, b + q.q_inf)) : null,
      sup: q ? limitar(transformar(M, b + q.q_sup)) : null,
    };
    if (r.valor !== esperado.valor || r.inf !== esperado.inf || r.sup !== esperado.sup) {
      reprovar(`caso ${i}: intervalo/teto exibido difere do esperado`, { esperado, obtido: r, caso });
    }
    // só vale quando os quantis cercam o zero (um grupo com viés pode não cercar)
    if (q && q.q_inf <= 0 && q.q_sup >= 0 && !(r.inf <= r.valor && r.valor <= r.sup)) {
      reprovar(`caso ${i}: valor fora do próprio intervalo`, r);
    }
  });
  if (pg && usaramGrupo === 0) {
    reprovar("intervalo_por_grupo nunca foi usado: as chaves dos grupos não batem com os valores da feature");
  }
  console.log(`intervalo/teto         conferidos${pg ? ` (${usaramGrupo} casos com intervalo do grupo)` : ""}`);
}

console.log("\nAPROVADO — o site calcula o mesmo que o LightGBM.");
