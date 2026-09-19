/* "Teste de localização": formulário, previsão, prêmio da localização,
 * ocupação/receita, contexto de 2019, comparáveis e busca de endereço.
 *
 * Nada aqui está codificado para um modelo específico: os campos vêm de
 * modelo_preco.json → "entradas_usuario"; as features da área vêm de
 * celulas_r9.json (colunas nomeadas em "features_local"); o resto vem de
 * "features_fixas". A previsão é a de modelo.js — o mesmo arquivo que a
 * paridade confere contra o LightGBM.
 *
 * Localização = célula H3 r9 (ADR 0001): dois cliques no mesmo hexágono dão o
 * mesmo preço. "features_ponto", se existir, recebe o CENTRO da célula.
 */
import { cellToLatLng, cellToParent, latLngToCell } from "../vendor/h3-js-4.5.0/h3-js.es.js";
import { GRUPOS_PT, TIPOS_PT, emPontos, esc, grupoDoTipo, reduzirMovimento } from "./comum.js";
import { PALETAS, dolares, formatarMetrica, metros, numero, pct } from "./escalas.js";
import { prever, preverComIntervalo } from "./modelo.js";

const RES_FEATURES = 9;
const RES_MAPA = 8;
const K_COMPARAVEIS = 5;
const RAIO_COMPARAVEIS_M = 3000;

const NOMINATIM = "https://nominatim.openstreetmap.org/search";
const VIEWBOX_NYC = "-74.2591,40.9176,-73.7004,40.4774"; // oeste,norte,leste,sul (config.NYC_BBOX)

