/* Ponto de entrada do site: carrega site/data/*.json, monta cabeçalho, mapa,
 * simulador e rodapé. Tudo o que é texto de dado (métricas, equipe, fontes,
 * campos do formulário) vem dos JSON — nada disso é codificado aqui.
 *
 * Unidades: fatias (pct_* dos KPIs, sobrevivencia.pct, mdape, cobertura_80)
 * aceitam fração (0,817) ou pontos (81,7) — decidido pelo conjunto de valores;
 * *_pct de variação (melhora_vs_baseline_pct) vem em pontos.
 *
 * O mapa é importado sob demanda: se a MapLibre não carregar (navegador sem
 * WebGL 2, por exemplo), o simulador continua funcionando pela busca.
 */
import { GRUPOS_PT, emPontos, esc } from "./comum.js";
import { PALETAS, dolares, fatorExibicao, numero, pct } from "./escalas.js";
import { criarSimulador } from "./simulador.js";

// relativo ao MODULO (assets/), nao a pagina: o mapa pode viver em qualquer
// caminho do site sem que os dados mudem de lugar
const DADOS = new URL("../data/", import.meta.url);
const $ = (id) => document.getElementById(id);

async function carregar(nome) {
  const r = await fetch(new URL(nome, DADOS));
  if (!r.ok) throw new Error(`${nome}: HTTP ${r.status}`);
  return r.json();
}

