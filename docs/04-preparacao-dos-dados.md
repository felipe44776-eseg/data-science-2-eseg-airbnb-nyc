# 3 · Preparação dos dados

> Limpeza: `python -m airbnb.clean.pipeline` (`src/airbnb/clean/`). Números de
> `data/processed/_qualidade.json`. O contrato de cada coluna está no
> [Dicionário de dados](dicionario-dados.md), gerado de `src/airbnb/schema.py`.

## 1. Bronze → silver

| saída (`data/processed/`) | linhas × colunas | conteúdo |
|---|---|---|
| `anuncios_2019.parquet` | 48.895 × 25 | Kaggle limpo e tipado, sem `host_name`, + derivadas |
| `anuncios_2026.parquet` | 30.257 × 102 | detalhado limpo e tipado, sem colunas pessoais nem texto livre, + derivadas |
| `anuncios_resumo.parquet` | 79.152 × 23 | os dois snapshots empilhados nas colunas comuns + `snapshot` |
| `quarentena.parquet` | 9.156 × 5 | toda linha excluída — da base ou do preço — com regra, motivo e escopo |
| `_qualidade.json` | — | regras × snapshot, cascata, nulos antes/depois, hash das entradas e das saídas |

**Por que 2026 vem do detalhado, e não do resumo.** O resumo (`visualisations/listings.csv`)
tem 30.555 linhas; o detalhado, 30.259. O detalhado cobre **todos** os ids que tem em
comum com o resumo com valores **idênticos** em todas as colunas comuns (coordenada,
bairro, tipo, mínimo de noites, avaliações, disponibilidade, licença: 100%); o preço
do resumo é o do detalhado arredondado ao dólar (diferença máxima de US$ 0,50). Os
**296 ids que só o resumo tem** são todos sem `host_id`, `Private room`, mínimo de 1
noite e sem licença; 268 têm nome de hotel ("… Hotel, Deluxe King"), 246 estão em
Manhattan, preço mediano de US$ 249. É inventário de hotel distribuído sem perfil de
anfitrião — o detalhado não o traz, e ele não teria nenhuma das 71 colunas extras.
Ficar com o detalhado custa 296 quartos de hotel (1% do resumo) e ganha cotação,
amenidades, licença, ocupação estimada e notas.

**Tipagem.** Cada coluna recebe o dtype do contrato (`schema.tipos`): datas como
`datetime64`, `t`/`f` como booleano anulável, categorias com domínio fechado. A
conversão **não remenda**: valor fora do domínio de uma categoria e booleano com nulo
são erro (o `pd.Categorical` transformaria o valor estranho em nulo, e o
`astype(bool)` transformaria nulo em `True`). Ao fim, `schema.validar` confere colunas,
ordem, dtypes, domínios e nulos proibidos das três saídas; se algo divergir, **nada é
gravado**.

## 2. Regras e quarentena

Invariante 2: nenhuma linha sai em silêncio. Há dois escopos, e a diferença importa:

- **`base`** — a linha sai de **tudo**: não descreve um anúncio válido.
- **`preco`** — a linha **fica** (conta anúncio, ocupação, mapa), mas sai das análises
  de preço: `preco_valido = False`.

As regras rodam em cascata, na ordem da tabela; cada linha é atribuída à **primeira**
regra em que cai, e a soma fecha com o total. "Casam" conta quem a regra pegaria
sozinha.

| regra | escopo | motivo | 2019 casam · cascata | 2026 casam · cascata |
|---|---|---|---:|---:|
| B01 `id_duplicado` | base | id repetido (mantida a 1ª ocorrência) | 0 · 0 | 0 · 0 |
| B02 `duplicata_perfeita` | base | idêntica a outra linha em tudo, exceto o id | 0 · 0 | 0 · 0 |
| B03 `coordenada_fora_nyc` | base | coordenada nula ou fora do envelope dos 5 distritos | 0 · 0 | 0 · 0 |
| B04 `distrito_invalido` | base | distrito fora dos 5 | 0 · 0 | 0 · 0 |
| B05 `bairro_desconhecido` | base | bairro fora da lista do Inside Airbnb | 0 · 0 | 0 · 0 |
| B06 `room_type_invalido` | base | tipo de acomodação fora do domínio | 0 · 0 | 0 · 0 |
| B07 `minimo_noites_invalido` | base | mínimo de noites nulo ou < 1 | 0 · 0 | **2 · 2** |
| P01 `preco_ausente` | preco | preço nulo (sem cotação) | 0 · 0 | **8.744 · 8.743** |
| P02 `preco_zero` | preco | preço igual a zero | **11 · 11** | 0 · 0 |
| P03 `cotacao_acima_31_noites` | preco | cotação > 31 noites: total mensal ÷ N noites | — | **413 · 388** |
| P04 `preco_abaixo_piso` | preco | 0 < preço < US$ 10 | 0 · 0 | 3 · 0 |
| P05 `preco_acima_teto` | preco | preço > US$ 10.000 | 0 · 0 | **12 · 12** |

