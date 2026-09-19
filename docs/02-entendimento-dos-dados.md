# 2 · Entendimento dos dados

> Números apurados por `src/airbnb/clean/pipeline.py` e `src/airbnb/eda/qualidade.py`
> e gravados em `data/processed/_qualidade.json`, `_perguntas_equipe.json` e
> `_correcoes_v0.json`. São contagens sobre as bases inteiras — a única estimativa
> deste documento é a ocupação (§4), e ela vem com a validação do modelo.

## 1. Fontes primárias

| snapshot | fonte | arquivo | linhas × colunas | licença |
|---|---|---|---|---|
| **2019** (scrape de 2019-07-08) | Kaggle `dgomonov/new-york-city-airbnb-open-data`, v3 | `AB_NYC_2019.csv` (formato *resumo*) | 48.895 × 16 | CC0 |
| **2026** (scrape de 2026-06-14) | Inside Airbnb | `listings.csv.gz` (*detalhado*) | 30.259 × 90 | CC BY 4.0 |
| 2026, conferência | Inside Airbnb | `visualisations/listings.csv` (*resumo*) | 30.555 × 19 | CC BY 4.0 |
| 2026, apoio | Inside Airbnb | avaliações (`listing_id`, `date`), polígonos e lista de bairros | 990.170 avaliações · 233 polígonos | CC BY 4.0 |

Proveniência, URL, bytes e SHA-256 de cada arquivo em
[`data/raw/FONTES.md`](https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc/blob/main/data/raw/FONTES.md);
a ingestão (`python -m airbnb.ingest.baixar`) **confere** o hash a cada execução e
aborta se um arquivo mudar.

Três fatos das fontes condicionam todo o resto:

1. **2019 só existe no formato resumo.** O Inside Airbnb publica para download apenas
   os snapshots dos últimos 12 meses; o de 2019 responde HTTP 403. O Kaggle
   republicou o resumo de julho de 2019 — 16 colunas, sem descrição do imóvel,
   notas, amenidades, licença nem cotação. **Toda comparação entre os anos usa só as
   colunas comuns** (`anuncios_resumo.parquet`).
2. **Em 2026, 12 colunas do detalhado vieram 100% vazias**, entre elas `host_since`,
   `host_response_rate`, `host_acceptance_rate` e `instant_bookable`. Taxa de
   resposta e de aceitação do anfitrião não existem para este snapshot.
3. **O `price` de 2026 não é a mesma grandeza do `price` de 2019** (Q5). É o achado
   de maior consequência para a comparação de preços.

## 2. Perfil das bases

Depois da limpeza ([Preparação dos dados](04-preparacao-dos-dados.md)); "preço válido"
exclui as linhas em quarentena de escopo `preco`.

| | 2019 | 2026 |
|---|---:|---:|
| anúncios | 48.895 | 30.257 |
| anfitriões (`host_id`) | 37.457 | 16.472 |
| bairros com anúncio | 221 | 223 |
| células H3 r9 ocupadas | 3.515 | 3.432 |
| Manhattan · Brooklyn · Queens | 21.661 · 20.104 · 5.666 | 13.709 · 10.561 · 4.679 |
| Bronx · Staten Island | 1.091 · 373 | 976 · 332 |
| imóvel inteiro · quarto privativo | 52,0% · 45,7% | 55,5% · 42,0% |
| quarto compartilhado · quarto de hotel | 2,4% · — | 0,7% · 1,7% |
| **mínimo ≥ 30 noites** (`min30`) | **9,2%** | **81,7%** |
| anúncios de anfitrião com mais de um anúncio | 33,9% | 56,1% |
| sem nenhuma avaliação | 20,6% | 28,3% |
| calendário 100% fechado (`availability_365 = 0`) | 35,9% | 22,4% |
| preço mediano, mínimo < 30 noites | US$ 100 (n = 44.379) | US$ 308,50 (n = 5.012) |
| preço mediano, mínimo ≥ 30 noites | US$ 130 (n = 4.505) | US$ 144,36 (n = 16.102) |

