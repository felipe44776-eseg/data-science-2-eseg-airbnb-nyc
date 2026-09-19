/* Mapa: MapLibre GL JS (vendorizada) + hexágonos H3 gerados no navegador.
 *
 * Camadas (de baixo para cima): mapa-base OpenFreeMap · hexágonos r8 coloridos
 * pela medida escolhida · contorno dos bairros · [rótulos do mapa-base] ·
 * célula escolhida e célula de referência · anúncios de 2026 · metrô · ponto.
 *
 * Se o mapa-base não carregar, o mapa segue com fundo liso: as camadas do
 * projeto são dados locais (site/data), não dependem de servidor de tiles.
 */
import * as maplibregl from "../vendor/maplibre-gl-6.10.0/maplibre-gl.mjs";
import { cellToBoundary } from "../vendor/h3-js-4.5.0/h3-js.es.js";
import { TIPOS_PT, esc, grupoDoTipo, reduzirMovimento } from "./comum.js";
import { PALETAS, dolares, escalaDaMetrica, formatarMetrica, pct } from "./escalas.js";

const ESTILOS = {
  claro: "https://tiles.openfreemap.org/styles/positron",
  escuro: "https://tiles.openfreemap.org/styles/dark",
};
const LOCALE = {
  "Map.Title": "Mapa de Nova York. Setas movem o mapa; + e − mudam o zoom.",
  "NavigationControl.ZoomIn": "Aproximar",
  "NavigationControl.ZoomOut": "Afastar",
  "NavigationControl.ResetBearing": "Voltar o norte para cima",
  "AttributionControl.ToggleAttribution": "Mostrar créditos do mapa",
  "Popup.Close": "Fechar",
};
const CENTRO_NYC = [-73.94, 40.71];
const LIMITES_NYC = [[-74.5, 40.38], [-73.5, 41.02]];
const TRANSPARENTE = "rgba(0, 0, 0, 0)";

