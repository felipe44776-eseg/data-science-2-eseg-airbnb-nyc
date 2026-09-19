# 1 · Entendimento do negócio

> Fase 1 do CRISP-DM. Tudo o que está aqui foi escrito **antes** de qualquer
> modelo ser treinado — inclusive os critérios de sucesso da seção 5. Mudar um
> critério depois de ver o resultado seria ajustar a régua ao salto; se algum for
> revisto, a revisão fica registrada com data e motivo na seção 7.

## 1. O ponto de partida

A v0 do grupo ([`reports/v0/`](https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc/tree/main/reports/v0))
descreveu os 48.895 anúncios do dataset do Kaggle *New York City Airbnb Open Data*:
quantos há por região, quanto custam, quem aluga o quê. É um retrato de **julho de
2019** — e só um retrato. Três limites motivam esta versão:

1. **Descrever não é prever.** "Manhattan é mais cara" não responde quanto deveria
   custar *este* apartamento, *nesta* esquina.
2. **A base sozinha não explica a localização.** O dataset diz *onde* o anúncio está,
   mas não o que há ali: renda do entorno, metrô, criminalidade, restaurantes, aluguel
   de longo prazo. Sem isso, "localização" vira só latitude e longitude.
3. **2019 não é hoje.** Entre o dataset e 2026 houve a pandemia e, sobretudo, a
   **Local Law 18** — que mudou o que um anúncio de Airbnb *é* em Nova York.

## 2. O contexto que muda tudo: a Local Law 18

Em Nova York, alugar um apartamento inteiro por menos de 30 dias sem o morador
presente já era ilegal na maior parte dos prédios residenciais (Multiple Dwelling
Law, 2010). A fiscalização era esparsa. A **Local Law 18 de 2022** (*Short-Term
Rental Registration Law*) passou a ser fiscalizada em **5 de setembro de 2023**:
estadias de menos de 30 dias exigem registro na *Office of Special Enforcement*
(OSE), com o anfitrião morando no imóvel e no máximo dois hóspedes, e as
plataformas ficam proibidas de processar reservas de anúncios não registrados.
A cronologia oficial e as fontes estão em [Fontes externas](03-fontes-externas.md).

A consequência aparece no próprio dado: em 2026, **81,7%** dos anúncios exigem
mínimo de 30 noites. O "Airbnb de Nova York" de 2026 é, majoritariamente, um
mercado de **aluguel mensal mobiliado** — não de turismo de fim de semana.

!!! warning "Implicação para toda comparação 2019 × 2026"
    O campo `price` de um anúncio de 30+ noites em 2026 é a cotação por noite de
    uma estadia longa, com desconto mensal embutido. Comparar a mediana de 2026 com a
    de 2019 sem estratificar pelo mínimo de noites mede a mudança de *composição*,
    não a de *preço*. Ver ADR 0005 e a [análise comparativa](05-comparativo-2019-2026.md).

## 3. Quem decide o quê

| quem | decisão | pergunta que os dados respondem | entregável |
|---|---|---|---|
| **Anfitrião / investidor** | quanto cobrar; onde vale a pena ter um imóvel | quanto um imóvel com estas características, neste ponto, deveria cobrar por noite — e quanto fatura? | simulador do site (preço + intervalo + ocupação) |
| **Hóspede** | reservar ou não | este preço é justo para o que o anúncio oferece e onde está? | mapa de anúncios acima/abaixo do previsto |
| **Poder público / pesquisa urbana** | regulação, fiscalização, habitação | o que a LL18 mudou? quem sobreviveu? onde o aluguel de curta temporada compete com o de longo prazo? | comparativo 2019 → 2026, modelo de sobrevivência |
| **Equipe / banca** | aprovar o método | o resultado é reprodutível e a validação é honesta? | repositório, documentação, testes, paridade Python ↔ JS |

## 4. Objetivos de mineração de dados

Cada pergunta de negócio vira uma tarefa com métrica — e a métrica foi escolhida
pela decisão que ela apoia, não pela que dá o número mais bonito.

