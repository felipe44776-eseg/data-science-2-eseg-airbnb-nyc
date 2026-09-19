# Da v0 à v1

A v0 do grupo ([`reports/v0/airbnb-nyc-dashboard-slide.html`](https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc/blob/main/reports/v0/airbnb-nyc-dashboard-slide.html))
é uma boa leitura descritiva de 48.895 anúncios de 2019: clara, visual, com o código
à mostra. Este documento registra, com número, **o que ela mediu, o que de fato
media** e o que a v1 acrescenta. Os números vêm de
`data/processed/_correcoes_v0.json` e `_perguntas_equipe.json`, gerados por
`src/airbnb/eda/qualidade.py` — que primeiro **reproduz** a v0 com o script dela
(48.868 linhas, ocupação geral de 69,1%) e só então compara.

## 1. A correção que muda conclusão: "ocupação"

A v0 calculou `taxa_ocupacao = 1 − availability_365 / 365` e concluiu que *"a cidade
está ocupada na maior parte do tempo — 7 em cada 10 dias"*.

`availability_365` conta os dias **disponíveis para reserva** no calendário dos
próximos 365 dias. Dia indisponível inclui dia **reservado** — mas também dia
**bloqueado pelo anfitrião**, anúncio pausado, calendário nunca aberto. A fórmula
mede "calendário fechado", não "imóvel ocupado".

| evidência | 2019 | 2026 |
|---|---:|---:|
| anúncios com `availability_365 = 0` (a v0 os conta como 100% ocupados) | 17.533 (35,9%) | 6.789 (22,4%) |
| desses, sem nenhuma avaliação nos últimos 12 meses | — | 6.450 (95,0%) |
| correlação de Spearman entre `1 − disponibilidade` e a ocupação estimada | — | **−0,11** |
| "ocupação" média pela fórmula da v0 | 69,1% | 49,1% |
| ocupação média estimada pelo modelo de avaliações do Inside Airbnb | **28,7%** | **14,4%** |

Em 2026, anúncio com calendário 100% fechado quase nunca teve hóspede no ano: é
anúncio parado, não lotado. E a correlação entre a métrica da v0 e a ocupação real
estimada é **negativa**.

**O que usamos no lugar.** O Inside Airbnb estima ocupação a partir das avaliações
(*San Francisco model*: avaliações ÷ taxa de avaliação de 50% × estadia média, com teto
de 70% do ano — parâmetros em <https://insideairbnb.com/data-assumptions/>). Em 2026
o campo pronto `estimated_occupancy_l365d` foi **reproduzido exatamente** nos 30.257
anúncios: `min(round(avaliações_12m ÷ 0,5 × max(6,4; mínimo_de_noites)); 255)`, com
estadia média de 6,4 noites em NYC. Para 2019, o mesmo modelo aplicado ao
`reviews_per_month` dá 28,7% (mediana 16,4%; 40% dos anúncios sem ocupação estimada).

**Consequência na receita por distrito.** O "rendimento potencial por noite" da v0
(preço × ocupação) estava inflado e com a ordem trocada:

| distrito | v0 (US$/noite) | preço × ocupação estimada (US$/noite) |
|---|---:|---:|
| Manhattan | 124,0 | 47,9 |
| Staten Island | 48,2 | 34,9 |
| Brooklyn | 86,3 | 33,7 |
| Queens | 57,7 | 32,4 |
| Bronx | 45,2 | 29,2 |

Staten Island, que a v0 punha em penúltimo, sobe para segundo: tem poucos anúncios,
mas os que existem são mais ocupados. E a distância entre Manhattan e o resto cai
de 1,4–2,7× para 1,4–1,6×.

## 2. Correções de método (sem efeito nesta base, mas erradas por princípio)

| o que a v0 fez | por que é problema | efeito medido |
|---|---|---|
| removeu `id` **antes** de `drop_duplicates()` | sem a chave, dois anúncios distintos com os mesmos atributos seriam fundidos | nenhum: 0 duplicatas por id e 0 sem id — erro de método, não de número |
| `dropna()` depois de preencher `reviews_per_month` | só `name` ainda tinha nulo — a limpeza descartou anúncios válidos por um campo que nenhuma análise usa | 16 anúncios removidos sem necessidade (todos com preço, coordenada e bairro) |
| correlação de **Pearson** em variáveis de cauda pesada (assimetria do preço: 19) | Pearson é dominado por extremos; a relação monotônica some ou inverte | avaliações × avaliações/mês: 0,59 (Pearson) × 0,85 (Spearman); preço × anúncios do anfitrião: +0,06 × −0,11 |
| `reviews_per_month` nulo preenchido com 0 | **correto**: o nulo é estrutural (10.052 nulos ⟺ 10.052 anúncios sem avaliação) | mantido na v1 |

## 3. As perguntas que a equipe anotou

As anotações de `reports/v0/Análise.txt` viraram testes. Respostas completas, com
todos os números, em [Entendimento dos dados](02-entendimento-dos-dados.md).

| pergunta da equipe | resposta |
|---|---|
| "Id — único, duplicados perfeitos?" | único nos dois snapshots; 0 duplicatas perfeitas, com ou sem id. Em 2026 há 3.638 anúncios que dividem anfitrião **e** coordenada (prédios com várias unidades e hotéis) — não são duplicatas |
| "Campo vazio, excluídos?" | nenhuma linha excluída por nulo; os nulos de avaliação são estruturais. Em 2026, 12 colunas vieram 100% vazias (ex.: `host_since`, `instant_bookable`) e ficaram fora |
| "Host id / host name" | `host_name` não identifica: 3.125 nomes são usados por mais de um anfitrião, e 74% dos anúncios de 2019 têm um nome compartilhado. É dado pessoal e saiu da base; `host_id` fica, só para concentração |
| "Latitude/longitude — mapa de calor, polígono do bairro" | 100% dentro de NYC; 99,97% dentro do polígono do bairro declarado. O Airbnb desloca o ponto em até ~150 m — por isso a unidade espacial é a célula H3 (ADR 0001) |
| "price — preço por noite" | em 2019, diária anunciada. **Em 2026, cotação de uma estadia de N noites ÷ N, já com desconto de estadia longa** — `price` = `price_quote_price_per_night` em 100% dos casos |
| "reviews_per_month — do host ou do anúncio?" | **do anúncio**: recalculado como avaliações ÷ meses desde a primeira avaliação (mínimo 1 mês), bate em 99,97% dos anúncios; varia entre anúncios do mesmo anfitrião em 98% dos anfitriões |

## 4. O que a v1 acrescenta

| v0 | v1 |
|---|---|
| uma base (Kaggle 2019) | Kaggle 2019 + Inside Airbnb 2026 + 8 fontes públicas externas |
| descreve | prevê — preço, ocupação, sobrevivência — com validação espacial e intervalo de erro |
| médias por região | modelo que separa "o imóvel" de "o lugar", e testa se o lugar importa (Moran, LISA) |
| retrato de 2019 | comparação em dólar constante com 2026, separando o efeito da Local Law 18 |
| gráfico de dispersão das coordenadas | mapa público com simulador: qualquer ponto, qualquer imóvel |
| script único | pipeline reprodutível, com hash das fontes, testes e decisões registradas |