/** Arquivo opcional: ausente (404) vira null, sem exceção. */
async function carregarOpcional(nome) {
  try {
    const r = await fetch(new URL(nome, DADOS));
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

/* ---------------------------------------------------------------- tema */
const TEMAS = ["auto", "light", "dark"];
const ROTULO_TEMA = { auto: "automático", light: "claro", dark: "escuro" };
const escuroNoSistema = matchMedia("(prefers-color-scheme: dark)");

function temaSalvo() {
  try { return localStorage.getItem("tema") ?? "auto"; } catch { return "auto"; }
}
function salvarTema(t) {
  try { if (t === "auto") localStorage.removeItem("tema"); else localStorage.setItem("tema", t); } catch { /* sem armazenamento */ }
}
function temaEfetivo(escolha) {
  if (escolha === "light") return "claro";
  if (escolha === "dark") return "escuro";
  return escuroNoSistema.matches ? "escuro" : "claro";
}

let escolhaTema = TEMAS.includes(temaSalvo()) ? temaSalvo() : "auto";
const aoMudarTema = [];

function aplicarEscolhaTema() {
  if (escolhaTema === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = escolhaTema;
  $("botao-tema-rotulo").textContent = `Tema: ${ROTULO_TEMA[escolhaTema]}`;
  const efetivo = temaEfetivo(escolhaTema);
  for (const f of aoMudarTema) f(efetivo);
}
$("botao-tema").addEventListener("click", () => {
  escolhaTema = TEMAS[(TEMAS.indexOf(escolhaTema) + 1) % TEMAS.length];
  salvarTema(escolhaTema);
  aplicarEscolhaTema();
});
escuroNoSistema.addEventListener("change", () => { if (escolhaTema === "auto") aplicarEscolhaTema(); });
aplicarEscolhaTema();

/* ---------------------------------------------------------------- cabeçalho */
function renderizarCabecalho(resumo) {
  for (const s of document.querySelectorAll("[data-snapshot]")) {
    const data = resumo.snapshots?.[s.dataset.snapshot];
    if (data) s.title = `snapshot de ${data}`;
  }
  const k19 = resumo.kpis?.["2019"] ?? {};
  const k26 = resumo.kpis?.["2026"] ?? {};
  // fatias em fração (0,817) ou em pontos (81,7): decide pelo conjunto, não por valor
  const fatias = [k19, k26].flatMap((k) => ["pct_min30", "pct_inteiro", "pct_host_multi"].map((c) => k[c]))
    .filter((v) => typeof v === "number");
  const fk = fatias.length && fatias.every((v) => Math.abs(v) <= 1) ? 100 : 1;
  const itens = [
    { rotulo: "Anúncios ativos", chave: "anuncios", fmt: (v) => numero(v, 0) },
    { rotulo: "Preço mediano por noite, em dólar de hoje*", chave: "preco_mediano_real", fmt: dolares },
    { rotulo: "Exigem 30 noites ou mais", chave: "pct_min30", fmt: (v) => pct(v * fk) },
    { rotulo: "Casa ou apartamento inteiro", chave: "pct_inteiro", fmt: (v) => pct(v * fk) },
    { rotulo: "De anfitriões com vários anúncios", chave: "pct_host_multi", fmt: (v) => pct(v * fk) },
  ];
  // preço estratificado por estadia (invariante 8), se o resumo trouxer
  const estrato = (ano, e) => resumo.kpis?.[ano]?.precos_por_estadia?.[e];
  if (estrato("2019", "curta") !== undefined) {
    itens.splice(1, 1,
      { rotulo: "Preço mediano, estadia < 30 noites (dólar de hoje)", valores: [estrato("2019", "curta"), estrato("2026", "curta")], fmt: dolares },
      { rotulo: "Preço mediano, estadia ≥ 30 noites (dólar de hoje)", valores: [estrato("2019", "longa"), estrato("2026", "longa")], fmt: dolares });
  }
  $("kpis").innerHTML = itens.map((it) => {
    const [a, b] = it.valores ?? [k19[it.chave], k26[it.chave]];
    if (a === undefined && b === undefined) return "";
    const v = (x) => (x === undefined || x === null ? "—" : it.fmt(x));
    return `<li class="kpi"><p class="kpi-rotulo">${esc(it.rotulo)}</p>
      <dl class="kpi-anos"><div><dt>2019</dt><dd>${v(a)}</dd></div><div><dt>2026</dt><dd>${v(b)}</dd></div></dl>
      ${it.nota ? `<p class="kpi-nota">${esc(it.nota)}</p>` : ""}</li>`;
  }).join("");
  const s = resumo.sobrevivencia;
  if (s && typeof s.pct === "number") {
    $("kpis").insertAdjacentHTML("beforeend", `<li class="kpi"><p class="kpi-rotulo">Anúncios de 2019 que ainda existem em 2026</p>
      <dl class="kpi-anos"><div><dt>2026</dt><dd>${pct(emPontos(s.pct))}</dd></div></dl>
      ${typeof s.n === "number" ? `<p class="kpi-nota">${numero(s.n, 0)} anúncios</p>` : ""}</li>`);
  }
  const notas = [];
  if (estrato("2019", "curta") === undefined) {
    notas.push("*Não compare os dois preços direto: em 2026 a maioria dos anúncios é de estadia de 30 noites ou mais, cotada com desconto mensal.");
  }
  if (resumo.cpi?.fator) {
    notas.push(`Preços de 2019 corrigidos pela inflação de Nova York (CPI-U): ×${numero(resumo.cpi.fator, 3)}, de ${resumo.cpi.de} a ${resumo.cpi.para}.`);
  }
  notas.push("Desde 2023, estadias com menos de 30 noites exigem registro na prefeitura (Local Law 18) — por isso o mercado de 2026 é outro.");
  $("nota-kpis").textContent = notas.join(" ");
}

function renderizarSecoes(resumo) {
  $("cartoes-metricas").innerHTML = (resumo.metricas_celula ?? []).map((m) => `<div class="cartao">
      <h3>${esc(m.rotulo)}</h3>
      ${m.descricao ? `<p>${esc(m.descricao)}</p>` : ""}
      ${m.como ? `<p><b>Como calculamos:</b> ${esc(m.como)}</p>` : ""}</div>`).join("");
  const mp = resumo.modelo_preco ?? {};
  const itens = [
    ["mae_usd", "erro absoluto médio", (v) => dolares(v)],
    ["mdape", "erro percentual mediano", (v) => pct(emPontos(v))],
    ["cobertura_80", "dos preços reais dentro da faixa de 80%", (v) => pct(emPontos(v))],
    ["r2_log", "R² na escala do log do preço", (v) => numero(v, 2)],
    ["melhora_vs_baseline_pct", "menos erro que a média do bairro", (v) => pct(v)],
  ];
  $("metricas-modelo").innerHTML = itens.filter(([k]) => typeof mp[k] === "number")
    .map(([k, rotulo, fmt]) => `<li><b>${fmt(mp[k])}</b>${esc(rotulo)}</li>`).join("");
}

function renderizarRodape(resumo) {
  $("equipe").innerHTML = (resumo.equipe ?? []).map((p) => {
    const ra = p.ra ? `RA ${esc(p.ra)}` : "RA a confirmar";
    const gh = p.github ? ` · <a href="https://github.com/${esc(p.github)}" target="_blank" rel="noopener">@${esc(p.github)}</a>` : "";
    return `<li>${esc(p.nome)} <span class="ra">(${ra})</span>${gh}</li>`;
  }).join("");
  $("credito").textContent = resumo.credito ?? "";
  if (resumo.repositorio) $("link-repositorio").href = resumo.repositorio;
  else $("link-repositorio").hidden = true;
  $("atribuicoes").innerHTML = (resumo.atribuicoes ?? []).map((a) => `<li>${a.url
    ? `<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.fonte)}</a>` : esc(a.fonte)}${a.texto ? ` — ${esc(a.texto)}` : ""}</li>`).join("");
  const partes = [];
  if (resumo.gerado_em) partes.push(`Dados gerados em ${resumo.gerado_em}`);
  if (resumo.snapshots) partes.push(`anúncios de ${resumo.snapshots["2019"]} e ${resumo.snapshots["2026"]}`);
  $("gerado-em").textContent = partes.join(" · ");
}

/* ---------------------------------------------------------------- legenda */
function renderizarLegenda(metrica, escala) {
  if (!metrica || !escala) { $("legenda").innerHTML = ""; return; }
  const itens = escala.classes.map((c) => `<li><span class="sw" style="background:${c.cor}"></span>${esc(c.rotulo)}</li>`).join("");
  const nulo = `<li><span class="sw nulo"></span>sem dado (tracejado)</li>`;
  $("legenda").innerHTML = `<p class="legenda-titulo">${esc(metrica.rotulo)}</p>
    ${metrica.unidade ? `<p class="legenda-unidade">em ${esc(metrica.unidade)}</p>` : ""}
    <ul class="legenda-lista">${itens}${nulo}</ul>
    ${metrica.descricao || metrica.como ? `<details><summary>O que é isto?</summary>${metrica.descricao ? `<p>${esc(metrica.descricao)}</p>` : ""}${metrica.como ? `<p><b>Como calculamos:</b> ${esc(metrica.como)}</p>` : ""}</details>` : ""}`;
}

function renderizarLegendaPontos(tema) {
  const on = $("camada-anuncios").checked;
  const el = $("legenda-pontos");
  el.hidden = !on;
  if (!on) return;
  const cores = (PALETAS[tema] ?? PALETAS.claro).tipos;
  el.innerHTML = GRUPOS_PT.map((g, i) => `<li><span class="sw" style="background:${cores[i]}"></span>${esc(g)}</li>`).join("");
}

function avisar(texto) {
  const el = $("aviso-mapa");
  el.textContent = texto;
  el.hidden = false;
}

/* ---------------------------------------------------------------- início */
async function iniciar() {
  let resumo;
  try {
    resumo = await carregar("resumo.json");
  } catch (erro) {
    console.error("[site] resumo.json:", erro);
    $("kpis").innerHTML = `<li class="kpi erro-carga">Não foi possível carregar os dados do site (${esc(erro.message)}).</li>`;
    return;
  }
  renderizarCabecalho(resumo);
  renderizarSecoes(resumo);
  renderizarRodape(resumo);

  let dados;
  try {
    const [r8, r9, bairros, metro, anuncios, modeloPreco, modeloOcupacao] = await Promise.all([
      carregar("celulas_r8.json"), carregar("celulas_r9.json"), carregar("bairros.geojson"),
      carregar("metro.geojson"), carregar("anuncios_2026.json"), carregar("modelo_preco.json"),
      // o modelo de ocupação é opcional: ausente, a seção some
      // (se o resumo declarar "modelo_ocupacao": false, nem pede — evita um 404 no console)
      resumo.modelo_ocupacao === false ? Promise.resolve(null) : carregarOpcional("modelo_ocupacao.json"),
    ]);
    dados = { resumo, r8, r9, bairros, metro, anuncios, modeloPreco, modeloOcupacao };
  } catch (erro) {
    console.error("[site] dados:", erro);
    $("res-resumo").innerHTML = `<p class="erro-carga">Não foi possível carregar os dados do simulador (${esc(erro.message)}).</p>`;
    return;
  }


  // fator de exibição de cada medida (fração x pontos), a partir dos próprios valores
  for (const m of resumo.metricas_celula ?? []) {
    const i = dados.r8.colunas.indexOf(m.chave);
    m.fator = fatorExibicao(m, i < 0 ? [] : dados.r8.linhas.map((l) => l[i]));
  }

  let tema = temaEfetivo(escolhaTema);
  const simulador = criarSimulador({
    dados,
    tema,
    el: {
      campos: $("campos"), resumo: $("res-resumo"), detalhes: $("res-detalhes"), resultado: $("resultado"),
      ponto: $("ponto-escolhido"), painel: $("simulador"), alca: $("alca"),
      formBusca: $("form-busca"), busca: $("busca"), botaoBusca: $("botao-busca"),
      statusBusca: $("busca-status"), resultadosBusca: $("busca-resultados"),
    },
  });

  // folha inferior no celular
  $("alca").addEventListener("click", () => {
    const aberto = $("simulador").dataset.estado !== "aberto";
    $("simulador").dataset.estado = aberto ? "aberto" : "fechado";
    $("alca").setAttribute("aria-expanded", String(aberto));
    $("alca").querySelector("span").textContent = aberto ? "Recolher" : "Ver detalhes";
  });
  if (matchMedia("(max-width: 880px)").matches) $("mapa-controles").open = false;

  // seletor de medida (lista vinda do resumo, não do código)
  const metricas = resumo.metricas_celula ?? [];
  $("metrica").innerHTML = metricas.map((m, i) => `<option value="${i}">${esc(m.rotulo)}</option>`).join("");

  let api = null;
  try {
    const { criarMapa } = await import("./mapa.js");
    api = await criarMapa({
      container: $("mapa"),
      dados: { r8: dados.r8, bairros: dados.bairros, metro: dados.metro, anuncios: dados.anuncios, metricas },
      tema,
      aoEscolherPonto: (p) => simulador.escolherPonto(p),
      aoAvisar: avisar,
      aoFalhar: (erro) => {
        console.warn("[mapa] indisponível:", erro);
        avisar("Este navegador não conseguiu desenhar o mapa (WebGL 2 indisponível). A busca por endereço continua funcionando.");
      },
    });
  } catch (erro) {
    console.warn("[mapa] indisponível:", erro);
    avisar("O mapa não pôde ser carregado neste navegador. A busca por endereço continua funcionando.");
  }

  if (api) {
    simulador.definirMapa(api);
    const escolherMetrica = () => {
      const m = metricas[Number($("metrica").value)];
      renderizarLegenda(m, api.definirMetrica(m));
    };
    $("metrica").addEventListener("change", escolherMetrica);
    escolherMetrica();
    for (const [id, camada] of [["camada-hex", "hex"], ["camada-bairros", "bairros"], ["camada-anuncios", "anuncios"], ["camada-metro", "metro"]]) {
      $(id).addEventListener("change", () => {
        api.alternar(camada, $(id).checked);
        if (camada === "anuncios") renderizarLegendaPontos(tema);
      });
    }
    $("usar-centro").addEventListener("click", () => simulador.escolherPonto({ ...api.centro(), origem: "centro" }));
    for (const ev of ["mouseenter", "focus"]) $("usar-centro").addEventListener(ev, () => $("mira").classList.add("visivel"));
    for (const ev of ["mouseleave", "blur"]) $("usar-centro").addEventListener(ev, () => $("mira").classList.remove("visivel"));
  } else {
    $("mapa-controles").hidden = true;
    $("usar-centro").parentElement.hidden = true;
  }

  aoMudarTema.push(async (novo) => {
    tema = novo;
    simulador.definirTema(novo);
    renderizarLegendaPontos(novo);
    if (api) {
      await api.definirTema(novo);
      const m = metricas[Number($("metrica").value)];
      renderizarLegenda(m, api.definirMetrica(m));
    }
  });
}

iniciar();
