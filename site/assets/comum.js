/* Utilitários compartilhados, sem dependência: o simulador não pode depender da
 * MapLibre — se o mapa falhar (sem WebGL 2), o teste segue pela busca. */

export const TIPOS_PT = {
  "Entire home/apt": "Casa ou apartamento inteiro",
  "Private room": "Quarto privativo",
  "Shared room": "Quarto compartilhado",
  "Hotel room": "Quarto de hotel",
};

/** Grupos de cor dos anúncios: mais de 3 cores num mapa confunde (validação de daltonismo). */
export const GRUPOS_PT = ["Casa ou apê inteiro", "Quarto privativo", "Outros (compartilhado ou hotel)"];

export function grupoDoTipo(nome) {
  if (nome === "Entire home/apt") return 0;
  if (nome === "Private room") return 1;
  return 2;
}

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const reduzirMovimento = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Fração (0–1) ou pontos percentuais: aceita os dois, devolve pontos. */
export const emPontos = (v) => (typeof v === "number" && Math.abs(v) <= 1.5 ? v * 100 : v);
