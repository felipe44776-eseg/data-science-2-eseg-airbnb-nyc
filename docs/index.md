# Airbnb em Nova York, 2019 → 2026

**Data Science 2 · ESEG** — um projeto CRISP-DM completo: da base do Kaggle de 2019
ao mercado de junho de 2026, com fontes públicas externas, modelos preditivos
validados espacialmente e um site público com mapa e teste de localização.

<div class="grid cards" markdown>

- :material-map-search: **[Mapa e teste de localização](https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/mapa/)**

    Escolha um ponto de Nova York e as características de um imóvel: o modelo devolve o
    preço por noite esperado, com faixa de erro, e quanto um anúncio ativo fatura ali.

- :material-presentation-play: **[A apresentação executiva](https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/executiva/)** ·
  [com letra maior](https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/executiva-maior/) ·
  [versão técnica](https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/apresentacao/)

    Vinte slides com os gráficos dos achados e o passo a passo de cada análise, da linha
    do tempo da Local Law 18 à escada de modelos. Setas para navegar, `F` para tela cheia.

- :material-chart-timeline-variant: **[O que mudou desde 2019](05-comparativo-2019-2026.md)**

    Em dólar constante e separado o efeito da Local Law 18 — que transformou o Airbnb de
    Nova York num mercado de aluguel mensal.

- :material-target: **[Os modelos e como foram validados](07-modelagem.md)**

    Escada de modelos, validação cruzada espacial, intervalo conformal, SHAP e a ablação
    que mede quanto cada fonte externa agrega.

- :material-history: **[Da v0 à v1](00-v0-e-o-que-muda.md)**

    O que a versão descritiva do grupo mediu, o que ela de fato media, e o que muda aqui.

</div>

## Como ler esta documentação

A navegação segue as seis fases do CRISP-DM. Cada página diz de qual fase é, cita o
código que produziu cada número e remete às decisões registradas (ADRs).

| fase | pergunta | página |
|---|---|---|
| 1 · negócio | quem decide o quê, e como saberemos se deu certo? | [Entendimento do negócio](01-entendimento-do-negocio.md) |
| 2 · dados | o que as bases dizem — e o que parecem dizer mas não dizem? | [Entendimento dos dados](02-entendimento-dos-dados.md), [Fontes externas](03-fontes-externas.md) |
| 3 · preparação | que regras transformaram o bruto em analisável? | [Preparação dos dados](04-preparacao-dos-dados.md) |
| análise | o que mudou, e a localização importa? | [Comparativo 2019 → 2026](05-comparativo-2019-2026.md), [Testes de localização](06-testes-de-localizacao.md) |
| 4 · modelagem | que modelos, validados como? | [Modelagem](07-modelagem.md) |
| 5 · avaliação | os critérios de sucesso foram atingidos? | [Avaliação](08-avaliacao.md) |
| 6 · implantação | como o modelo chega ao público, fiel ao validado? | [Implantação](09-implantacao.md) |

## Equipe

--8<-- "_snippets/equipe.md"

Código em [github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc](https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc)
— MIT. Dados sob as licenças das fontes ([Ética e LGPD](10-etica-e-lgpd.md) §Atribuição).