async function buscarEstilo(tema, espera = 8000) {
  const ctrl = new AbortController();
  const relogio = setTimeout(() => ctrl.abort(), espera);
  try {
    const r = await fetch(ESTILOS[tema], { signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const estilo = await r.json();
    // escudos de rodovia: poluem um mapa de preço e usam expressões legadas que a
    // style-spec 25 (MapLibre 6) sinaliza no console a cada carga
    estilo.layers = estilo.layers.filter((l) => !/shield/i.test(l.id));
    return { estilo, base: true };
  } catch {
    // fundo liso: sem tiles, sem glifos (nenhuma camada nossa usa texto)
    return {
      estilo: { version: 8, sources: {}, layers: [{ id: "fundo", type: "background", paint: { "background-color": PALETAS[tema].fundo } }] },
      base: false,
    };
  } finally {
    clearTimeout(relogio);
  }
}

const vazio = () => ({ type: "FeatureCollection", features: [] });

function geojsonHex(r8) {
  const iH3 = r8.colunas.indexOf("h3");
  return {
    type: "FeatureCollection",
    features: r8.linhas.map((linha) => {
      const props = {};
      // null fica de fora: ["get", k] devolve null do mesmo jeito
      r8.colunas.forEach((c, i) => { if (linha[i] !== null && linha[i] !== undefined) props[c] = linha[i]; });
      return { type: "Feature", properties: props, geometry: { type: "Polygon", coordinates: [cellToBoundary(linha[iH3], true)] } };
    }),
  };
}

function geojsonAnuncios(an) {
  const c = Object.fromEntries(an.colunas.map((n, i) => [n, i]));
  return {
    type: "FeatureCollection",
    features: an.linhas.map((l) => {
      const props = { g: grupoDoTipo(an.tipos[l[c.tipo]]), t: l[c.tipo] };
      if (l[c.preco] !== null && l[c.preco] !== undefined) props.p = l[c.preco];
      if (l[c.previsto] !== null && l[c.previsto] !== undefined) props.v = l[c.previsto];
      if (l[c.bairro]) props.b = l[c.bairro];
      return { type: "Feature", properties: props, geometry: { type: "Point", coordinates: [l[c.lon], l[c.lat]] } };
    }),
  };
}

export function poligonoCelula(h, props = {}) {
  return { type: "Feature", properties: props, geometry: { type: "Polygon", coordinates: [cellToBoundary(h, true)] } };
}

/**
 * Cria o mapa. `dados` = {r8, bairros, metro, anuncios, metricas}. Callbacks:
 * aoEscolherPonto({lat, lon, origem}), aoAvisar(texto), aoFalhar(erro).
 */
export async function criarMapa({ container, dados, tema, aoEscolherPonto, aoAvisar, aoFalhar }) {
  const fontes = {
    hex: geojsonHex(dados.r8),
    bairros: dados.bairros,
    metro: dados.metro,
    anuncios: geojsonAnuncios(dados.anuncios),
  };
  const colunaR8 = (chave) => {
    const i = dados.r8.colunas.indexOf(chave);
    return i < 0 ? [] : dados.r8.linhas.map((l) => l[i]);
  };

  const estado = {
    tema,
    metrica: dados.metricas[0] ?? null,
    escala: null,
    camadas: { hex: true, bairros: true, anuncios: false, metro: false },
    selecao: vazio(),
    ponto: vazio(),
    hover: null,
  };

  const { estilo, base } = await buscarEstilo(tema);
  if (!base) aoAvisar?.("O mapa-base (ruas e nomes) não carregou agora. As camadas do projeto continuam visíveis e o teste funciona normalmente.");

  let mapa;
  try {
    mapa = new maplibregl.Map({
      container,
      style: estilo,
      center: CENTRO_NYC,
      zoom: 10.2,
      minZoom: 9,
      maxZoom: 17,
      maxBounds: LIMITES_NYC,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      renderWorldCopies: false,
      locale: LOCALE,
    });
  } catch (erro) {
    aoFalhar?.(erro);
    return null;
  }
  mapa.addControl(new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }), "top-right");
  // a atribuição (OpenFreeMap © OpenMapTiles, dados © OpenStreetMap) vem do TileJSON do
  // próprio mapa-base; repeti-la aqui duplicava o texto
  mapa.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
  // o estilo do OpenFreeMap cita imagens que o sprite não tem ("wood-pattern"):
  // sem isto, a MapLibre avisa no console a cada carga. Imagem transparente 1x1.
  mapa.setMissingStyleImageResolver?.((id) => {
    if (!mapa.hasImage(id)) mapa.addImage(id, { width: 1, height: 1, data: new Uint8Array(4) });
  });
  mapa.touchZoomRotate?.disableRotation?.();
  mapa.keyboard?.disableRotation?.();

  // sem ouvinte, a MapLibre joga todo erro no console; aqui: um aviso só, e segue
  let avisouTiles = false;
  mapa.on("error", (ev) => {
    const msg = String(ev?.error?.message ?? ev?.error ?? "");
    if (/webgl/i.test(msg)) { aoFalhar?.(ev.error); return; }
    if (!avisouTiles) {
      avisouTiles = true;
      aoAvisar?.("Parte do mapa-base não carregou (conexão com o servidor de mapas). As camadas do projeto seguem visíveis.");
      console.warn("[mapa]", msg);
    }
  });

  const pal = () => PALETAS[estado.tema] ?? PALETAS.claro;
  const existe = (id) => Boolean(mapa.getLayer(id));
  const opacidadeHex = () => (estado.camadas.anuncios ? 0.35 : 0.72);

  function aplicarMetrica() {
    if (!estado.metrica) return;
    estado.escala = escalaDaMetrica(estado.metrica, colunaR8(estado.metrica.chave), estado.tema);
    if (!existe("hex-fill")) return;
    mapa.setPaintProperty("hex-fill", "fill-color", estado.escala.expressao);
    mapa.setFilter("hex-nulo", ["==", ["get", estado.metrica.chave], null]);
  }

  function aplicarCamadas() {
    const vis = (v) => (v ? "visible" : "none");
    const grupos = {
      hex: ["hex-fill", "hex-nulo", "hex-borda", "hex-hover"],
      bairros: ["bairros-linha"],
      anuncios: ["anuncios-pontos"],
      metro: ["metro-pontos"],
    };
    for (const [nome, ids] of Object.entries(grupos)) {
      for (const id of ids) if (existe(id)) mapa.setLayoutProperty(id, "visibility", vis(estado.camadas[nome]));
    }
    if (existe("hex-fill")) mapa.setPaintProperty("hex-fill", "fill-opacity", opacidadeHex());
  }

  function adicionarCamadas() {
    const p = pal();
    const antesDosRotulos = mapa.getStyle().layers.find((l) => l.type === "symbol")?.id;
    const add = (camada, antes) => { if (!existe(camada.id)) mapa.addLayer(camada, antes); };
    const fonte = (id, def) => { if (!mapa.getSource(id)) mapa.addSource(id, def); };

    fonte("hex", { type: "geojson", data: fontes.hex, promoteId: "h3" });
    fonte("bairros", { type: "geojson", data: fontes.bairros });
    fonte("selecao", { type: "geojson", data: estado.selecao });
    fonte("anuncios", { type: "geojson", data: fontes.anuncios });
    fonte("metro", { type: "geojson", data: fontes.metro });
    fonte("ponto", { type: "geojson", data: estado.ponto });

    add({ id: "hex-fill", type: "fill", source: "hex", paint: { "fill-color": TRANSPARENTE, "fill-opacity": opacidadeHex() } }, antesDosRotulos);
    // separação fina entre hexágonos, na cor da superfície
    add({ id: "hex-borda", type: "line", source: "hex", paint: { "line-color": p.superficie, "line-width": 0.5, "line-opacity": 0.6 } }, antesDosRotulos);
    add({ id: "hex-nulo", type: "line", source: "hex", filter: ["==", ["get", "h3"], "__nenhum__"],
      paint: { "line-color": p.contorno, "line-width": 0.8, "line-dasharray": [2, 2], "line-opacity": 0.7 } }, antesDosRotulos);
    add({ id: "hex-hover", type: "line", source: "hex",
      paint: { "line-color": p.tinta, "line-width": ["case", ["boolean", ["feature-state", "hover"], false], 2.2, 0] } }, antesDosRotulos);
    add({ id: "bairros-linha", type: "line", source: "bairros",
      paint: { "line-color": p.contorno, "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.4, 13, 1.1, 16, 1.8] } }, antesDosRotulos);

    add({ id: "selecao-fill", type: "fill", source: "selecao", filter: ["==", ["get", "papel"], "escolhida"],
      paint: { "fill-color": p.tinta, "fill-opacity": 0.14 } });
    add({ id: "referencia-linha", type: "line", source: "selecao", filter: ["==", ["get", "papel"], "referencia"],
      paint: { "line-color": p.tinta, "line-width": 1.6, "line-dasharray": [1.5, 1.5] } });
    add({ id: "selecao-linha", type: "line", source: "selecao", filter: ["==", ["get", "papel"], "escolhida"],
      paint: { "line-color": p.tinta, "line-width": 2.6 } });
    add({ id: "anuncios-pontos", type: "circle", source: "anuncios", layout: { visibility: "none" },
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 1.3, 12, 2.6, 15, 5, 17, 7],
        "circle-color": ["match", ["get", "g"], 0, p.tipos[0], 1, p.tipos[1], p.tipos[2]],
        "circle-stroke-color": p.superficie,
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 9, 0, 12, 0.5, 15, 1.2],
      } });
    add({ id: "metro-pontos", type: "circle", source: "metro", layout: { visibility: "none" },
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 1.4, 12, 2.6, 14, 4.5, 16, 6.5],
        "circle-color": p.superficie, "circle-stroke-color": p.tinta,
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 9, 0.8, 13, 1.4, 16, 2],
      } });
    add({ id: "ponto-halo", type: "circle", source: "ponto",
      paint: { "circle-radius": 10, "circle-color": p.superficie, "circle-opacity": 0.9, "circle-stroke-color": p.tinta, "circle-stroke-width": 2.5 } });
    add({ id: "ponto-centro", type: "circle", source: "ponto", paint: { "circle-radius": 3.5, "circle-color": p.tinta } });

    aplicarMetrica();
    aplicarCamadas();
  }

  let resolverPronto;
  const pronto = new Promise((r) => { resolverPronto = r; });
  mapa.on("style.load", () => {
    adicionarCamadas();
    resolverPronto();
  });

  /* ---- dica ao passar o mouse sobre um hexágono --------------------------- */
  const dica = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: "300px", offset: 14, className: "dica" });
  const nomeDistrito = (d) => esc(d ?? "");
  const corDistrito = (d) => ({
    Manhattan: "var(--manhattan)", Brooklyn: "var(--brooklyn)", Queens: "var(--queens)",
    Bronx: "var(--bronx)", "Staten Island": "var(--staten)",
  }[d] ?? "var(--ink-faint)");

  function htmlDica(props) {
    const m = estado.metrica;
    const v = props[m.chave];
    const valor = v === undefined || v === null
      ? `<span class="sub">sem dado: ${esc(m.nulo ?? "esta medida não está disponível para esta área")}</span>`
      : `${esc(m.rotulo)}: <b>${esc(formatarMetrica(m, v))}</b>`;
    return `<div><b>${esc(props.bairro ?? "Área sem nome")}</b> <span class="sub"><span class="distrito-sw" style="background:${corDistrito(props.distrito)}"></span>${nomeDistrito(props.distrito)}</span></div><div>${valor}</div>`;
  }

  if (matchMedia("(hover: hover)").matches) {
    mapa.on("mousemove", "hex-fill", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      if (estado.hover !== f.id) {
        if (estado.hover !== null) mapa.setFeatureState({ source: "hex", id: estado.hover }, { hover: false });
        estado.hover = f.id;
        mapa.setFeatureState({ source: "hex", id: f.id }, { hover: true });
      }
      dica.setLngLat(e.lngLat).setHTML(htmlDica(f.properties)).addTo(mapa);
    });
    mapa.on("mouseleave", "hex-fill", () => {
      if (estado.hover !== null) mapa.setFeatureState({ source: "hex", id: estado.hover }, { hover: false });
      estado.hover = null;
      dica.remove();
    });
  }

  /* ---- clique: anúncio/metrô abre ficha; o resto escolhe o ponto ----------- */
  const ficha = new maplibregl.Popup({ maxWidth: "300px", offset: 10, className: "ficha" });
  const tipoNome = (t) => dados.anuncios.tipos[t];

  function abrirFichaAnuncio(f) {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    const tipo = TIPOS_PT[tipoNome(p.t)] ?? tipoNome(p.t) ?? "Tipo não informado";
    let comparacao = "";
    if (typeof p.p === "number" && typeof p.v === "number" && p.v > 0) {
      const d = (p.p / p.v - 1) * 100;
      const txt = Math.abs(d) < 2 ? "em linha com o previsto" : `${pct(Math.abs(d))} ${d > 0 ? "acima" : "abaixo"} do previsto`;
      comparacao = `<p>Previsto pelo modelo: <b>${dolares(p.v)}</b> — ${txt}</p>`;
    } else if (typeof p.v === "number") {
      comparacao = `<p>Previsto pelo modelo: <b>${dolares(p.v)}</b></p>`;
    }
    const preco = typeof p.p === "number" ? `<b>${dolares(p.p)}</b> por noite (anunciado)` : "<b>Preço não informado</b>";
    ficha.setLngLat([lon, lat]).setHTML(
      `<div class="pop"><p>${preco}</p><p class="sub">${esc(tipo)}${p.b ? ` · ${esc(p.b)}` : ""}</p>${comparacao}` +
      `<button class="botao botao-sec" type="button" data-acao="testar">Testar esta localização</button></div>`).addTo(mapa);
    ficha.getElement()?.querySelector("[data-acao=testar]")?.addEventListener("click", () => {
      ficha.remove();
      aoEscolherPonto({ lat, lon, origem: "anuncio" });
    });
  }

  function abrirFichaMetro(f) {
    const p = f.properties;
    let linhas = p.linhas;
    if (typeof linhas === "string" && linhas.startsWith("[")) {
      try { linhas = JSON.parse(linhas); } catch { /* texto simples */ }
    }
    const txtLinhas = Array.isArray(linhas) ? linhas.join(" · ") : (linhas ?? "");
    ficha.setLngLat(f.geometry.coordinates).setHTML(
      `<div class="pop"><p><b>${esc(p.nome ?? "Estação")}</b></p>${txtLinhas ? `<p class="sub">Linhas: ${esc(txtLinhas)}</p>` : ""}</div>`).addTo(mapa);
  }

  mapa.on("click", (e) => {
    const tol = 6;
    const caixa = [[e.point.x - tol, e.point.y - tol], [e.point.x + tol, e.point.y + tol]];
    const camadas = ["metro-pontos", "anuncios-pontos"].filter((id) => existe(id) && mapa.getLayoutProperty(id, "visibility") !== "none");
    const achados = camadas.length ? mapa.queryRenderedFeatures(caixa, { layers: camadas }) : [];
    if (achados.length) {
      const f = achados[0];
      if (f.layer.id === "metro-pontos") abrirFichaMetro(f);
      else abrirFichaAnuncio(f);
      return;
    }
    aoEscolherPonto({ lat: e.lngLat.lat, lon: e.lngLat.lng, origem: "mapa" });
  });
  for (const id of ["anuncios-pontos", "metro-pontos"]) {
    mapa.on("mouseenter", id, () => { mapa.getCanvas().style.cursor = "pointer"; });
    mapa.on("mouseleave", id, () => { mapa.getCanvas().style.cursor = ""; });
  }

  /* ---- API usada pelo app --------------------------------------------------- */
  return {
    mapa,
    pronto,
    escala: () => estado.escala,
    definirMetrica(metrica) {
      estado.metrica = metrica;
      aplicarMetrica();
      return estado.escala;
    },
    alternar(camada, visivel) {
      estado.camadas[camada] = visivel;
      aplicarCamadas();
    },
    marcar({ lat, lon }, celula, referencia) {
      estado.ponto = { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [lon, lat] } }] };
      const feats = [];
      if (celula) feats.push(poligonoCelula(celula, { papel: "escolhida" }));
      if (referencia) feats.push(poligonoCelula(referencia, { papel: "referencia" }));
      estado.selecao = { type: "FeatureCollection", features: feats };
      mapa.getSource("ponto")?.setData(estado.ponto);
      mapa.getSource("selecao")?.setData(estado.selecao);
    },
    voarPara(lat, lon, zoomMin = 13) {
      const alvo = { center: [lon, lat], zoom: Math.max(mapa.getZoom(), zoomMin) };
      if (reduzirMovimento()) mapa.jumpTo(alvo);
      else mapa.flyTo({ ...alvo, speed: 1.6, essential: false });
    },
    centro() {
      const c = mapa.getCenter();
      return { lat: c.lat, lon: c.lng };
    },
    async definirTema(novo) {
      if (novo === estado.tema) return;
      estado.tema = novo;
      estado.hover = null;
      dica.remove();
      const r = await buscarEstilo(novo);
      if (!r.base) aoAvisar?.("O mapa-base (ruas e nomes) não carregou agora. As camadas do projeto continuam visíveis.");
      mapa.setStyle(r.estilo, { diff: false }); // style.load recoloca as camadas no tema novo
    },
  };
}