/** Distância em metros (haversine). */
function distancia(lat1, lon1, lat2, lon2) {
  const r = 6371008.8;
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

/** features_ponto: lista de nomes (lat/lon pelo nome) ou {feature: "lat"|"lon"}. */
function featuresPonto(modelo) {
  const fp = modelo.features_ponto;
  if (!fp) return new Map();
  if (Array.isArray(fp)) return new Map(fp.map((n) => [n, /lat/i.test(n) ? "lat" : "lon"]));
  return new Map(Object.entries(fp));
}

/** Campos do formulário: os do modelo de preço, depois os que só o de ocupação usa. */
function unirEntradas(...modelos) {
  const vistas = new Map();
  for (const m of modelos) for (const e of m?.entradas_usuario ?? []) if (!vistas.has(e.chave)) vistas.set(e.chave, e);
  return [...vistas.values()];
}

const opcional = (e) => e.opcional === true || e.padrao === null || e.padrao === undefined;

export function criarSimulador({ dados, el, tema: temaInicial }) {
  const { resumo, r8, r9, anuncios, modeloPreco: mp, modeloOcupacao: mo } = dados;
  let tema = temaInicial;
  let mapaApi = null;
  const estado = { ponto: null, celula: null, rotulo: null };

  /* ---- índices ------------------------------------------------------------ */
  const iR8 = Object.fromEntries(r8.colunas.map((c, i) => [c, i]));
  const linhasR8 = new Map(r8.linhas.map((l) => [l[iR8.h3], l]));
  const metricas = resumo.metricas_celula ?? [];
  // papel declarado em resumo.json ("papel"); na falta, o das chaves que o
  // exportador do projeto usa — só para a frase de contexto, nunca para o mapa
  const PAPEL_POR_CHAVE = {
    n_2019: "anuncios_2019", preco_2019_real: "preco_2019",
    n_2026: "anuncios_2026", preco_2026: "preco_2026",
    var_n_pct: "var_anuncios_pct", var_preco_real_pct: "var_preco_pct",
  };
  const porPapel = (p) => metricas.find((m) => (m.papel ?? PAPEL_POR_CHAVE[m.chave]) === p);
  const ref = r9.referencia && r9.celulas[r9.referencia] ? r9.referencia : null;
  const colAn = Object.fromEntries(anuncios.colunas.map((c, i) => [c, i]));

  const problemas = [];
  for (const [nome, m] of [["preço", mp], ["ocupação", mo]]) {
    if (!m) continue;
    const faltam = (m.features_local ?? []).filter((f) => !r9.colunas.includes(f));
    if (faltam.length) problemas.push(`modelo de ${nome}: features da área ausentes em celulas_r9.json (${faltam.join(", ")})`);
  }
  if (problemas.length) console.error("[simulador] dados inconsistentes:", problemas);

  const entradas = unirEntradas(mp, mo);
  const entradaPorChave = new Map(entradas.map((e) => [e.chave, e]));

  /* ---- formulário ----------------------------------------------------------- */
  const campos = el.campos;
  const idCampo = (chave) => `campo-${chave.replace(/[^\w-]/g, "_")}`;

  function htmlCampo(e) {
    const id = idCampo(e.chave);
    const ajuda = e.ajuda ? `<p class="ajuda" id="${id}-ajuda">${esc(e.ajuda)}</p>` : "";
    const erro = `<p class="erro" id="${id}-erro" hidden></p>`;
    const desc = [e.ajuda ? `${id}-ajuda` : "", `${id}-erro`].filter(Boolean).join(" ");
    if (e.tipo === "categoria") {
      const ops = e.opcoes ?? [];
      if (ops.length <= 4) {
        const radios = ops.map((o, i) => `<label><input type="radio" name="${esc(e.chave)}" value="${esc(o.valor)}"${String(o.valor) === String(e.padrao) || (e.padrao == null && i === 0) ? " checked" : ""}> ${esc(o.rotulo)}</label>`).join("");
        return `<div class="campo"><fieldset aria-describedby="${desc}"><legend>${esc(e.rotulo)}</legend><div class="segmentado">${radios}</div></fieldset>${ajuda}${erro}</div>`;
      }
      const opts = ops.map((o) => `<option value="${esc(o.valor)}"${String(o.valor) === String(e.padrao) ? " selected" : ""}>${esc(o.rotulo)}</option>`).join("");
      return `<div class="campo"><label for="${id}">${esc(e.rotulo)}</label><select id="${id}" name="${esc(e.chave)}" aria-describedby="${desc}">${opts}</select>${ajuda}${erro}</div>`;
    }
    if (e.tipo === "booleano") {
      return `<div class="campo"><label class="caixa"><input type="checkbox" id="${id}" name="${esc(e.chave)}"${e.padrao ? " checked" : ""} aria-describedby="${desc}"> <span>${esc(e.rotulo)}</span></label>${ajuda}${erro}</div>`;
    }
    const passo = e.passo ?? (e.tipo === "inteiro" ? 1 : "any");
    const attrs = [
      `type="number"`, `id="${id}"`, `name="${esc(e.chave)}"`, `step="${esc(passo)}"`,
      e.min !== undefined ? `min="${esc(e.min)}"` : "", e.max !== undefined ? `max="${esc(e.max)}"` : "",
      e.padrao !== null && e.padrao !== undefined ? `value="${esc(e.padrao)}"` : "",
      `inputmode="${e.tipo === "inteiro" ? "numeric" : "decimal"}"`,
      opcional(e) ? `placeholder="em branco = sem informação"` : "",
      `aria-describedby="${desc}"`,
    ].filter(Boolean).join(" ");
    const rotulo = `${esc(e.rotulo)}${opcional(e) ? ' <span class="res-sub">(opcional)</span>' : ""}`;
    return `<div class="campo"><label for="${id}">${rotulo}</label><input ${attrs}>${ajuda}${erro}</div>`;
  }

  function renderizarCampos() {
    const cats = entradas.filter((e) => e.tipo === "categoria").map(htmlCampo).join("");
    const nums = entradas.filter((e) => e.tipo === "inteiro" || e.tipo === "decimal").map(htmlCampo).join("");
    const bools = entradas.filter((e) => e.tipo === "booleano").map(htmlCampo).join("");
    campos.innerHTML = `${cats}${nums ? `<div class="campos-duplos">${nums}</div>` : ""}${bools}`;
    if (!entradas.length) campos.innerHTML = `<p class="res-sub">Este modelo não pede dados do imóvel.</p>`;
  }

  function mostrarErro(chave, msg) {
    const id = idCampo(chave);
    const alvo = document.getElementById(id) ?? campos.querySelector(`[name="${CSS.escape(chave)}"]`);
    const p = document.getElementById(`${id}-erro`);
    if (alvo) alvo.setAttribute("aria-invalid", msg ? "true" : "false");
    if (p) { p.textContent = msg ?? ""; p.hidden = !msg; }
  }

  function lerFormulario() {
    const valores = {};
    const erros = [];
    for (const e of entradas) {
      let msg = null;
      if (e.tipo === "categoria") {
        const marcado = campos.querySelector(`[name="${CSS.escape(e.chave)}"]:checked`) ?? campos.querySelector(`select[name="${CSS.escape(e.chave)}"]`);
        const op = (e.opcoes ?? []).find((o) => String(o.valor) === marcado?.value);
        valores[e.chave] = op ? op.valor : (e.padrao ?? null);
      } else if (e.tipo === "booleano") {
        valores[e.chave] = document.getElementById(idCampo(e.chave))?.checked ? 1 : 0;
      } else {
        const input = document.getElementById(idCampo(e.chave));
        const s = (input?.value ?? "").trim();
        if (input?.validity?.badInput) msg = "Digite um número.";
        else if (s === "") {
          if (opcional(e)) valores[e.chave] = null;
          else msg = "Preencha este campo.";
        } else {
          const n = Number(s);
          if (!Number.isFinite(n)) msg = "Digite um número.";
          else if (e.tipo === "inteiro" && !Number.isInteger(n)) msg = "Use um número inteiro.";
          else if ((e.min !== undefined && n < e.min) || (e.max !== undefined && n > e.max)) {
            msg = `Use um valor entre ${numero(e.min ?? -Infinity)} e ${numero(e.max ?? Infinity)}.`;
          } else valores[e.chave] = n;
        }
      }
      mostrarErro(e.chave, msg);
      if (msg) erros.push({ chave: e.chave, rotulo: e.rotulo, msg });
    }
    return { valores, erros };
  }

  /* ---- montagem da entrada do modelo --------------------------------------- */
  function valoresDaCelula(h) {
    const linha = r9.celulas[h];
    if (!linha) return null;
    return Object.fromEntries(r9.colunas.map((c, i) => [c, linha[i]]));
  }

  function montar(modelo, celula, form) {
    const loc = valoresDaCelula(celula) ?? {};
    const [clat, clon] = cellToLatLng(celula);
    const locais = new Set(modelo.features_local ?? []);
    const ponto = featuresPonto(modelo);
    const fixas = modelo.features_fixas ?? {};
    const x = {};
    const origem = {};
    for (const f of modelo.features) {
      if (locais.has(f)) { x[f] = loc[f] ?? null; origem[f] = "área"; } else if (ponto.has(f)) {
        x[f] = ponto.get(f) === "lat" ? clat : clon; origem[f] = "área";
      } else if (Object.hasOwn(form, f)) { x[f] = form[f]; origem[f] = "você"; } else if (Object.hasOwn(fixas, f)) {
        x[f] = fixas[f]; origem[f] = "fixo";
      } else { x[f] = null; origem[f] = "ausente"; }
    }
    return { x, origem };
  }

  /* ---- contexto, comparáveis --------------------------------------------- */
  function linhaR8(celula9) {
    const pai = cellToParent(celula9, RES_MAPA);
    return linhasR8.get(pai) ?? null;
  }
  function nomeArea(celula9) {
    const l = linhaR8(celula9);
    if (!l) return null;
    const b = l[iR8.bairro];
    const d = l[iR8.distrito];
    return b ? (d ? `${b}, ${d}` : b) : d ?? null;
  }

  /**
   * Frase de contexto da célula r8. Usa o que o resumo trouxer: níveis de 2019
   * (papéis anuncios_2019 / preco_2019) ou os de 2026 com a variação desde 2019
   * (anuncios_2026 + var_anuncios_pct, preco_2026 + var_preco_pct). Nunca deriva
   * o nível de 2019 de uma variação — a definição exata da variação é do exportador.
   */
  function contexto2019(celula9) {
    const l = linhaR8(celula9);
    const val = (papel) => {
      const m = porPapel(papel);
      const v = l && m ? l[iR8[m.chave]] : undefined;
      return typeof v === "number" ? { v, m } : null;
    };
    const area = "esta área (hexágono de ~0,7 km²)";
    const qtd = (n) => `<b>${numero(n, 0)}</b> ${n === 1 ? "anúncio" : "anúncios"}`;
    const frases = [];
    const n19 = val("anuncios_2019");
    const p19 = val("preco_2019");
    const n26 = val("anuncios_2026");
    const dn = val("var_anuncios_pct");
    const p26 = val("preco_2026");
    const dp = val("var_preco_pct");
    if (n19) {
      let f = n19.v ? `Em 2019, ${area} tinha ${qtd(n19.v)}` : `Em 2019, ${area} não tinha anúncios no Airbnb`;
      if (p19) f += `, com preço mediano de <b>${dolares(p19.v)}</b> por noite (em dólar de hoje)`;
      frases.push(`${f}.`);
    } else if (n26) {
      let f = `Hoje ${area} tem ${qtd(n26.v)}`;
      if (dn) {
        const dnPts = dn.v * (dn.m.fator ?? 1);
        f += Math.abs(dnPts) < 1 ? ", praticamente o mesmo número de 2019"
          : ` — ${formatarMetrica(dn.m, Math.abs(dn.v), { sinal: false })} ${dn.v > 0 ? "a mais" : "a menos"} que em 2019`;
      }
      frases.push(`${f}.`);
    } else if (porPapel("anuncios_2019") || porPapel("anuncios_2026")) {
      frases.push(`Não há anúncios suficientes em ${area} para descrever o mercado local.`);
    }
    if (!p19 && (p26 || dp)) {
      const partes = [];
      if (p26) partes.push(`preço mediano de <b>${dolares(p26.v)}</b> por noite hoje`);
      if (dp) partes.push(`${esc(dp.m.rotulo).toLowerCase()} desde 2019: <b>${formatarMetrica(dp.m, dp.v, { sinal: true })}</b>`);
      frases.push(`${partes.join("; ").replace(/^./, (c) => c.toUpperCase())}.`);
    }
    return frases.length ? frases.join(" ") : null;
  }

  function comparaveis(ponto, form) {
    // chave_tipo declarada no modelo; na falta, room_type_cod (códigos na ordem de "tipos")
    const chaveTipo = mp.chave_tipo ?? (entradaPorChave.get("room_type_cod")?.tipo === "categoria" ? "room_type_cod" : undefined);
    const tipo = chaveTipo !== undefined && form[chaveTipo] !== null && form[chaveTipo] !== undefined ? Number(form[chaveTipo]) : null;
    const lista = [];
    for (const l of anuncios.linhas) {
      const preco = l[colAn.preco];
      if (typeof preco !== "number") continue;
      if (tipo !== null && l[colAn.tipo] !== tipo) continue;
      const d = distancia(ponto.lat, ponto.lon, l[colAn.lat], l[colAn.lon]);
      if (d > RAIO_COMPARAVEIS_M) continue;
      lista.push({ d, preco, tipo: l[colAn.tipo], bairro: l[colAn.bairro] });
    }
    lista.sort((a, b) => a.d - b.d);
    return { itens: lista.slice(0, K_COMPARAVEIS), porTipo: tipo !== null, tipo };
  }

  /* ---- rótulos e valores para o "como chegamos" ---------------------------- */
  const rotuloFeature = (f) => mp.rotulos?.[f] ?? entradaPorChave.get(f)?.rotulo ?? r9.rotulos?.[f] ?? f;
  function valorLegivel(f, v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "sem dado";
    const e = entradaPorChave.get(f);
    if (e?.tipo === "categoria") return (e.opcoes ?? []).find((o) => String(o.valor) === String(v))?.rotulo ?? String(v);
    if (e?.tipo === "booleano") return v ? "sim" : "não";
    return typeof v === "number" ? numero(v) : String(v);
  }

  /* ---- renderização --------------------------------------------------------- */
  const resumoEl = el.resumo;
  const detalhesEl = el.detalhes;

  function vazio(msg) {
    el.resultado.dataset.estado = "vazio";
    delete el.resultado.dataset.celula;
    delete el.resultado.dataset.valor;
    resumoEl.innerHTML = `<p class="res-sub">${msg}</p>`;
    detalhesEl.innerHTML = "";
  }

  function blocoIntervalo(r, formatador) {
    if (r.inf === null || r.sup === null) return "";
    const lo = Math.min(r.inf, r.valor) * 0.85;
    const hi = Math.max(r.sup, r.valor) * 1.08;
    const pos = (v) => `${(((v - lo) / (hi - lo)) * 100).toFixed(1)}%`;
    const nivel = Math.round((r.nivel ?? 0.8) * 100);
    return `<p class="res-faixa">Faixa de ${nivel}%: de <b>${formatador(r.inf)}</b> a <b>${formatador(r.sup)}</b></p>
      <div class="faixa-visual" aria-hidden="true"><span class="barra" style="left:${pos(r.inf)};width:calc(${pos(r.sup)} - ${pos(r.inf)})"></span><span class="marca" style="left:${pos(r.valor)}"></span></div>`;
  }

  function render({ r, premio, valorRef, ocup, ctx, comps, montado }) {
    el.resultado.dataset.estado = "cheio";
    // auditável: a célula usada e o valor sem arredondar (conferidos contra o Python)
    el.resultado.dataset.celula = estado.celula;
    el.resultado.dataset.valor = String(r.valor);
    resumoEl.innerHTML = `<p class="res-rotulo">Preço por noite estimado (valor típico)</p>
      <p class="res-numero">${dolares(r.valor)} <small>por noite</small></p>${blocoIntervalo(r, dolares)}`;

    const blocos = [];
    if (premio !== null) {
      const txt = Math.abs(premio) < 0.01 ? "praticamente igual à" : premio > 0 ? "acima da" : "abaixo da";
      const nomeRef = nomeArea(ref);
      blocos.push(`<div class="res-bloco"><p class="res-rotulo">Efeito da localização</p>
        <p><span class="res-destaque">${pct(premio * 100, { sinal: true })}</span> <span class="res-sub">${txt} área de referência</span></p>
        <p>O mesmo imóvel, com as mesmas características, sairia por cerca de <b>${dolares(valorRef)}</b> na área de referência${nomeRef ? ` (${esc(nomeRef)})` : ""}. A diferença vem só do lugar.</p></div>`);
    }
    if (ocup) {
      const noites = ocup.valor;
      const receita = r.valor * noites;
      const faixa = ocup.inf !== null && ocup.sup !== null ? ` <span class="res-sub">(faixa de ${Math.round((ocup.nivel ?? 0.8) * 100)}%: ${numero(ocup.inf, 0)} a ${numero(ocup.sup, 0)})</span>` : "";
      const teto = ocup.limitadoPeloTeto ? `<p class="res-sub">Limitado a ${numero(mo.teto, 0)} noites por ano, o teto da estimativa de ocupação do Inside Airbnb.</p>` : "";
      blocos.push(`<div class="res-bloco"><p class="res-rotulo">Se você operar o anúncio</p>
        <p><span class="res-destaque">~${numero(noites, 0)}</span> noites/ano ocupadas${faixa} <span class="res-sub">(anúncios ativos parecidos)</span></p>
        <p>Receita bruta estimada: <b>~${dolares(Math.round(receita / 100) * 100)}</b> por ano <span class="res-sub">(preço previsto × noites; sem taxas nem custos)</span></p>${teto}</div>`);
    }
    if (ctx) blocos.push(`<div class="res-bloco"><p>${ctx}</p></div>`);

    const cores = (PALETAS[tema] ?? PALETAS.claro).tipos;
    if (comps.itens.length) {
      const tipoTxt = comps.porTipo ? (TIPOS_PT[anuncios.tipos[comps.tipo]] ?? "do mesmo tipo").toLowerCase() : "de qualquer tipo";
      const itens = comps.itens.map((c) => {
        const g = grupoDoTipo(anuncios.tipos[c.tipo]);
        const tipo = comps.porTipo ? "" : ` · ${esc(GRUPOS_PT[g])}`;
        return `<li><span class="sw" style="background:${cores[g]}" aria-hidden="true"></span><span class="onde"><span class="preco">${dolares(c.preco)}</span> · ${esc(c.bairro ?? "")}${tipo}</span><span class="dist">≈ ${metros(c.d)}</span></li>`;
      }).join("");
      blocos.push(`<div class="res-bloco"><p class="res-rotulo">Anúncios de 2026 mais próximos (${esc(tipoTxt)})</p>
        <ol class="comparaveis">${itens}</ol>
        <p class="res-sub" style="margin-top:6px">Preço anunciado por noite; distância a partir do ponto escolhido (a posição de cada anúncio é aproximada, ±150 m).</p></div>`);
    } else {
      blocos.push(`<div class="res-bloco"><p class="res-sub">Nenhum anúncio de 2026 desse tipo, com preço, num raio de ${metros(RAIO_COMPARAVEIS_M)}.</p></div>`);
    }

    blocos.push(htmlComo(r, montado));
    detalhesEl.innerHTML = blocos.join("");
  }

  function htmlComo(r, { x, origem }) {
    const mpRes = resumo.modelo_preco ?? {};
    const linhas = mp.features.map((f) => `<tr><td>${esc(rotuloFeature(f))}</td><td class="num">${esc(valorLegivel(f, x[f]))}</td><td>${origem[f]}</td></tr>`).join("");
    const metr = [];
    if (typeof mpRes.mae_usd === "number") metr.push(`erro absoluto médio de ${dolares(mpRes.mae_usd)}`);
    if (typeof mpRes.mdape === "number") metr.push(`erro percentual mediano de ${pct(emPontos(mpRes.mdape))}`);
    if (typeof mpRes.cobertura_80 === "number") metr.push(`a faixa de 80% acertou ${pct(emPontos(mpRes.cobertura_80))} dos casos`);
    const grupo = r.grupo !== null && mp.intervalo_por_grupo
      ? " Para este tipo de acomodação, a faixa usa uma calibração própria: a faixa única da cidade ficava estreita demais para alguns tipos."
      : "";
    return `<details class="como"><summary>Como chegamos nesse número?</summary><div class="como-corpo">
      <p>Um modelo de <b>${numero(mp.n_arvores, 0)} árvores de decisão</b> (LightGBM) estima o preço a partir das características que você informou e das características da área — o hexágono de ~0,1 km² onde fica o ponto. Não usamos o ponto exato: o Airbnb desloca a posição publicada de cada anúncio.</p>
      <p>O número grande é o valor típico (a mediana) para um imóvel assim, ali. A faixa diz onde cai o preço de 8 em cada 10 imóveis parecidos.${grupo}</p>
      ${metr.length ? `<p>Nos testes com regiões que o modelo não viu no treino: ${metr.join("; ")}.</p>` : ""}
      <p>O efeito da localização compara a previsão aqui com a previsão para o <b>mesmo</b> imóvel numa área de referência da cidade, mudando só o lugar.</p>
      <p class="res-sub">Célula H3 usada: <code>${esc(estado.celula)}</code>${ref ? ` · referência: <code>${esc(ref)}</code>` : ""}.</p>
      <table><thead><tr><th>O que o modelo recebeu</th><th class="num">Valor</th><th>De onde</th></tr></thead><tbody>${linhas}</tbody></table>
      <p class="res-sub">A conta roda no seu navegador com o mesmo modelo validado em Python; um teste automático confere que os números são idênticos.</p>
    </div></details>`;
  }

  /* ---- cálculo --------------------------------------------------------------- */
  function calcular() {
    if (!estado.celula) { vazio("Escolha um ponto no mapa para ver a estimativa."); return; }
    if (!r9.celulas[estado.celula]) {
      vazio("Não temos dados para este ponto: ele pode estar na água, num parque, num aeroporto, fora dos cinco distritos ou numa área sem anúncios suficientes. Tente um ponto próximo.");
      return;
    }
    const { valores, erros } = lerFormulario();
    if (erros.length) {
      el.resultado.dataset.estado = "vazio";
      resumoEl.innerHTML = `<p class="erro-carga">Ajuste ${erros.length === 1 ? "o campo destacado" : "os campos destacados"}: ${erros.map((e) => esc(e.rotulo)).join(", ")}.</p>`;
      detalhesEl.innerHTML = "";
      return;
    }
    const montado = montar(mp, estado.celula, valores);
    const r = preverComIntervalo(mp, montado.x);
    let premio = null;
    let valorRef = null;
    if (ref) {
      valorRef = prever(mp, montar(mp, ref, valores).x);
      premio = valorRef > 0 ? r.valor / valorRef - 1 : null;
    }
    const ocup = mo ? preverComIntervalo(mo, montar(mo, estado.celula, valores).x) : null;
    render({ r, premio, valorRef, ocup, ctx: contexto2019(estado.celula), comps: comparaveis(estado.ponto, valores), montado });
  }

  let relogio = null;
  const agendar = () => { clearTimeout(relogio); relogio = setTimeout(calcular, 120); };
  campos.addEventListener("input", agendar);
  campos.addEventListener("change", agendar);

  /* ---- ponto escolhido ------------------------------------------------------- */
  function escolherPonto({ lat, lon, origem, rotulo }) {
    estado.ponto = { lat, lon };
    estado.celula = latLngToCell(lat, lon, RES_FEATURES);
    estado.rotulo = rotulo ?? null;
    const coberta = Boolean(r9.celulas[estado.celula]);
    const area = nomeArea(estado.celula);
    const de = { mapa: "clique no mapa", busca: "busca", anuncio: "anúncio no mapa", centro: "centro do mapa" }[origem] ?? origem;
    el.ponto.innerHTML = `<b>Ponto escolhido</b> <span class="res-sub">(${esc(de)})</span><br>${rotulo ? `${esc(rotulo)}<br>` : ""}${area ? `Área: ${esc(area)}` : coberta ? "" : "Fora da área coberta pelos dados"}`;
    mapaApi?.marcar({ lat, lon }, coberta ? estado.celula : null, coberta ? ref : null);
    if (origem !== "mapa") mapaApi?.voarPara(lat, lon);
    calcular();
    // no celular, abre a folha e leva ao resultado
    if (matchMedia("(max-width: 880px)").matches) {
      el.painel.dataset.estado = "aberto";
      el.alca.setAttribute("aria-expanded", "true");
      el.alca.querySelector("span").textContent = "Recolher";
    }
    el.resultado.scrollIntoView({ block: "nearest", behavior: reduzirMovimento() ? "auto" : "smooth" });
  }

  /* ---- busca de endereço (Nominatim: só ao enviar, no máximo 1 por segundo) --- */
  const cache = new Map();
  let ultima = 0;
  async function buscar(q) {
    const termo = q.trim();
    el.resultadosBusca.innerHTML = "";
    if (termo.length < 3) { el.statusBusca.textContent = "Digite pelo menos 3 letras."; return; }
    el.botaoBusca.disabled = true;
    el.statusBusca.textContent = "Buscando…";
    try {
      let achados = cache.get(termo);
      if (!achados) {
        const espera = 1000 - (Date.now() - ultima);
        if (espera > 0) await new Promise((r) => setTimeout(r, espera));
        ultima = Date.now();
        const url = new URL(NOMINATIM);
        url.search = new URLSearchParams({
          q: termo, format: "jsonv2", limit: "5", viewbox: VIEWBOX_NYC, bounded: "1",
          countrycodes: "us", "accept-language": "pt-BR,pt,en",
        }).toString();
        const resp = await fetch(url, { headers: { Accept: "application/json" } });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        achados = (await resp.json()).map((a) => ({ lat: Number(a.lat), lon: Number(a.lon), nome: a.display_name }));
        cache.set(termo, achados);
      }
      if (!achados.length) { el.statusBusca.textContent = `Nada encontrado em Nova York para “${termo}”.`; return; }
      if (achados.length === 1) {
        el.statusBusca.textContent = "1 endereço encontrado.";
        escolherPonto({ ...achados[0], origem: "busca", rotulo: achados[0].nome });
        return;
      }
      el.statusBusca.textContent = `${achados.length} endereços encontrados — escolha um:`;
      el.resultadosBusca.innerHTML = achados.map((a, i) => `<li><button type="button" data-i="${i}">${esc(a.nome)}</button></li>`).join("");
      el.resultadosBusca.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        const a = achados[Number(b.dataset.i)];
        el.resultadosBusca.innerHTML = "";
        el.statusBusca.textContent = "";
        escolherPonto({ ...a, origem: "busca", rotulo: a.nome });
      }));
    } catch {
      el.statusBusca.textContent = "A busca de endereços não respondeu agora. Tente de novo em instantes ou clique no mapa.";
    } finally {
      el.botaoBusca.disabled = false;
    }
  }
  el.formBusca.addEventListener("submit", (ev) => {
    ev.preventDefault();
    buscar(el.busca.value);
  });

  renderizarCampos();
  if (problemas.length) {
    vazio(`<span class="erro-carga">Os dados do simulador estão inconsistentes (${esc(problemas.join("; "))}).</span>`);
  }

  return {
    escolherPonto,
    definirMapa(api) { mapaApi = api; if (estado.ponto) api.marcar(estado.ponto, r9.celulas[estado.celula] ? estado.celula : null, ref); },
    definirTema(novo) { tema = novo; if (estado.celula) calcular(); },
  };
}