| # | tarefa | alvo | métrica principal | por que essa métrica |
|---|---|---|---|---|
| O1 | regressão hedônica de preço | log do preço por noite (2026) | **MdAPE** e MAE em US$ sob **CV espacial** | erro relativo é comparável entre um quarto de US$ 60 e uma cobertura de US$ 900; CV espacial mede o que o simulador faz — prever num lugar novo |
| O2 | intervalo de previsão | idem | **cobertura honesta** do intervalo de 80% | um número sem faixa de erro engana quem decide |
| O3 | ocupação / receita | noites ocupadas estimadas no ano | MAE em noites; correlação de Spearman | receita = preço × ocupação; a v0 errou justamente aqui |
| O4 | sobrevivência 2019 → 2026 | anúncio de 2019 ainda ativo em 2026 | **AUC** e PR-AUC sob CV espacial; Brier | quem sobreviveu à LL18 e à pandemia é pergunta de política pública |
| O5 | validação temporal | preço real 2026 | degradação do MdAPE do modelo de 2019 aplicado a 2026 | mede quanto o "mercado de 2019" ainda explica o de hoje |
| O6 | teste de localização | preço por célula H3 | **I de Moran** (permutação) e LISA | "a localização importa" deixa de ser opinião e vira hipótese testada |

## 5. Critérios de sucesso (registrados antes da modelagem)

| critério | limiar | se falhar |
|---|---|---|
| C1 · modelo de preço bate o baseline descritivo | MAE ≥ **15% menor** que a mediana por bairro × tipo de quarto, sob CV espacial | o modelo não se justifica; publicamos o baseline no simulador |
| C2 · erro relativo utilizável | **MdAPE ≤ 30%** no modelo do produto | o simulador mostra só a faixa, sem a mediana |
| C3 · intervalo calibrado | cobertura honesta do intervalo de 80% entre **77% e 83%** | recalibrar por grupo (conformal de Mondrian) |
| C4 · dados externos agregam | ablação: tirar as features externas **aumenta** o erro de forma consistente entre folds | reportado como resultado nulo — não escondemos |
| C5 · sobrevivência prevê | **AUC ≥ 0,70** sob CV espacial e Brier abaixo do baseline de prevalência | o modelo fica só explicativo (razões de chance), sem previsão no mapa |
| C6 · site fiel ao modelo | paridade Python ↔ JavaScript com erro ≤ **1e-9** no escore bruto | o site não é publicado |
| C7 · reprodutível | `.\tasks.ps1 all` reconstrói tudo a partir das fontes, com hash conferido | bloqueia a entrega |

## 6. Riscos e premissas

| risco | efeito | mitigação |
|---|---|---|
| `price` é preço **anunciado**, não pago | o modelo aprende a expectativa do anfitrião, não o mercado liquidado | declarado em todo resultado; resíduo lido como "acima/abaixo do que anúncios parecidos pedem" |
| coordenadas deslocadas até ~150 m pelo Airbnb | ponto exato é ruído | unidade espacial = H3 r9 (ADR 0001) |
| 2019 só tem 16 colunas (sem quartos, banheiros, comodidades) | modelos de 2019 são mais fracos | comparações 2019 × 2026 usam o mesmo conjunto comum de features |
| o snapshot 2019 detalhado do Inside Airbnb não é público (HTTP 403) | não dá para enriquecer 2019 com a base detalhada | 2019 vem do Kaggle; limitação documentada |
| mudança semântica do `price` pós-LL18 | comparação ingênua mede composição | estratificação por mínimo de noites (ADR 0005) |
| ocupação é **estimada** pelo Inside Airbnb a partir de avaliações | alvo do modelo O3 é modelo de outro modelo | tratado como proxy, com as premissas citadas |
| dados externos com safras e granularidades diferentes | anacronismo (ex.: POIs atuais aplicados a 2019) | cada feature tem safra declarada; anacronismos listados em [Fontes externas](03-fontes-externas.md) |

## 7. Plano do projeto

| fase CRISP-DM | etapa (`tasks.ps1`) | documento |
|---|---|---|
| 1 · negócio | — | este documento |
| 2 · dados | `dados`, `externos` | [02](02-entendimento-dos-dados.md), [03](03-fontes-externas.md) |
| 3 · preparação | `limpeza`, `celulas`, `features` | [04](04-preparacao-dos-dados.md) |
| 2/5 · análise | `comparativo`, `espacial` | [05](05-comparativo-2019-2026.md), [06](06-testes-de-localizacao.md) |
| 4 · modelagem | `preco`, `ocupacao`, `sobrevivencia`, `deriva` | [07](07-modelagem.md) |
| 5 · avaliação | — | [08](08-avaliacao.md) |
| 6 · implantação | `site`, `docs` | [09](09-implantacao.md) |

**Revisões de critério:** nenhuma até o momento.
