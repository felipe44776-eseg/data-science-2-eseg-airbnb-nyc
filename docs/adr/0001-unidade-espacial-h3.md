# ADR 0001 — Localização é a célula H3 r9, não o ponto

**Status:** aceito · **Data:** 2026-09-18

## Contexto
O Airbnb não publica a coordenada real do imóvel: desloca o ponto aleatoriamente,
em até ~150 m, dentro do mesmo bairro (política descrita pelo Inside Airbnb).
Qualquer feature calculada no ponto exato — "distância ao metrô: 212 m" — carrega
um erro da mesma ordem do próprio valor.

Ao mesmo tempo, o simulador do site precisa das features de localização de um ponto
**arbitrário** que o usuário clica, sem backend para calcular distâncias sob demanda.

## Decisão
Três resoluções do índice hexagonal H3, cada uma com um papel:

| resolução | área | papel |
|---|---|---|
| **r9** | ~0,105 km² (aresta ~174 m) | unidade das features de localização, no treino **e** no simulador |
| **r8** | ~0,74 km² | unidade dos mapas coropléticos (anúncios suficientes por célula) |
| **r6** | ~36 km² | bloco da validação cruzada espacial (ADR 0002) |

Toda feature externa é calculada **para a célula r9** (centroide e anel k=1) e o
anúncio herda as features da célula em que cai. O treino e o simulador leem a mesma
tabela — não há como divergirem.

## Alternativas descartadas
- **Features no ponto exato**: precisão fictícia (o ruído de 150 m é da ordem da aresta
  da r9) e exigiria recalcular no navegador.
- **Bairro (neighbourhood) como unidade**: 220 polígonos de tamanhos muito diferentes;
  mistura quarteirões de perfis opostos.
- **Grade regular lat/lon**: distorce área com a latitude e não tem vizinhança uniforme;
  o H3 tem os 6 vizinhos equidistantes que o anel k=1 e o I de Moran usam.

## Consequências
- A tabela `celulas_r9` (~8 mil linhas) é o contrato entre fonte externa, modelo e site.
- O site resolve "em que célula caiu o clique" com `h3-js` e busca as features num JSON.
- Anúncio que cai numa célula fora da cobertura (borda, água) herda a célula coberta
  mais próxima — contado e reportado em [Preparação dos dados](../04-preparacao-dos-dados.md).

**Gatilho que reabre:** se o Airbnb passar a publicar coordenada exata, ou se uma
ablação mostrar ganho relevante com r10.