**7.516 anúncios de 2019 (15,4%) ainda existem em 2026**, e 7.124 dos 37.457
anfitriões de 2019 ainda anunciam — base da análise de sobrevivência
(`presente_2026`).

Licença da OSE em 2026 (Local Law 18): 82,5% sem registro declarado, 9,8% "Exempt",
7,7% com número `OSE-STRREG`. O cruzamento com o mínimo de noites mostra a lei
funcionando como desenhada:

| `licenca_status` | mínimo < 30 | mínimo ≥ 30 |
|---|---:|---:|
| registrada | 2.268 | 61 |
| isenta | 2.905 | 51 |
| ausente | **367** | 24.605 |

Dos 5.540 anúncios de curta temporada, só 367 (6,6%) não declaram registro nem isenção.

## 3. As perguntas da equipe

As anotações de [`reports/v0/Análise.txt`](https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc/blob/main/reports/v0/An%C3%A1lise.txt)
viraram testes com número. Q1–Q3 rodam no bruto (antes da limpeza); Q4–Q6 na silver.

### Q1 · "Id — único? Duplicados perfeitos?"

**Único nos dois snapshots, e nenhuma duplicata perfeita — com ou sem o id.**

| | 2019 | 2026 |
|---|---:|---:|
| linhas / ids distintos | 48.895 / 48.895 | 30.259 / 30.259 |
| duplicatas em todas as colunas | 0 | 0 |
| duplicatas em todas as colunas **exceto** o id | 0 | 0 |
| anúncios que dividem anfitrião **e** coordenada exata | 3 (1 grupo) | **3.638** (761 grupos; maior: 49) |
| … e também o preço | 2 | 2.064 |
| … e também o título | 0 | 466 |
| mesmo anfitrião com o mesmo título | 410 | 1.406 |

Os "duplicados semânticos" de 2026 **não são duplicatas**: são unidades distintas do
mesmo prédio (1.957 imóveis inteiros, 1.212 quartos, 465 quartos de hotel), cada uma
com id, calendário e avaliações próprios. Em 2019 isso quase não existia (3 anúncios),
o que sugere que hoje o Airbnb publica a mesma coordenada para as unidades de um
mesmo operador. Consequência para a modelagem: unidades do mesmo prédio em treino e
teste inflariam a métrica — a validação cruzada por bloco H3 ([ADR 0002](adr/0002-validacao-espacial.md))
já as mantém juntas.

### Q2 · "Campo vazio — excluídos?"

**Nenhuma linha foi excluída por nulo.** Os nulos de avaliação são estruturais:

| coluna | 2019 | 2026 | nulo ⟺ `number_of_reviews = 0`? |
|---|---:|---:|---|
| `last_review` | 10.052 | 8.559 | sim, sem exceção |
| `reviews_per_month` | 10.052 | 8.559 | sim, sem exceção |
| `first_review` | — | 8.559 | sim, sem exceção |
| `review_scores_rating` | — | 8.559 | sim, sem exceção |
| `review_scores_accuracy` · `_value` | — | 8.565 · 8.568 | quase: 6 e 9 anúncios avaliados sem a nota parcial |

Preencher `reviews_per_month` com 0, como a v0 fez, está **certo**: sem avaliação, a
taxa é zero. Já `last_review` não tem valor a imputar — fica nulo.

Outros nulos: em 2019, `host_name` (21) e `name` (16); em 2026, `price` (8.744 —
ver Q5), `bathrooms` (33,4%), `bedrooms` (36,3%), `beds` (31,1%), `license` (82,5%) e
os campos do anfitrião em 349 anúncios — 348 deles com `has_availability = f`
(anúncio desativado). **A v0 excluiu as 16 linhas com `name` nulo sem necessidade:**
todas tinham preço positivo, coordenada e bairro, e nenhuma análise usava `name`
(correção c, §4).

### Q3 · "Host id — id do anfitrião; host_name — nome do anfitrião"

