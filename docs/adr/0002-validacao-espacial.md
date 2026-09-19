# ADR 0002 — Validação cruzada espacial por bloco H3 r6

**Status:** aceito · **Data:** 2026-09-18

## Contexto
Anúncios vizinhos compartilham tudo o que o modelo não vê: o prédio, a rua, o mesmo
anfitrião profissional com dezenas de unidades no quarteirão. Com KFold aleatório, o
vizinho está no treino e o anúncio no teste; o modelo "acerta" por proximidade, e o
erro medido é de **interpolação**.

O uso real é outro: o simulador prevê para um ponto que o usuário escolhe, muitas vezes
sem nenhum anúncio igual por perto. O erro relevante é o de **generalizar para um
lugar novo**.

## Decisão
- Toda validação de modelo que usa localização é por **bloco espacial**: célula H3 r6
  (~36 km²), `GroupKFold(5, shuffle=True)`.
- A parada antecipada do LightGBM usa uma validação tirada **do treino**, também por
  bloco — nunca o fold de teste.
- O intervalo conformal é calibrado nos resíduos fora do fold e sua cobertura é medida
  em folds que não o calibraram (`cobertura_honesta` em `models/validacao.py`).
- O KFold aleatório é rodado **uma vez**, no modelo principal, só para reportar o
  otimismo que ele produziria.

## Consequências
- As métricas publicadas são piores do que as de um KFold aleatório — de propósito.
- `tests/test_modelos.py` garante que nenhum bloco cruza folds.

**Gatilho que reabre:** se a diferença entre CV espacial e aleatória for desprezível
em todos os modelos, r6 pode dar lugar a r7 para folds mais equilibrados.
