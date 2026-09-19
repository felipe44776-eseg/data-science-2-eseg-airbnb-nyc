# ADR 0005 — 2019 × 2026: dólar constante e estratificação pela Local Law 18

**Status:** aceito · **Data:** 2026-09-18

## Contexto
Dois problemas tornam ingênua a comparação direta de preços entre os snapshots:

1. **Inflação.** Sete anos separam julho de 2019 e junho de 2026. Um dólar de 2019
   não é um dólar de 2026.
2. **Mudança de significado.** Depois da Local Law 18 (fiscalizada desde 2023-09-05),
   a maioria dos anúncios exige mínimo de 30 noites, e o `price` passou a ser a cotação
   por noite de uma estadia longa, com desconto mensal. A mediana de 2026 mistura um
   produto diferente.

## Decisão
- Todo preço de 2019 comparado com o atual é convertido para **dólar do mês do snapshot
  atual** pelo CPI-U New York-Newark-Jersey City (BLS `CUURS12ASA0`) — índice regional,
  não o nacional, porque o custo de vida de NYC não seguiu a média do país.
- Toda comparação de preço entre snapshots é **estratificada** por mínimo de noites
  (< 30 e ≥ 30) e por tipo de quarto. O número agregado só aparece acompanhado do
  estratificado.
- A variação de composição (quanto do mercado mudou de estrato) é reportada separada da
  variação de preço dentro do estrato.

## Consequências
- `preco_real` (dólar constante) é derivada documentada; `preco` é sempre o nominal.
- O KPI "preço mediano real" do site vem com a nota de composição.

**Gatilho que reabre:** se o BLS descontinuar a série regional, usar o CPI-U nacional
(`CUUR0000SA0`) e declarar a troca.
