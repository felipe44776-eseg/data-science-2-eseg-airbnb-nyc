# ADR 0004 — O modelo roda no navegador, com paridade Python ↔ JavaScript

**Status:** aceito · **Data:** 2026-09-18

## Contexto
O "teste de localização" precisa responder a qualquer ponto e a qualquer combinação
de características. Pré-computar todas as combinações é inviável; um backend
contradiz o ADR 0003.

## Decisão
- O modelo de preço do produto é um LightGBM exportado de `Booster.dump_model()`
  para um JSON compacto (`site/data/modelo_preco.json`) e avaliado por um avaliador
  JavaScript próprio (`site/assets/modelo.js`) que reproduz a semântica do LightGBM:
  comparação `<=`, tratamento de ausente (`None`, `Zero`, `NaN`), divisões categóricas.
- `tests/paridade_js.mjs` importa **o mesmo arquivo** que a página usa e compara com
  as previsões do próprio LightGBM em casos gerados pelo Python, incluindo ausentes.
  Tolerância 1e-9 no escore bruto. Roda em `.\tasks.ps1 site` e no CI.
- O modelo do produto é **compacto** (poucas centenas de árvores) para caber no
  navegador; o custo em erro frente ao modelo completo é medido e publicado.

## Alternativas descartadas
- **ONNX + onnxruntime-web**: vários MB de WebAssembly para avaliar árvores.
- **Grade pré-computada**: não responde a combinações fora da grade.
- **Backend (Cloud Run)**: custo e manutenção; contradiz o ADR 0003.

## Consequências
- O número que o site mostra é o número do modelo validado — e o CI prova isso.
- Qualquer pessoa pode auditar o modelo baixando um JSON.