As regras de base que não pegaram nada **ficam** — são a prova de que a condição foi
verificada, e disparam se um snapshot futuro trouxer o problema. Os 2 anúncios de
B07 não têm mínimo de noites: sem ele não há como situá-los antes ou depois da Local
Law 18 (invariante 8).

## 3. Limiares de preço, justificados com o dado

Nenhum corte por percentil: cada limiar tem uma razão observável.

- **Piso de US$ 10** (P04). Em 2019 **não existe** preço entre US$ 1 e US$ 9 — os 11 abaixo
  de 10 são zeros (P02). Em 2026 os 3 casos abaixo de US$ 10 (mínimo: US$ 4,58) são
  todos cotações de 180 a 365 noites — já capturados por P03, que é a causa.
- **Teto de US$ 10.000** (P05). O máximo de 2019 é exatamente US$ 10.000 (3 anúncios,
  mais 3 a US$ 9.999): acima disso não há suporte de comparação com 2019. Em 2026, 12
  anúncios passam do teto (até US$ 30.972,96 por noite num apartamento de 7 quartos
  cotado para 30 noites).
- **Cotação acima de 31 noites** (P03). Até 31 noites o total da cotação é do período;
  acima disso o Airbnb devolve um total **mensal** e o Inside Airbnb o divide por N — o
  preço por noite mediano cai de US$ 144,57 (28–31 noites) para US$ 25,62 (121–365)
  enquanto o total mediano fica em US$ 4.300–5.500
  ([Entendimento dos dados, Q5](02-entendimento-dos-dados.md#q5-price-preco-por-noite)).
  Uma correção (total ÷ 30) seria defensável, mas depende de inferir a semântica da
  API; a exclusão do preço é conservadora e reversível.

## 4. Cascata de exclusões

| | 2019 | 2026 |
|---|---:|---:|
| linhas no bruto | 48.895 | 30.259 |
| − escopo `base` | 0 | 2 (B07) |
| **na silver** | **48.895** | **30.257** |
| − preço ausente | 0 | 8.743 |
| − preço zero | 11 | 0 |
| − cotação > 31 noites | — | 388 |
| − abaixo do piso | 0 | 0 |
| − acima do teto | 0 | 12 |
| **com preço válido** | **48.884** | **21.114** |

O código confere que a cascata fecha com a silver (`assert` em `pipeline._cascata`).

**Nulos antes e depois.** A limpeza não imputa nada: todo nulo da silver já estava no
bruto. Em 2019 os nulos são os mesmos (`name` 16; `last_review` e `reviews_per_month`
10.052, estruturais); `host_name` (21) saiu com a coluna. Em 2026 saem as 12 colunas
100% vazias; `banheiros` reduz o nulo de 10.110 (`bathrooms`) para 36 ao completar pelo
texto. Contagem coluna a coluna em `_qualidade.json` → `nulos`.

## 5. Colunas derivadas

Regras em `src/airbnb/clean/derivadas.py` (funções puras, testadas sem o dado real).

### Comuns aos dois snapshots

| coluna | regra |
|---|---|
| `snapshot` | `"2019"` ou `"2026"` (`config.ROTULO_*`) |
| `preco` | `price` como número: `"$1,234.00"` → 1234.0 (2019 já é inteiro) |
| `preco_valido` | não caiu em nenhuma regra de escopo `preco` |
| `min30` | `minimum_nights ≥ 30` (`config.NOITES_CURTA_TEMPORADA`) |
| `host_multi` | `calculated_host_listings_count > 1` |
| `h3_r9`, `h3_r8`, `h3_r6` | `h3.latlng_to_cell(lat, lon, res)` nas resoluções de `config` (features, mapa, blocos de CV) |
| `dias_desde_ultima_avaliacao` | dias entre `last_review` e o scrape (2019: `config.SNAPSHOT_2019`; 2026: `last_scraped`) |
| `ocupacao_modelo` | modelo de avaliações do Inside Airbnb, igual nos dois anos: `reviews_per_month × 12 ÷ 0,5 × max(6,4; mínimo) ÷ 365`, teto 0,70, zero sem avaliação em 365 dias ([§4 da fase 2](02-entendimento-dos-dados.md#4-o-que-a-v0-mediu-e-o-que-de-fato-mede)) |
| `presente_2026` (só 2019) | o id ainda aparece no snapshot de 2026 (7.516 anúncios) |

### Só 2026

| coluna | regra |
|---|---|
| `preco_cotacao_noites` | noites da cotação (`checkout − checkin`) |
| `preco_cheio` | diária **sem desconto**: (total da cotação + \|itens negativos\|) ÷ noites; coincide até US$ 1 com o item "Average monthly price" em 16.486 de 16.515 cotações (as 29 restantes têm imposto no total) |
| `desconto_pct` | \|itens negativos\| ÷ preço cheio do período; 0 sem item de desconto; nulo sem cotação ou com JSON malformado |
| `banheiros` | `bathrooms` quando existe; senão o número do texto; "half-bath" = 0,5. Número e texto concordam em 99,995% das 20.024 linhas que têm os dois |
| `banheiro_compartilhado` | "shared" no `bathrooms_text` (7.292 anúncios); nulo sem texto (159) |
| `n_amenidades` + 17 `amen_*` | contagem e flags da lista JSON (abaixo) |
| `licenca_status` | `registrada` (começa com OSE-STRREG, sem distinguir caixa: 2.329) · `isenta` ("Exempt": 2.956) · `ausente` (24.972) · `outra` (0) |
| `host_superhost` | `host_is_superhost` com nulo = False (349 anúncios sem perfil) |
| `host_anos` | `hosts_time_as_host_years + months ÷ 12` — `host_since` veio 100% vazio |
| `meses_desde_primeira_avaliacao` | (`last_scraped − first_review`) em dias ÷ 30,4375 |
| `tipo_imovel_grupo` | 69 `property_type` em 7 grupos, por regra de texto com o `room_type` como rede de segurança |

`tipo_imovel_grupo`: apartamento inteiro 14.711 · quarto em apartamento 7.413 · quarto
em casa 3.739 · hotel ou pousada 2.122 · casa inteira 2.005 · quarto compartilhado
218 · atípico (barco, trailer, torre, domo…) 49.

**Não derivadas, por falta de fonte:** taxas de resposta e de aceitação do anfitrião
(0–1) — `host_response_rate` e `host_acceptance_rate` vieram 100% vazias em 2026.

### Amenidades: critério de escolha

A lista de 2026 tem 6.179 itens distintos, com a mesma coisa grafada de várias formas
("Washer", "Free washer – In unit", "Paid washer – In building"). Cada flag é uma
expressão regular sobre cada item (em `schema.AMENIDADES`), testada contra as
armadilhas da grafia: "Hair dryer" não é secadora, "Dishwasher" não é lavadora, "Pool
table" não é piscina, "Shared gym nearby" não é academia, "Free street parking" não é
estacionamento do imóvel, "Movie theater" não é aquecedor.

Critério: (1) **atributo do imóvel ou do prédio** com efeito plausível sobre o preço
(conforto, serviço do prédio, uso por estadia longa); (2) fora consumíveis (xampu,
cabides) e itens **exigidos por lei em NYC** (detector de fumaça e de CO), que não
diferenciam anúncio; (3) prevalência de pelo menos 1%. Razão = preço mediano com a
amenidade ÷ sem, entre preços válidos, **por estrato** de mínimo de noites (o `price`
de 2026 não é a mesma grandeza nos dois). É razão bruta, sem controle — indica
relevância, não efeito: academia e porteiro andam junto com prédio de alto padrão em
Manhattan, e o modelo de preço é quem separa.

| flag | prevalência | razão, mín. < 30 | razão, mín. ≥ 30 |
|---|---:|---:|---:|
| `amen_wifi` | 98,5% | 1,16 | 1,01 |
| `amen_ar_condicionado` | 90,8% | 1,19 | 1,82 |
| `amen_cozinha` | 88,0% | 0,90 | 1,26 |
| `amen_aquecimento` | 87,0% | 1,05 | 1,15 |
| `amen_tv` | 80,5% | 1,61 | 1,96 |
| `amen_espaco_trabalho` | 51,7% | 1,10 | 1,18 |
| `amen_lavadora` | 45,6% | 1,30 | 1,48 |
| `amen_self_checkin` | 45,5% | 0,99 | 1,39 |
| `amen_secadora` | 39,7% | 1,30 | 1,49 |
| `amen_lava_loucas` | 26,9% | 1,36 | 1,83 |
| `amen_permite_pets` | 25,4% | 1,28 | 1,83 |
| `amen_elevador` | 24,1% | 1,21 | 1,82 |
| `amen_varanda_patio` | 19,9% | 0,91 | 1,18 |
| `amen_academia` | 19,2% | 1,44 | 2,00 |
| `amen_estacionamento` | 18,2% | 1,15 | 1,10 |
| `amen_porteiro` | 10,2% | 1,42 | 2,68 |
| `amen_piscina` | 2,2% | 1,43 | 2,78 |

Wi-Fi é quase constante (98,5%) e quase não discrimina no estrato ≥ 30: fica por ter
sido pedida e por sinalizar anúncio incompleto quando falta, mas o modelo pode descartá-la.

## 6. Dado pessoal

Sai na limpeza (invariante 9): `host_name`, `host_about`, `host_location`,
`host_picture_url`, `host_thumbnail_url`, `host_url`, `host_profile_url`,
`host_profile_id`, `host_neighbourhood`, `listing_url`, `picture_url`, `description`,
`neighborhood_overview` — lista em `schema.PROIBIDAS_NA_SILVER`, conferida por teste
contra os parquets reais.

Fica, marcado `pessoal = True` (nunca publicado): `id` e `host_id` (cruzar snapshots,
medir concentração) e `name`, o título do anúncio (análise de duplicatas).
`amenities` fica: é lista de comodidades, não texto do anfitrião.

## 7. Reprodutibilidade

- **Idempotente:** duas execuções completas produziram o mesmo hash de conteúdo nas
  quatro saídas (`_qualidade.json` → `saidas`); teste com frames sintéticos trava isso.
- **Determinística:** nenhuma amostragem; a ordem das linhas é a do arquivo de origem.
- **Rastreável:** `_qualidade.json` guarda o SHA-256 de cada arquivo de entrada (do
  manifesto) e o hash de conteúdo de cada saída.
- **Testada:** `tests/test_limpeza.py` e `tests/test_schema.py` rodam sem o dado real;
  os testes marcados `dados` conferem os parquets reais contra o contrato.

## 8. Junção com as features de localização

A silver de anúncios é unida às features de localização pela célula H3 r9
(`h3_r9`, [ADR 0001](adr/0001-unidade-espacial-h3.md)) em `src/airbnb/features/anuncios.py`,
que produz as tabelas de modelagem anúncio × célula (`modelagem_2019.parquet`,
`modelagem_2026.parquet`) e o resumo `data/processed/_features.json`.

**Três decisões:**

1. **A localização é a da célula, não a do anúncio.** O anúncio herda as features
   da célula r9 em que cai — inclusive latitude e longitude, que no modelo são as do
   **centroide** da célula, e o distrito, que é o **da célula**. É o que o simulador
   do site conhece para um clique; treino e produto leem a mesma tabela.
2. **Anúncio fora da cobertura herda a célula coberta mais próxima**, até o anel
   k = 3 (~0,5 km). A cobertura é a malha r9 recortada pelos polígonos terrestres dos
   bairros; um ponto deslocado para a água ou para a margem cai numa célula não
   coberta. Quantos foram realocados, e a que distância, está em `_features.json` →
   `realocados_por_anel`; quem ficasse além de k = 3 ficaria sem feature de
   localização, contado em `sem_celula_coberta` — nunca descartado em silêncio.
3. **Cada snapshot recebe a sua safra.** 2019 recebe ACS 2015–2019, crimes e 311 de
   jul/2018–jul/2019 e o aluguel Zillow de jul/2019; 2026 recebe as safras atuais.
   Features sem safra (metrô, POIs do OpenStreetMap, marcos) são as mesmas nos dois —
   anacronismo declarado em [Fontes externas](03-fontes-externas.md).

**Codificações.** Categorias viram inteiros estáveis na ordem do `schema.py`
(`room_type_cod`, `tipo_imovel_cod`, `licenca_cod`, `distrito_cod`) — o site envia
exatamente esses códigos. Booleanos viram 0/1 (ausente continua ausente: o LightGBM e
o avaliador JavaScript tratam o ausente pela mesma regra). O preço de 2019 ganha
`preco_real`, em dólar do snapshot atual pelo CPI-U NY ([ADR 0005](adr/0005-comparabilidade-2019-2026.md)).
