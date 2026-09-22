// Geometria dos decks (site/apresentacao, site/executiva, site/executiva-maior).
//
// A escala do slide e fixa (1280x720) e o texto e escrito no HTML: uma frase mais
// longa ou uma letra maior quebra o layout sem que nenhum teste Python perceba.
// Este verificador abre o deck no Chrome e acusa, slide a slide:
//   - conteudo que sai da caixa do slide;
//   - conteudo que invade o rodape (folga minima de 6 px);
//   - elemento cujo conteudo transborda a propria caixa;
//   - numero, pilula, rotulo de grafico ou URL que quebrou linha;
//   - texto sobre texto (retangulos de nos de texto que se cruzam).
// Tambem lista erro de console e requisicao que falhou (imagem, fonte, JSON).
//
// Nao roda no CI (precisa de Chrome). Uso, da raiz do repositorio:
//   npm install --no-save puppeteer-core
//   .	asks.ps1 servir                      # ou qualquer servidor estatico em site/
//   node tests/geometria_decks.mjs http://localhost:8000/executiva-maior/ [pasta-capturas]
// Com a pasta, grava uma captura por slide. Sai com codigo 1 se algum slide tiver problema.
// CHROME=<caminho> troca o executavel (padrao: Chrome do Windows).
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";

const [url, saida] = process.argv.slice(2);
if (!url) { console.error("uso: node tests/geometria_decks.mjs <url> [pasta-capturas]"); process.exit(2); }
if (saida) fs.mkdirSync(saida, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: "new", args: ["--no-sandbox", "--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 });
const logs = [];
page.on("console", (m) => { if (m.type() !== "log") logs.push(`[${m.type()}] ${m.text()}`); });
page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));
page.on("requestfailed", (r) => logs.push(`[requestfailed] ${r.url()}`));
page.on("response", (r) => { if (r.status() >= 400) logs.push(`[${r.status()}] ${r.url()}`); });
await page.goto(url, { waitUntil: "networkidle0" });
await page.evaluate(() => document.fonts.ready);
await new Promise((r) => setTimeout(r, 500));

const res = await page.evaluate(() => {
  const txt = (el) => (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 44);
  return [...document.querySelectorAll(".slide")].map((s, i) => {
    const R = s.getBoundingClientRect();
    const k = R.width / s.offsetWidth;
    const probs = [];
    // 1. fora da caixa do slide
    if (s.scrollHeight > s.clientHeight + 1 || s.scrollWidth > s.clientWidth + 1)
      probs.push(`slide rola: ${s.scrollWidth}x${s.scrollHeight}`);
    for (const el of s.querySelectorAll("*")) {
      const e = el.getBoundingClientRect();
      if (!e.width || !e.height) continue;
      if (e.right > R.right + 2 || e.bottom > R.bottom + 2 || e.left < R.left - 2 || e.top < R.top - 2)
        probs.push(`fora do slide <${el.tagName.toLowerCase()} .${el.className}> "${txt(el)}"`);
    }
    // 2. invade o rodape
    const foot = s.querySelector(".foot");
    if (foot) {
      const ft = foot.getBoundingClientRect().top;
      for (const el of s.querySelectorAll("*")) {
        if (foot.contains(el) || el.classList.contains("corpo")) continue;
        const e = el.getBoundingClientRect();
        if (!e.width || !e.height) continue;
        if (e.bottom > ft - 6 * k)
          probs.push(`invade o rodape em ${Math.round((e.bottom - ft) / k + 6)}px <${el.tagName.toLowerCase()} .${el.className}> "${txt(el)}"`);
      }
    }
    // 3. conteudo maior que a propria caixa (texto vazando de cartao, pilula, link)
    for (const el of s.querySelectorAll("*")) {
      if (!el.clientWidth || el.classList.contains("slide")) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "inline") continue;
      if (el.scrollWidth > el.clientWidth + 1 && txt(el))
        probs.push(`transborda na largura ${el.scrollWidth - el.clientWidth}px <${el.tagName.toLowerCase()} .${el.className}> "${txt(el)}"`);
      if (el.scrollHeight > el.clientHeight + 1 && cs.overflow !== "visible" && txt(el))
        probs.push(`transborda na altura ${el.scrollHeight - el.clientHeight}px <${el.tagName.toLowerCase()} .${el.className}> "${txt(el)}"`);
    }
    // 5. o que nao pode quebrar linha: numeros, pilulas, rotulos de grafico, URLs
    for (const el of s.querySelectorAll("span.num,div.num,td.num,.num-xl,.num-lg,.num-md,.v,.chip,.no,.bar-v,.db-v,.row-extra,.link span,.mono,.tl-data")) {
      const r = document.createRange(); r.selectNodeContents(el);
      // linhas = faixas verticais que nao se sobrepoem (texto menor na mesma linha tem outro topo)
      const qs = [...r.getClientRects()].filter((q) => q.width > 1).sort((a, b) => a.top - b.top);
      let linhas = 0, fundo = -1e9;
      for (const q of qs) { if (q.top >= fundo - 1) { linhas++; fundo = q.bottom; } else fundo = Math.max(fundo, q.bottom); }
      if (linhas > 1 && !el.querySelector("br")) probs.push(`quebrou em ${linhas} linhas <${el.tagName.toLowerCase()} .${el.className}> "${txt(el)}"`);
    }
    // 4. texto sobre texto: retangulos de cada no de texto, de elementos diferentes
    const caixas = [];
    const w = document.createTreeWalker(s, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      if (!n.textContent.trim()) continue;
      const r = document.createRange(); r.selectNodeContents(n);
      for (const q of r.getClientRects()) if (q.width > 1 && q.height > 1) caixas.push({ el: n.parentElement, q, t: n.textContent.trim().slice(0, 24) });
    }
    for (let a = 0; a < caixas.length; a++) for (let b = a + 1; b < caixas.length; b++) {
      const A = caixas[a], B = caixas[b];
      if (A.el === B.el) continue;
      const ix = Math.min(A.q.right, B.q.right) - Math.max(A.q.left, B.q.left);
      const iy = Math.min(A.q.bottom, B.q.bottom) - Math.max(A.q.top, B.q.top);
      if (ix > 2 * k && iy > 3 * k) probs.push(`texto colide: "${A.t}" x "${B.t}" (${Math.round(ix / k)}x${Math.round(iy / k)}px)`);
    }
    const t = s.querySelector(".h1,.titulo");
    return { n: i + 1, titulo: t ? txt(t) : "", probs: [...new Set(probs)] };
  });
});

if (saida) {
  for (let i = 0; i < res.length; i++) {
    await page.evaluate((i) => document.querySelectorAll(".frame")[i].scrollIntoView({ block: "start" }), i);
    await new Promise((r) => setTimeout(r, 200));
    await page.screenshot({ path: path.join(saida, `slide-${String(i + 1).padStart(2, "0")}.png`) });
  }
}
if (saida) fs.writeFileSync(path.join(saida, "checagem.json"), JSON.stringify({ res, logs }, null, 1));
const ruins = res.filter((r) => r.probs.length);
console.log(`${res.length} slides · com problema: ${ruins.map((r) => r.n).join(", ") || "nenhum"}`);
for (const r of ruins) {
  console.log(`#${r.n} "${r.titulo}"`);
  for (const p of r.probs.slice(0, 12)) console.log(`   ${p}`);
  if (r.probs.length > 12) console.log(`   ... +${r.probs.length - 12}`);
}
if (logs.length) console.log("console/rede:\n  " + logs.slice(0, 10).join("\n  "));
await browser.close();
process.exit(ruins.length ? 1 : 0);
