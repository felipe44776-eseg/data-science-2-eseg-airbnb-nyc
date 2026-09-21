/* Nomes da equipe nas apresentacoes.
 *
 * A unica fonte dos nomes e src/airbnb/produto/autoria.py, publicada pelo pipeline
 * em site/data/resumo.json. As duas apresentacoes (completa e executiva) nao
 * escrevem nenhum nome: marcam o lugar e este script preenche. Preencher o RA que
 * falta no autoria.py e rodar .\tasks.ps1 site atualiza as duas de uma vez.
 *
 *   data-equipe-linha    um <span> por nome (as pilulas da capa)
 *   data-equipe-texto    os nomes em texto corrido, separados por virgula
 *   data-equipe-cartoes  um cartao por integrante: nome, RA e usuario do GitHub
 *
 * Sem o JSON, os lugares ficam vazios — nunca com nomes velhos.
 */
(function () {
  "use strict";
  var linhas = document.querySelectorAll("[data-equipe-linha]");
  var textos = document.querySelectorAll("[data-equipe-texto]");
  var grades = document.querySelectorAll("[data-equipe-cartoes]");
  if (!linhas.length && !textos.length && !grades.length) return;

  var esc = function (t) {
    return String(t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  var cada = function (lista, f) { Array.prototype.forEach.call(lista, f); };

  fetch("../data/resumo.json")
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      if (!d || !d.equipe || !d.equipe.length) return;
      var eq = d.equipe;
      cada(linhas, function (el) {
        el.innerHTML = eq.map(function (p) { return "<span>" + esc(p.nome) + "</span>"; }).join("");
      });
      cada(textos, function (el) {
        el.textContent = eq.map(function (p) { return p.nome; }).join(", ");
      });
      // as iniciais alternam as duas cores do deck; primeiro e ultimo nome
      var iniciais = function (nome) {
        var partes = String(nome).trim().split(/\s+/);
        return (partes[0][0] + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
      };
      var cores = ["var(--rausch)", "var(--babu)"];
      cada(grades, function (el) {
        el.innerHTML = eq.map(function (p, i) {
          return '<div class="card" style="padding:28px 24px 24px;min-height:200px;' +
              'display:flex;flex-direction:column;gap:4px">' +
            '<span aria-hidden="true" style="width:52px;height:52px;border-radius:50%;flex:none;' +
              "display:grid;place-items:center;color:#fff;font-weight:800;font-size:18px;" +
              "letter-spacing:.02em;background:" + cores[i % cores.length] + '">' +
              esc(iniciais(p.nome)) + "</span>" +
            '<div class="h3" style="margin-top:16px;font-size:19px;line-height:1.25">' +
              esc(p.nome) + "</div>" +
            (p.ra ? '<p class="caption" style="margin-top:6px">RA ' + esc(p.ra) + "</p>" : "") +
            (p.github ? '<p class="caption mono" style="margin-top:2px">@' + esc(p.github) + "</p>" : "") +
            "</div>";
        }).join("");
      });
    })
    .catch(function () { /* sem o JSON: lugares vazios */ });
})();