**`host_name` não identifica ninguém; `host_id` sim.**

| | 2019 | 2026 |
|---|---:|---:|
| `host_id` distintos | 37.457 | 16.474 |
| `host_name` distintos | 11.452 | 7.001 |
| `host_id` com mais de um nome | 0 | 0 |
| nomes usados por mais de um `host_id` | 3.125 (27,3% dos nomes) | 1.737 (24,8%) |
| anúncios cujo `host_name` é compartilhado com outro anfitrião | 36.325 (**74,3%**) | 17.534 (58,0%) |
| anfitriões distintos com o nome mais comum | 335 | 154 |

Cada `host_id` tem um único nome, mas um mesmo primeiro nome cobre centenas de
anfitriões: agrupar por nome fundiria pessoas diferentes. Como é dado pessoal e não
serve de chave, `host_name` **sai na limpeza** (invariante 9). `host_id` fica na silver
— marcado `pessoal`, nunca publicado — porque mede concentração de oferta.

### Q4 · "Latitude/longitude — mapa de calor, polígono do bairro"

**Todos os pontos estão dentro de NYC e, na prática, dentro do polígono do bairro
declarado — mas isso é tautológico.**

| | 2019 | 2026 |
|---|---:|---:|
| dentro do envelope dos 5 distritos | 48.895 (100%) | 30.257 (100%) |
| dentro do polígono do bairro declarado | 48.878 (99,97%) | 30.257 (100%) |
| em **outro** bairro | 0 | 0 |
| fora de todos os polígonos (orla/água) | 17 — mediana de 84 m do bairro declarado, máx. 361 m | 0 |
| **a menos de 150 m da fronteira do próprio bairro** | **14.364 (29,4%)** | **9.401 (31,1%)** |

Por que quase nenhum ponto "cai em outro bairro": o Inside Airbnb **atribui o bairro
a partir da própria coordenada publicada** — que já é a deslocada. Ponto e bairro não
podem discordar, a não ser por diferença de versão dos polígonos (os 17 casos de 2019,
todos na orla). O efeito do deslocamento de privacidade (0–450 pés, ~150 m, segundo
<https://insideairbnb.com/data-assumptions/>) é sobre o **endereço verdadeiro**, que não
observamos. O que dá para medir é o risco: **~30% dos anúncios estão a menos de 150 m
de uma fronteira**, e para eles o bairro real pode ser o vizinho. É o argumento
quantitativo para a localização ser a célula H3 r9, não o ponto nem o bairro
([ADR 0001](adr/0001-unidade-espacial-h3.md)), e para o "mapa de calor" pedido ser
um coroplético de células H3 r8, não um *heatmap* de pontos.

O `neighbourhoods.geojson` tem 233 feições para 230 bairros (Bayswater, City Island e
Howard Beach vêm em duas partes) e 7 geometrias inválidas, corrigidas com
`shapely.make_valid` antes do cruzamento.

### Q5 · "price — preço por noite?"

**Em 2019, sim. Em 2026, é outra coisa.**

**2019** — diária anunciada pelo anfitrião, em dólares inteiros. Mediana US$ 106,
média US$ 152,72, p99 US$ 799, máximo US$ 10.000; assimetria 19,1. Há 11 preços
zero, **nenhum** entre US$ 1 e US$ 9, 3 anúncios a exatamente US$ 10.000 e 3 a
US$ 9.999.

**2026** — o `price` é uma **cotação**: o Inside Airbnb pede ao site o preço de uma
estadia de N noites a partir da primeira data livre e divide o total por N.

| evidência | resultado |
|---|---|
| `price` = `price_quote_price_per_night` | 21.514 de 21.514 anúncios com os dois (100%) |
| total da cotação = `price` × N | 100% |
| N = mínimo de noites do anúncio | 21.909 de 22.678 cotações (96,6%); mediana de N = 30 |
| check-in da cotação | mediana de 18 dias após o scrape |
| o total inclui | subtotal **após** desconto semanal/mensal, "Airbnb monthly stay savings" e ofertas; resort fee quando há; impostos em 58 cotações |
| o total não inclui | taxa de limpeza e taxa de serviço |
| cotações com algum desconto | 11.393 de 21.513 (53,0%) — mediana 0% (mín. < 30) e 4,3% (mín. ≥ 30); p90 de 22,9% no mín. ≥ 30; máximo 89,9% |

Consequência: para mínimo ≥ 30, o `price` de 2026 é a **diária de um aluguel mensal
com desconto** — não a diária de turista de 2019. Daí a coluna derivada `preco_cheio`
(a diária antes do desconto) e a regra de comparar só estratificado por mínimo de
noites e em dólar constante ([ADR 0005](adr/0005-comparabilidade-2019-2026.md),
invariante 8).

| mediana (preço válido) | mínimo < 30 | mínimo ≥ 30 |
|---|---:|---:|
| 2019, `preco` | US$ 100 | US$ 130 |
| 2026, `preco` (com desconto) | US$ 308,50 | US$ 144,36 |
| 2026, `preco_cheio` (sem desconto) | US$ 313,00 | US$ 164,10 |

**Por que há preço nulo (8.744 anúncios, 28,9%).** 7.581 não têm cotação e 1.163 têm
cotação sem valor (datas indisponíveis). O nulo acompanha o calendário: é nulo em
6.790 dos 6.791 anúncios com `availability_365 = 0` e em 8,3% dos demais — sem data
livre não há o que cotar.

!!! warning "Defeito da fonte: cotações de mais de 31 noites"
    Quando N passa de 31, o Airbnb devolve um total **mensal** ("Average monthly
    price") e o Inside Airbnb o divide por N noites. O preço por noite cai com N sem
    que o total mude:

    | noites cotadas | anúncios | `price` mediano | total mediano da cotação |
    |---|---:|---:|---:|
    | 1–27 | 4.993 | US$ 308,50 | US$ 453 |
    | 28–31 | 16.133 | US$ 144,57 | US$ 4.339 |
    | 32–60 | 146 | US$ 89,98 | US$ 4.778 |
    | 61–120 | 173 | US$ 61,35 | US$ 5.487 |
    | 121–365 | 69 | US$ 25,62 | US$ 5.189 |

    Um anúncio com mínimo de 365 noites aparece a US$ 4,58 a noite. Esses 388 anúncios
    com preço saem das análises de preço (regra P03), mas ficam na base.

### Q6 · "reviews_per_month — é do host ou do anúncio? Por que tem mais que review per month?"

**É do anúncio.** Três testes:

**Teste 1 — recalcular a partir do anúncio (2026).** Avaliações do anúncio ÷ meses desde
a primeira avaliação dele:

| definição | Pearson | concordância |
|---|---:|---|
| total ÷ (dias desde a 1ª avaliação ÷ 30,44) | 0,978 | Spearman 0,999 |
| `number_of_reviews ÷ max(1; (last_scraped − first_review + 1 dia) ÷ 30)` | **0,999998** | idêntico em 2 casas em 21.675 de 21.700 (99,9%); diferença ≤ 0,01 em 99,97% |

A segunda linha **é** a fórmula do Inside Airbnb, reconstruída: só usa dados do
próprio anúncio.

**Teste 2 — variação entre anúncios do mesmo anfitrião.** Se a taxa fosse do
anfitrião, seria constante entre os anúncios dele.

| | 2019 | 2026 |
|---|---:|---:|
| anfitriões com 2+ anúncios avaliados | 4.302 | 2.497 |
| com taxa **diferente** entre os anúncios | 4.234 (98,4%) | 2.468 (98,8%) |

**Teste 3 — "tem mais que...".** `reviews_per_month` maior que `number_of_reviews`:
**0 casos** nos dois snapshots, e é impossível por construção — o denominador tem
piso de 1 mês (1.558 anúncios em 2019 e 203 em 2026 têm a taxa *igual* ao total:
primeira avaliação há menos de um mês). O que parece "demais" são taxas acima de 30
avaliações/mês, mais de uma por dia, impossível para uma unidade só: 1 anúncio em 2019
(máx. 58,5) e 10 em 2026 (máx. 115,6; 7 quartos de hotel, 2 lofts, 1 pousada). São
**anúncios que representam várias unidades** — um tipo de quarto de hotel vendido como
um anúncio —, não agregação por anfitrião.

## 4. O que a v0 mediu e o que de fato mede

A v0 é uma boa leitura descritiva de 2019. Antes de comparar, o script dela (constante
`PY_CODE` do dashboard) foi **reproduzido**: 48.895 → 48.868 linhas (11 preços zero,
16 `name` nulos), ocupação geral de **69,1%** — os mesmos números publicados.

### (a) "Taxa de ocupação" = 1 − `availability_365` ÷ 365

**O que mede:** a fração do calendário dos próximos 365 dias que está **fechada** — noite
reservada *e* noite bloqueada pelo anfitrião, anúncio pausado, calendário que nunca
foi aberto (invariante 7).

| evidência | 2019 | 2026 |
|---|---:|---:|
| anúncios com `availability_365 = 0` (a v0 os conta como 100% ocupados) | 17.533 (35,9%) | 6.789 (22,4%) |
| desses, com ocupação estimada zero (nenhuma avaliação em 12 meses) | — | 6.450 (95,0%) |
| ocupação estimada média desses anúncios | — | 1,5% |
| correlação entre `1 − disponibilidade` e a ocupação estimada | — | Pearson −0,109 · Spearman −0,113 |
| "ocupação" média pela fórmula da v0 | 69,1% | 49,1% |
| **ocupação média pelo modelo de avaliações** | **28,7%** | **14,4%** (campo do Inside Airbnb) |

Em 2026, calendário 100% fechado é quase sempre **anúncio parado**, e a métrica da v0
anda na direção contrária da ocupação.

**Como estimamos a ocupação.** Modelo do Inside Airbnb (<https://insideairbnb.com/data-assumptions/>,
consultado em 2026-09-18): avaliações ÷ taxa de avaliação de 50% = reservas; reservas ×
estadia média (ou o mínimo de noites, se maior) = noites; teto de 70% do ano. A página
dá 3 noites como padrão para cidades sem dado público. Para NYC, o valor saiu do
próprio dado: `estimated_occupancy_l365d` de 2026 é reproduzido **exatamente em
30.257 de 30.257 anúncios** por `min(round(avaliações_12m ÷ 0,5 × max(6,4; mínimo)); 255)`
— estadia média de **6,4 noites**, teto de 255 noites.

2019 não tem avaliações dos últimos 12 meses, só `reviews_per_month` (média da vida
inteira do anúncio). O proxy — a mesma fórmula com a taxa mensal × 12, zerada quando a
última avaliação tem mais de 365 dias — foi validado duas vezes:

| validação | proxy | referência | Spearman | Pearson | erro abs. médio |
|---|---:|---:|---:|---:|---:|
| 2026, todos os anúncios (contra `estimated_occupancy_l365d`) | 18,9% | 14,4% | 0,977 | 0,886 | 5,6 p.p. |
| 2019, 7.516 sobreviventes (contra as avaliações de 12 meses reconstruídas do arquivo de 2026) | 29,5% | 25,5% | 0,938 | 0,887 | 6,8 p.p. |
| *sem* o corte de 365 dias (2026) | 30,6% | 14,4% | 0,622 | 0,618 | 17,3 p.p. |

O corte de atividade é o que faz o proxy funcionar; o viés residual é de **+4,0 a
+4,5 p.p.** nas duas validações (quem já foi muito avaliado e desacelerou). Resultado
para 2019:

| distrito | v0 (1 − disponibilidade) | modelo de avaliações |
|---|---:|---:|
| Manhattan | 69,3% | 26,5% |
| Brooklyn | 72,5% | 28,3% |
| Queens | 60,4% | 35,6% |
| Bronx | 54,6% | 37,6% |
| Staten Island | 45,3% | 41,3% |
| **geral** | **69,1%** | **28,7%** (mediana 16,4%; 40,4% dos anúncios com zero) |

A ordem se inverte: os distritos periféricos, que a v0 punha como os menos ocupados,
são os de maior ocupação estimada por anúncio. Sensibilidade: com 3 noites de estadia
média, 21,8%; sem o corte de atividade, 30,6% (6,4 noites) ou 23,1% (3 noites).
**Nenhuma variante chega perto de 69%.**

O "rendimento potencial" (preço × ocupação) herda o problema:

| distrito | v0 (US$/noite) | preço × ocupação estimada (US$/noite) |
|---|---:|---:|
| Manhattan | 124,0 | 47,9 |
| Staten Island | 48,2 | 34,9 |
| Brooklyn | 86,3 | 33,7 |
| Queens | 57,7 | 32,4 |
| Bronx | 45,2 | 29,2 |

### (b) `drop` do id antes do `drop_duplicates`

A v0 removeu `id`, `host_name` e `last_review` e só então procurou duplicatas. Sem a
chave, dois anúncios distintos com os mesmos atributos seriam fundidos. A verificação
certa é por id e, à parte, por todas as colunas exceto o id (regras B01 e B02). **Efeito
nesta base: nenhum** — 0 duplicatas por qualquer critério. Erro de método, não de número.

### (c) `dropna()` por `name`

Depois de preencher `reviews_per_month`, só `name` ainda tinha nulo: o `dropna()` tirou
**16 anúncios** com preço, coordenada e bairro válidos por causa de um campo que
nenhuma análise usava. Esta versão os mantém.

### (d) Pearson em variáveis de cauda pesada

A v0 usou `df.corr()` (Pearson). Com assimetria de 19,1 no preço, 21,0 no mínimo de
noites e 7,9 nos anúncios por anfitrião, o coeficiente é dominado pelos extremos.
Spearman (postos) mede a relação monotônica:

| par (2019, base da v0) | Pearson | Spearman |
|---|---:|---:|
| avaliações × avaliações/mês | 0,589 | **0,851** |
| anúncios do anfitrião × disponibilidade | 0,226 | **0,407** |
| preço × anúncios do anfitrião | +0,057 | **−0,106** (inverte o sinal) |
| avaliações/mês × disponibilidade | 0,164 | 0,298 |
| mínimo de noites × avaliações/mês | −0,127 | −0,248 |
| preço × avaliações (insight 01 da v0) | −0,048 | −0,055 |

O insight 01 da v0 ("preço e procura praticamente não andam juntos") **se sustenta**
com Spearman. Outras relações eram mais fortes do que a matriz mostrava, e uma trocava
de sinal. Em 2026 (preço válido), a relação que mais muda é preço × mínimo de noites:
−0,224 (Pearson) × **−0,409** (Spearman) — a marca da cotação com desconto mensal.

### O que a v0 acertou

"1 em cada 3 anúncios pertence a um anfitrião com outros imóveis" — **33,9%, confirmado**.
É fração de anúncios; de anfitriões são 13,8% em 2019. Em 2026: 56,1% dos anúncios e
19,4% dos anfitriões — a oferta se concentrou.

## 5. Onde os números moram

| arquivo (versionado) | conteúdo |
|---|---|
| `data/raw/_manifesto.json` | bytes, SHA-256, URL, data de acesso e licença de cada fonte |
| `data/processed/_qualidade.json` | regras de quarentena, cascata, nulos antes/depois, hash das saídas |
| `data/processed/_perguntas_equipe.json` | Q1–Q6 |
| `data/processed/_correcoes_v0.json` | (a)–(d), com a v0 reproduzida |

Nenhum deles contém nome, id de anúncio ou texto livre (invariante 9). Colunas e
tipos: [Dicionário de dados](dicionario-dados.md).
