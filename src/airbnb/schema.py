"""Contrato de dados das bases do Airbnb — fonte unica de verdade (invariante 1).

Tres camadas, na ordem em que o dado anda:

1. **Colunas brutas** (`BRUTAS`): o que cada arquivo de origem traz, com o
   tratamento que recebe na limpeza — mantida, renomeada, usada para derivar ou
   descartada (e por que). Cobre o resumo de 2019 (Kaggle), o resumo de 2026 e o
   detalhado de 2026 do Inside Airbnb. O mesmo nome pode significar coisas
   diferentes em arquivos diferentes (`neighbourhood` e o bairro no Kaggle e um
   campo 100% vazio no detalhado), por isso a chave e (arquivo, nome).
2. **Colunas da silver** (`ESQUEMA`): o contrato dos parquets em
   `data/processed/`. Nome, dtype, dominio, descricao, origem e a flag
   `pessoal`. Coluna de origem mantem o nome da origem (rastreavel ao
   dicionario do Inside Airbnb); derivada e pt-BR snake_case.
3. **Constantes `COL_*`**: o nome que os outros modulos importam. Ninguem
   escreve "h3_r9" a mao fora daqui.

`pessoal=True` significa "nunca sai para site nem relatorio" (invariante 9):
identificadores (id do anuncio, id do anfitriao), nome e textos do anfitriao,
URLs e fotos. Algumas dessas colunas continuam na silver porque a analise
precisa delas (o titulo `name`, os ids para cruzar snapshots) — a flag e o que
impede que cheguem a uma superficie publicada.

Se o dado violar o contrato, `validar` devolve a lista de violacoes e a limpeza
para — nao remenda.

Uso:
    python -m airbnb.schema              # imprime o dicionario em Markdown
    python -m airbnb.schema --escrever   # grava docs/dicionario-dados.md
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from airbnb import config

# --- arquivos de origem ---------------------------------------------------------

KAGGLE_2019 = "kaggle_2019"  #: data/raw/kaggle/AB_NYC_2019.csv (resumo de 2019)
RESUMO_2026 = "resumo_2026"  #: insideairbnb/<data>/listings_resumo.csv
DETALHADO_2026 = "detalhado_2026"  #: insideairbnb/<data>/listings.csv.gz

ARQUIVOS_ORIGEM = {
    KAGGLE_2019: "data/raw/kaggle/AB_NYC_2019.csv",
    RESUMO_2026: f"data/raw/insideairbnb/{config.SNAPSHOT_ATUAL}/listings_resumo.csv",
    DETALHADO_2026: f"data/raw/insideairbnb/{config.SNAPSHOT_ATUAL}/listings.csv.gz",
}

# --- saidas (parquets da silver) -------------------------------------------------

S2019 = "anuncios_2019"
S2026 = "anuncios_2026"
SRESUMO = "anuncios_resumo"
SAIDAS = (S2019, S2026, SRESUMO)
_TODAS = SAIDAS
_SO_2026 = (S2026,)
_2019_E_2026 = (S2019, S2026)

# --- dominios ---------------------------------------------------------------------

ROOM_TYPES = ("Entire home/apt", "Private room", "Shared room", "Hotel room")
SNAPSHOTS = (config.ROTULO_2019, config.ROTULO_ATUAL)
FONTES_SCRAPE = ("city scrape", "previous scrape")
LICENCA_STATUS = ("registrada", "isenta", "ausente", "outra")
TIPOS_IMOVEL = (
    "apartamento_inteiro",
    "casa_inteira",
    "quarto_em_apartamento",
    "quarto_em_casa",
    "hotel_pousada",
    "quarto_compartilhado",
    "atipico",
)

# --- nomes que os outros modulos importam ------------------------------------------

# colunas de origem (nome da origem)
COL_ID = "id"
COL_NOME = "name"
COL_HOST_ID = "host_id"
COL_DISTRITO = "neighbourhood_group"  # 2019 e resumo; em anuncios_2026 e _cleansed
COL_BAIRRO = "neighbourhood"
COL_DISTRITO_2026 = "neighbourhood_group_cleansed"
COL_BAIRRO_2026 = "neighbourhood_cleansed"
COL_LAT = "latitude"
COL_LON = "longitude"
COL_ROOM_TYPE = "room_type"
COL_MIN_NOITES = "minimum_nights"
COL_N_AVALIACOES = "number_of_reviews"
COL_N_AVALIACOES_LTM = "number_of_reviews_ltm"
COL_ULTIMA_AVALIACAO = "last_review"
COL_PRIMEIRA_AVALIACAO = "first_review"
COL_AVALIACOES_MES = "reviews_per_month"
COL_ANUNCIOS_HOST = "calculated_host_listings_count"
COL_DISPONIBILIDADE_365 = "availability_365"
COL_OCUPACAO_L365D = "estimated_occupancy_l365d"
COL_RECEITA_L365D = "estimated_revenue_l365d"
COL_LICENCA = "license"
COL_ULTIMO_SCRAPE = "last_scraped"

# derivadas (pt-BR snake_case)
COL_SNAPSHOT = "snapshot"
COL_PRECO = "preco"
COL_PRECO_VALIDO = "preco_valido"
COL_MIN30 = "min30"
COL_HOST_MULTI = "host_multi"
COL_H3_R9 = "h3_r9"
COL_H3_R8 = "h3_r8"
COL_H3_R6 = "h3_r6"
COL_OCUPACAO_MODELO = "ocupacao_modelo"
COL_DIAS_ULTIMA_AVALIACAO = "dias_desde_ultima_avaliacao"
COL_PRESENTE_2026 = "presente_2026"
COL_PRECO_COTACAO_NOITES = "preco_cotacao_noites"
COL_PRECO_CHEIO = "preco_cheio"
COL_DESCONTO_PCT = "desconto_pct"
COL_BANHEIROS = "banheiros"
COL_BANHEIRO_COMPARTILHADO = "banheiro_compartilhado"
COL_N_AMENIDADES = "n_amenidades"
COL_LICENCA_STATUS = "licenca_status"
COL_HOST_SUPERHOST = "host_superhost"
COL_HOST_ANOS = "host_anos"
COL_MESES_PRIMEIRA_AVALIACAO = "meses_desde_primeira_avaliacao"
COL_TIPO_IMOVEL_GRUPO = "tipo_imovel_grupo"

#: Resolucao H3 de cada coluna de celula (config manda; aqui so o nome).
COLUNAS_H3 = {
    COL_H3_R9: config.H3_RES_FEATURES,
    COL_H3_R8: config.H3_RES_MAPA,
    COL_H3_R6: config.H3_RES_CV,
}

#: Amenidades viram flag por expressao regular sobre CADA item da lista JSON
#: (sem distinguir caixa). O Airbnb grafa a mesma coisa de varias formas
#: ("Washer", "Free washer – In unit", "Paid washer – In building"), entao a
#: regra e por padrao, nao por igualdade. Criterio de escolha em docs/04 §4:
#: atributo do imovel ou do predio com efeito plausivel sobre o preco — fora
#: consumiveis (xampu, cabides) e itens exigidos por lei em NYC (detector de
#: fumaca e de CO), que nao diferenciam anuncio. Prevalencia e razao de preco
#: de cada flag saem em _qualidade.json.
AMENIDADES: dict[str, tuple[str, str]] = {
    "amen_wifi": (r"\bwi-?fi\b", "Wi-Fi (inclui 'Fast wifi – N Mbps' e 'Pocket wifi')"),
    "amen_cozinha": (r"^(kitchen|kitchenette)$", "cozinha ou kitchenette (não conta cozinha externa nem eletrodoméstico KitchenAid)"),
    "amen_ar_condicionado": (r"air conditioning|\bac\b", "ar-condicionado: central, de janela, split ou portátil"),
    "amen_aquecimento": (r"heating|\bheater\b", "aquecimento: central, radiante, split ou aquecedor portátil"),
    "amen_lavadora": (r"\bwasher\b", "lavadora de roupa, na unidade ou no prédio (não conta lava-louças)"),
    "amen_secadora": (r"(?<!hair )\bdryer\b", "secadora de roupa (não conta secador de cabelo)"),
    "amen_lava_loucas": (r"dishwasher", "lava-louças"),
    "amen_elevador": (r"\belevator\b", "elevador"),
    "amen_academia": (r"^(?!.*nearby).*(\bgym\b|exercise equipment)", "academia no prédio ou equipamento de ginástica (não conta 'nearby')"),
    "amen_estacionamento": (r"parking.*on premises|garage on premises|carport", "estacionamento no imóvel, pago ou gratuito (não conta vaga na rua)"),
    "amen_piscina": (r"\bpool\b(?! table| view)", "piscina (não conta mesa de sinuca nem vista para piscina)"),
    "amen_porteiro": (r"building staff|doorman|concierge", "equipe no prédio / porteiro"),
    "amen_self_checkin": (r"self check-?in", "self check-in"),
    "amen_espaco_trabalho": (r"workspace", "espaço de trabalho dedicado"),
    "amen_tv": (r"\b(hd)?tv\b", "TV"),
    "amen_varanda_patio": (r"patio|balcon|backyard|terrace", "varanda, pátio, quintal ou terraço"),
    "amen_permite_pets": (r"pets allowed", "aceita animais de estimação"),
}
COLS_AMENIDADES = list(AMENIDADES)

# --- estruturas ---------------------------------------------------------------------


@dataclass(frozen=True)
class Coluna:
    """Uma coluna da silver — o contrato que os modulos a jusante leem.

    `dtype` e o dtype pandas depois da limpeza ("str" e o texto padrao do
    pandas 3; "Int64"/"boolean" sao os anulaveis). `minimo`/`maximo`/`dominio`
    sao conferidos por `validar`; `aceita_nulo=False` idem.
    """

    nome: str
    dtype: str
    descricao: str
    origem: str
    saidas: tuple[str, ...]
    pessoal: bool = False
    minimo: float | None = None
    maximo: float | None = None
    dominio: tuple | None = None
    aceita_nulo: bool = True


@dataclass(frozen=True)
class ColunaBruta:
    """Uma coluna como vem no arquivo de origem, e o que a limpeza faz com ela.

    `tratamento`: "mantida" (mesmo nome na silver), "renomeada" (vira
    `destino`), "derivada" (so alimenta derivadas; nao fica), "descartada" ou
    "referencia" (arquivo usado so para conferencia).
    """

    arquivo: str
    nome: str
    dtype: str
    descricao: str
    tratamento: str
    destino: str = ""
    pessoal: bool = False
    motivo: str = ""


def _c(nome, dtype, descricao, origem, saidas, **kw) -> Coluna:
    return Coluna(nome, dtype, descricao, origem, saidas, **kw)


# --- contrato da silver ----------------------------------------------------------------

_ESQ: list[Coluna] = [
    # identificacao
    _c(COL_SNAPSHOT, "category", "Snapshot de origem da linha: \"2019\" (Kaggle, scrape de 2019-07-08) ou \"2026\" (Inside Airbnb, 2026-06-14).",
       "derivada (constante por arquivo; config.ROTULO_*)", _TODAS, dominio=SNAPSHOTS, aceita_nulo=False),
    _c(COL_ID, "int64", "Identificador do anúncio no Airbnb. Único por snapshot (conferido). Nunca publicado.",
       "origem: `id`", _TODAS, pessoal=True, minimo=1, aceita_nulo=False),
    _c(COL_ULTIMO_SCRAPE, "datetime64[ns]", "Data em que o anúncio foi coletado. Quatro datas entre 14 e 23/06/2026: o scrape da cidade (14–15) e a recoleta dos anúncios vistos no scrape anterior (22–23).",
       "origem: `last_scraped` (detalhado)", _SO_2026, aceita_nulo=False),
    _c("source", "category", "Como o anúncio entrou no scrape: `city scrape` (achado na busca da cidade) ou `previous scrape` (existia no scrape anterior e foi recoletado pelo id).",
       "origem: `source` (detalhado)", _SO_2026, dominio=FONTES_SCRAPE, aceita_nulo=False),
    _c(COL_NOME, "str", "Título do anúncio, escrito pelo anfitrião. Texto livre: usado só em análise (ex.: duplicatas), nunca publicado.",
       "origem: `name`", _2019_E_2026, pessoal=True),
    _c(COL_HOST_ID, "int64", "Identificador do anfitrião. Único identificador confiável do anfitrião (o nome não é — ver Q3). Nunca publicado.",
       "origem: `host_id`", _TODAS, pessoal=True, minimo=1, aceita_nulo=False),
    # anfitriao (so 2026)
    _c("hosts_time_as_user_years", "float64", "Anos completos desde que o anfitrião criou a conta no Airbnb (campo novo do Inside Airbnb; substitui `host_since`, que veio 100% vazio).",
       "origem: detalhado", _SO_2026, minimo=0),
    _c("hosts_time_as_user_months", "float64", "Meses restantes (0–11) além de `hosts_time_as_user_years`.",
       "origem: detalhado", _SO_2026, minimo=0, maximo=11),
    _c("hosts_time_as_host_years", "float64", "Anos completos desde que a conta passou a anunciar.",
       "origem: detalhado", _SO_2026, minimo=0),
    _c("hosts_time_as_host_months", "float64", "Meses restantes (0–11) além de `hosts_time_as_host_years`.",
       "origem: detalhado", _SO_2026, minimo=0, maximo=11),
    _c("host_is_superhost", "boolean", "Selo de Superhost (t/f da origem convertido em booleano; nulo nos 349 anúncios sem perfil de anfitrião).",
       "origem: `host_is_superhost`", _SO_2026),
    _c("host_listings_count", "Int64", "Anúncios do anfitrião segundo o perfil no Airbnb (inclui outras cidades). Difere de `calculated_host_listings_count` em 33% dos anúncios.",
       "origem: detalhado", _SO_2026, minimo=0),
    _c("host_has_profile_pic", "boolean", "Anfitrião tem foto de perfil (só o indicador; a foto em si é descartada).",
       "origem: detalhado", _SO_2026),
    _c("host_identity_verified", "boolean", "Anfitrião com identidade verificada pelo Airbnb.",
       "origem: detalhado", _SO_2026),
    # localizacao
    _c(COL_DISTRITO, "category", "Distrito (borough) de Nova York. Em 2026 vem de `neighbourhood_group_cleansed` (atribuído pelo Inside Airbnb a partir da coordenada).",
       "origem: `neighbourhood_group` (Kaggle); `neighbourhood_group_cleansed` (2026)", (S2019, SRESUMO), dominio=config.DISTRITOS, aceita_nulo=False),
    _c(COL_BAIRRO, "str", "Bairro (Neighbourhood Tabulation Area do Inside Airbnb). Os 221 bairros de 2019 existem todos no neighbourhoods.geojson de 2026.",
       "origem: `neighbourhood` (Kaggle); `neighbourhood_cleansed` (2026)", (S2019, SRESUMO), aceita_nulo=False),
    _c(COL_DISTRITO_2026, "category", "Distrito (borough) atribuído pelo Inside Airbnb pela coordenada. Vira `neighbourhood_group` em anuncios_resumo.",
       "origem: detalhado", _SO_2026, dominio=config.DISTRITOS, aceita_nulo=False),
    _c(COL_BAIRRO_2026, "str", "Bairro atribuído pelo Inside Airbnb pela coordenada (o campo `neighbourhood` do detalhado veio 100% vazio). Vira `neighbourhood` em anuncios_resumo.",
       "origem: detalhado", _SO_2026, aceita_nulo=False),
    _c(COL_LAT, "float64", "Latitude publicada. O Airbnb desloca o ponto em até ~150 m (0–450 pés) para proteger o endereço: a unidade de análise é a célula H3, não o ponto (ADR 0001).",
       "origem: `latitude`", _TODAS, minimo=config.NYC_BBOX[1], maximo=config.NYC_BBOX[3], aceita_nulo=False),
    _c(COL_LON, "float64", "Longitude publicada (mesmo deslocamento da latitude).",
       "origem: `longitude`", _TODAS, minimo=config.NYC_BBOX[0], maximo=config.NYC_BBOX[2], aceita_nulo=False),
    # imovel
    _c("property_type", "str", "Tipo de imóvel como o anfitrião declarou (69 valores em 2026). Agrupado em `tipo_imovel_grupo`.",
       "origem: detalhado", _SO_2026, aceita_nulo=False),
    _c(COL_ROOM_TYPE, "category", "Tipo de acomodação. `Hotel room` só existe em 2026 (520 anúncios); em 2019 havia três categorias.",
       "origem: `room_type`", _TODAS, dominio=ROOM_TYPES, aceita_nulo=False),
    _c("accommodates", "int64", "Número máximo de hóspedes.", "origem: detalhado", _SO_2026, minimo=1, aceita_nulo=False),
    _c("bathrooms", "float64", "Número de banheiros como o Inside Airbnb extraiu (33% nulo). Ver `banheiros`, que completa pelo texto.",
       "origem: detalhado", _SO_2026, minimo=0),
    _c("bathrooms_text", "str", "Banheiros em texto (\"1.5 shared baths\", \"Half-bath\"...). Fonte de `banheiros` e `banheiro_compartilhado`.",
       "origem: detalhado", _SO_2026),
    _c("bedrooms", "float64", "Número de quartos (36% nulo).", "origem: detalhado", _SO_2026, minimo=0),
    _c("beds", "float64", "Número de camas (31% nulo).", "origem: detalhado", _SO_2026, minimo=0),
    _c("amenities", "str", "Lista JSON de comodidades, grafia livre do Airbnb (6.179 itens distintos). Fonte de `n_amenidades` e das flags `amen_*`.",
       "origem: detalhado", _SO_2026, aceita_nulo=False),
    # preco
    _c(COL_PRECO, "float64", "Preço por noite em US$. 2019: diária anunciada. 2026: cotação de uma estadia de N noites (N = `preco_cotacao_noites`, em regra o mínimo do anúncio) dividida por N, JÁ COM desconto semanal/mensal — não é a mesma grandeza de 2019 (ADR 0005). Nulo quando não houve cotação.",
       "origem: `price` (Kaggle: inteiro; 2026: texto \"$1,234.00\")", _TODAS, minimo=0),
    _c(COL_PRECO_VALIDO, "bool", "True quando o preço entra nas análises de preço: não caiu em nenhuma regra de escopo `preco` da quarentena (ausente, zero, cotação > 31 noites, < US$ 10, > US$ 10.000).",
       "derivada: regras P01–P05 da limpeza", _TODAS, aceita_nulo=False),
    _c(COL_PRECO_COTACAO_NOITES, "Int64", "Noites da estadia cotada (checkout − checkin da cotação). Igual ao mínimo de noites em 96,6% das cotações; mediana 30.",
       "derivada: `price_quote_checkout_date` − `price_quote_checkin_date`", _SO_2026, minimo=1),
    _c(COL_PRECO_CHEIO, "float64", "Diária SEM desconto: preço cheio do período cotado (total + |descontos|; coincide até US$ 1 com o item \"Average monthly price\" em 99,8% das cotações que o têm) ÷ noites da cotação. Alternativa de robustez a `preco` na comparação com 2019. Mesma ressalva de `preco` para cotações > 31 noites.",
       "derivada: `price_quote_raw` (JSON) e `price_quote_total_price`", _SO_2026, minimo=0),
    _c(COL_DESCONTO_PCT, "float64", "Fração do preço cheio do período abatida por descontos (mensal, semanal, oferta especial, antecipação): Σ|itens negativos| ÷ preço cheio. 0 quando a cotação não tem desconto; nulo sem cotação.",
       "derivada: `price_quote_raw` (JSON)", _SO_2026, minimo=0, maximo=1),
    _c("price_quote_checkin_date", "datetime64[ns]", "Início da estadia cotada pelo Inside Airbnb (primeira data livre; mediana 18 dias após o scrape).",
       "origem: detalhado", _SO_2026),
    _c("price_quote_checkout_date", "datetime64[ns]", "Fim da estadia cotada.", "origem: detalhado", _SO_2026),
    _c("price_quote_total_price", "float64", "Total cotado após descontos (sem taxa de limpeza e de serviço; inclui resort fee quando houver). Em cotações > 31 noites é um total MENSAL, não do período.",
       "origem: detalhado", _SO_2026, minimo=0),
    # regras de estadia
    _c(COL_MIN_NOITES, "int64", "Mínimo de noites por reserva. ≥ 30 é o limiar da Local Law 18 (ver `min30`).",
       "origem: `minimum_nights`", _TODAS, minimo=1, aceita_nulo=False),
    _c(COL_MIN30, "bool", "Mínimo de noites ≥ 30 (config.NOITES_CURTA_TEMPORADA): fora do alcance do registro da Local Law 18. 9,2% em 2019, 81,7% em 2026.",
       "derivada: `minimum_nights` ≥ 30", _TODAS, aceita_nulo=False),
    _c("maximum_nights", "Int64", "Máximo de noites por reserva. 2.147.483.647 (2³¹−1) é sentinela de \"sem máximo\".",
       "origem: detalhado", _SO_2026, minimo=1),
    _c("minimum_minimum_nights", "float64", "Menor mínimo de noites no calendário dos próximos 365 dias.", "origem: detalhado", _SO_2026, minimo=0),
    _c("maximum_minimum_nights", "float64", "Maior mínimo de noites no calendário dos próximos 365 dias.", "origem: detalhado", _SO_2026, minimo=0),
    _c("minimum_maximum_nights", "float64", "Menor máximo de noites no calendário.", "origem: detalhado", _SO_2026, minimo=0),
    _c("maximum_maximum_nights", "float64", "Maior máximo de noites no calendário.", "origem: detalhado", _SO_2026, minimo=0),
    _c("minimum_nights_avg_ntm", "float64", "Média do mínimo de noites nos próximos 365 dias.", "origem: detalhado", _SO_2026, minimo=0),
    _c("maximum_nights_avg_ntm", "float64", "Média do máximo de noites nos próximos 365 dias.", "origem: detalhado", _SO_2026, minimo=0),
    # calendario
    _c("has_availability", "boolean", "Anúncio aceita reservas (t/f convertido; `f` em 349 anúncios, 348 deles sem perfil de anfitrião).",
       "origem: detalhado", _SO_2026),
    _c("availability_30", "int64", "Dias livres nos próximos 30.", "origem: detalhado", _SO_2026, minimo=0, maximo=30, aceita_nulo=False),
    _c("availability_60", "int64", "Dias livres nos próximos 60.", "origem: detalhado", _SO_2026, minimo=0, maximo=60, aceita_nulo=False),
    _c("availability_90", "int64", "Dias livres nos próximos 90.", "origem: detalhado", _SO_2026, minimo=0, maximo=90, aceita_nulo=False),
    _c(COL_DISPONIBILIDADE_365, "int64", "Dias livres nos próximos 365. NÃO é ocupação: dia indisponível inclui dia bloqueado pelo anfitrião (invariante 7).",
       "origem: `availability_365`", _TODAS, minimo=0, maximo=365, aceita_nulo=False),
    _c("availability_eoy", "int64", "Dias livres até o fim do ano corrente.", "origem: detalhado", _SO_2026, minimo=0, maximo=366, aceita_nulo=False),
    _c("calendar_last_scraped", "datetime64[ns]", "Data da coleta do calendário.", "origem: detalhado", _SO_2026, aceita_nulo=False),
    # avaliacoes
    _c(COL_N_AVALIACOES, "int64", "Total de avaliações do anúncio desde a criação.", "origem: `number_of_reviews`", _TODAS, minimo=0, aceita_nulo=False),
    _c(COL_N_AVALIACOES_LTM, "int64", "Avaliações nos últimos 12 meses (base da ocupação estimada do Inside Airbnb).",
       "origem: detalhado", _SO_2026, minimo=0, aceita_nulo=False),
    _c("number_of_reviews_l30d", "int64", "Avaliações nos últimos 30 dias.", "origem: detalhado", _SO_2026, minimo=0, aceita_nulo=False),
    _c("number_of_reviews_ly", "int64", "Avaliações no ano-calendário anterior.", "origem: detalhado", _SO_2026, minimo=0, aceita_nulo=False),
    _c(COL_PRIMEIRA_AVALIACAO, "datetime64[ns]", "Data da primeira avaliação (nula ⟺ sem avaliação).", "origem: detalhado", _SO_2026),
    _c(COL_ULTIMA_AVALIACAO, "datetime64[ns]", "Data da avaliação mais recente (nula ⟺ sem avaliação).", "origem: `last_review`", _TODAS),
    _c(COL_AVALIACOES_MES, "float64", "Avaliações por mês do ANÚNCIO: total ÷ meses desde a primeira avaliação, com piso de 1 mês (por isso nunca excede `number_of_reviews`). Nula ⟺ sem avaliação. Ver Q6.",
       "origem: `reviews_per_month`", _TODAS, minimo=0),
    *[
        _c(f"review_scores_{s}", "float64", f"Nota média ({rot}), escala 0–5.", "origem: detalhado", _SO_2026, minimo=0, maximo=5)
        for s, rot in [("rating", "geral"), ("accuracy", "exatidão do anúncio"), ("cleanliness", "limpeza"),
                       ("checkin", "check-in"), ("communication", "comunicação"), ("location", "localização"),
                       ("value", "custo-benefício")]
    ],
    # ocupacao e receita
    _c(COL_OCUPACAO_L365D, "int64", "Noites ocupadas estimadas pelo Inside Airbnb nos últimos 365 dias: min(avaliações_ltm ÷ 0,5 × max(6,4; mínimo de noites); 255). Reproduzida em 99,99% dos anúncios (docs/02).",
       "origem: detalhado", _SO_2026, minimo=0, maximo=365, aceita_nulo=False),
    _c(COL_RECEITA_L365D, "float64", "Receita estimada = `estimated_occupancy_l365d` × `price` (idêntica em 100% dos anúncios com preço). Herda o problema das cotações > 31 noites.",
       "origem: detalhado", _SO_2026, minimo=0),
    _c(COL_OCUPACAO_MODELO, "float64", "Fração do ano ocupada pelo modelo de avaliações do Inside Airbnb aplicado IGUAL aos dois snapshots: avaliações/mês × 12 ÷ 0,5 × max(6,4; mínimo de noites) ÷ 365, teto 0,70; zero se a última avaliação tem mais de 365 dias (ou não existe). É a ocupação comparável 2019 × 2026 (invariante 7).",
       "derivada: `reviews_per_month`, `minimum_nights`, `last_review`", _TODAS, minimo=0, maximo=0.70, aceita_nulo=False),
    # anfitriao
    _c(COL_ANUNCIOS_HOST, "int64", "Anúncios do mesmo anfitrião NESTE scrape de NYC.", "origem: `calculated_host_listings_count`", _TODAS, minimo=1, aceita_nulo=False),
    _c("calculated_host_listings_count_entire_homes", "int64", "Idem, só imóveis inteiros.", "origem: detalhado", _SO_2026, minimo=0, aceita_nulo=False),
    _c("calculated_host_listings_count_private_rooms", "int64", "Idem, só quartos privativos.", "origem: detalhado", _SO_2026, minimo=0, aceita_nulo=False),
    _c("calculated_host_listings_count_shared_rooms", "int64", "Idem, só quartos compartilhados.", "origem: detalhado", _SO_2026, minimo=0, aceita_nulo=False),
    _c(COL_HOST_MULTI, "bool", "Anfitrião com mais de um anúncio no scrape (`calculated_host_listings_count` > 1).",
       "derivada", _TODAS, aceita_nulo=False),
    # regulacao
    _c(COL_LICENCA, "str", "Registro na OSE (Local Law 18) como declarado: \"OSE-STRREG-…\", \"Exempt\" ou vazio. Grafia de caixa variável.",
       "origem: `license` (detalhado)", _SO_2026),
    _c(COL_LICENCA_STATUS, "category", "`registrada` (começa com OSE-STRREG, sem distinguir caixa), `isenta` (Exempt), `ausente` (vazio) ou `outra`.",
       "derivada: `license`", _SO_2026, dominio=LICENCA_STATUS, aceita_nulo=False),
    # celulas H3
    _c(COL_H3_R9, "str", "Célula H3 resolução 9 (~0,105 km², aresta ~174 m) — unidade das features de localização (ADR 0001).",
       "derivada: h3.latlng_to_cell(lat, lon, 9)", _TODAS, aceita_nulo=False),
    _c(COL_H3_R8, "str", "Célula H3 resolução 8 (~0,74 km²) — unidade dos mapas.",
       "derivada: h3.latlng_to_cell(lat, lon, 8)", _TODAS, aceita_nulo=False),
    _c(COL_H3_R6, "str", "Célula H3 resolução 6 (~36 km²) — blocos da validação cruzada espacial (ADR 0002).",
       "derivada: h3.latlng_to_cell(lat, lon, 6)", _TODAS, aceita_nulo=False),
    # tempo
    _c(COL_DIAS_ULTIMA_AVALIACAO, "Int64", "Dias entre a última avaliação e a data do scrape (2019: config.SNAPSHOT_2019; 2026: `last_scraped`). Nulo sem avaliação.",
       "derivada", _TODAS, minimo=0),
    _c(COL_MESES_PRIMEIRA_AVALIACAO, "float64", "Meses (dias ÷ 30,4375) entre a primeira avaliação e `last_scraped`. Nulo sem avaliação.",
       "derivada: `first_review`, `last_scraped`", _SO_2026, minimo=0),
    _c(COL_PRESENTE_2026, "bool", "O id de 2019 ainda aparece no snapshot de 2026 (resumo ou detalhado). Base da análise de sobrevivência.",
       "derivada: cruzamento de ids", (S2019,), aceita_nulo=False),
    # derivadas so de 2026
    _c(COL_BANHEIROS, "float64", "Número de banheiros: `bathrooms` quando existe; senão o número em `bathrooms_text`; \"half-bath\" = 0,5.",
       "derivada: `bathrooms`, `bathrooms_text`", _SO_2026, minimo=0),
    _c(COL_BANHEIRO_COMPARTILHADO, "boolean", "Banheiro compartilhado (\"shared\" no texto). Nulo quando não há texto.",
       "derivada: `bathrooms_text`", _SO_2026),
    _c(COL_N_AMENIDADES, "int64", "Quantidade de itens na lista de comodidades.", "derivada: `amenities`", _SO_2026, minimo=0, aceita_nulo=False),
    *[
        _c(nome, "bool", f"Comodidade: {rotulo}. Expressão regular sobre cada item da lista em `schema.AMENIDADES`.",
           "derivada: `amenities`", _SO_2026, aceita_nulo=False)
        for nome, (_padrao, rotulo) in AMENIDADES.items()
    ],
    _c(COL_HOST_SUPERHOST, "bool", "Superhost, com nulo tratado como False (os 349 anúncios sem perfil não podem ter o selo verificado).",
       "derivada: `host_is_superhost`", _SO_2026, aceita_nulo=False),
    _c(COL_HOST_ANOS, "float64", "Anos como anfitrião: `hosts_time_as_host_years` + meses/12. (`host_since` veio 100% vazio neste snapshot.)",
       "derivada", _SO_2026, minimo=0),
    _c(COL_TIPO_IMOVEL_GRUPO, "category", "`property_type` em 7 grupos: apartamento/casa inteira, quarto em apartamento/casa, hotel ou pousada, quarto compartilhado, atípico (barco, trailer, torre...). Regra em clean/derivadas.py.",
       "derivada: `property_type`", _SO_2026, dominio=TIPOS_IMOVEL, aceita_nulo=False),
]

ESQUEMA: dict[str, Coluna] = {c.nome: c for c in _ESQ}
assert len(ESQUEMA) == len(_ESQ), "nome de coluna repetido no contrato"

#: Ordem das colunas em cada parquet. Explicita porque e contrato: o modulo a
#: jusante que depende de posicao (exportacao para o site) nao pode ver a ordem
#: mudar porque alguem reordenou a lista acima.
_ORDEM_RESUMO = [
    COL_SNAPSHOT, COL_ID, COL_HOST_ID, COL_DISTRITO, COL_BAIRRO, COL_LAT, COL_LON,
    COL_ROOM_TYPE, COL_PRECO, COL_MIN_NOITES, COL_N_AVALIACOES, COL_ULTIMA_AVALIACAO,
    COL_AVALIACOES_MES, COL_ANUNCIOS_HOST, COL_DISPONIBILIDADE_365,
    COL_PRECO_VALIDO, COL_MIN30, COL_HOST_MULTI, COL_H3_R9, COL_H3_R8, COL_H3_R6,
    COL_OCUPACAO_MODELO, COL_DIAS_ULTIMA_AVALIACAO,
]
_ORDEM_2019 = [
    COL_SNAPSHOT, COL_ID, COL_NOME, COL_HOST_ID, COL_DISTRITO, COL_BAIRRO, COL_LAT, COL_LON,
    COL_ROOM_TYPE, COL_PRECO, COL_MIN_NOITES, COL_N_AVALIACOES, COL_ULTIMA_AVALIACAO,
    COL_AVALIACOES_MES, COL_ANUNCIOS_HOST, COL_DISPONIBILIDADE_365,
    COL_PRECO_VALIDO, COL_MIN30, COL_HOST_MULTI, COL_H3_R9, COL_H3_R8, COL_H3_R6,
    COL_OCUPACAO_MODELO, COL_DIAS_ULTIMA_AVALIACAO, COL_PRESENTE_2026,
]
_ORDEM_2026 = [c.nome for c in _ESQ if S2026 in c.saidas]

ORDEM: dict[str, list[str]] = {S2019: _ORDEM_2019, S2026: _ORDEM_2026, SRESUMO: _ORDEM_RESUMO}

for _s, _cols in ORDEM.items():
    _declaradas = {c.nome for c in _ESQ if _s in c.saidas}
    assert set(_cols) == _declaradas, f"ORDEM[{_s}] diverge de Coluna.saidas: {set(_cols) ^ _declaradas}"


def colunas(saida: str) -> list[str]:
    """Colunas de um parquet da silver, na ordem do contrato."""
    return list(ORDEM[saida])


def tipos(saida: str) -> dict[str, str]:
    """dtype pandas de cada coluna do parquet."""
    return {n: ESQUEMA[n].dtype for n in ORDEM[saida]}


COLUNAS_PESSOAIS_SILVER = frozenset(c.nome for c in _ESQ if c.pessoal)


# --- colunas brutas ------------------------------------------------------------------------

_M, _R, _D, _X, _REF = "mantida", "renomeada", "derivada", "descartada", "referencia"
_VAZIA = "100% nula neste snapshot"


def _b(arquivo, nome, dtype, descricao, tratamento, destino="", pessoal=False, motivo="") -> ColunaBruta:
    return ColunaBruta(arquivo, nome, dtype, descricao, tratamento, destino, pessoal, motivo)


_K = KAGGLE_2019
_BRUTAS_KAGGLE = [
    _b(_K, "id", "int64", "Id do anúncio.", _M, pessoal=True),
    _b(_K, "name", "texto", "Título do anúncio (16 nulos).", _M, pessoal=True),
    _b(_K, "host_id", "int64", "Id do anfitrião.", _M, pessoal=True),
    _b(_K, "host_name", "texto", "Primeiro nome do anfitrião (21 nulos).", _X, pessoal=True,
       motivo="dado pessoal (invariante 9) e inútil como chave: homônimos entre anfitriões (Q3)"),
    _b(_K, "neighbourhood_group", "texto", "Distrito.", _M),
    _b(_K, "neighbourhood", "texto", "Bairro.", _M),
    _b(_K, "latitude", "float64", "Latitude.", _M),
    _b(_K, "longitude", "float64", "Longitude.", _M),
    _b(_K, "room_type", "texto", "Tipo de acomodação (3 valores).", _M),
    _b(_K, "price", "int64", "Diária em US$ (inteiro).", _R, destino=COL_PRECO),
    _b(_K, "minimum_nights", "int64", "Mínimo de noites.", _M),
    _b(_K, "number_of_reviews", "int64", "Total de avaliações.", _M),
    _b(_K, "last_review", "texto (data)", "Última avaliação (10.052 nulos).", _M),
    _b(_K, "reviews_per_month", "float64", "Avaliações por mês (10.052 nulos).", _M),
    _b(_K, "calculated_host_listings_count", "int64", "Anúncios do anfitrião no scrape.", _M),
    _b(_K, "availability_365", "int64", "Dias livres nos próximos 365.", _M),
]

_RS = RESUMO_2026
_MOT_RESUMO = ("conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos "
               "(preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1")
_BRUTAS_RESUMO = [
    _b(_RS, n, t, d, _REF, pessoal=p, motivo=_MOT_RESUMO)
    for n, t, d, p in [
        ("id", "int64", "Id do anúncio.", True),
        ("name", "texto", "Título (quebras de linha preservadas, ao contrário do detalhado).", True),
        ("host_id", "float64", "Id do anfitrião (296 nulos).", True),
        ("host_profile_id", "float64", "Id do perfil do anfitrião.", True),
        ("host_name", "texto", "Nome do anfitrião.", True),
        ("neighbourhood_group", "texto", "Distrito.", False),
        ("neighbourhood", "texto", "Bairro.", False),
        ("latitude", "float64", "Latitude.", False),
        ("longitude", "float64", "Longitude.", False),
        ("room_type", "texto", "Tipo de acomodação.", False),
        ("price", "float64", "Preço arredondado ao dólar.", False),
        ("minimum_nights", "float64", "Mínimo de noites.", False),
        ("number_of_reviews", "int64", "Total de avaliações.", False),
        ("last_review", "texto (data)", "Última avaliação.", False),
        ("reviews_per_month", "float64", "Avaliações por mês.", False),
        ("calculated_host_listings_count", "float64", "Anúncios do anfitrião.", False),
        ("availability_365", "int64", "Dias livres nos próximos 365.", False),
        ("number_of_reviews_ltm", "int64", "Avaliações nos últimos 12 meses.", False),
        ("license", "texto", "Registro OSE.", False),
    ]
]

_DT = DETALHADO_2026
_BRUTAS_DETALHADO = [
    _b(_DT, "id", "int64", "Id do anúncio.", _M, pessoal=True),
    _b(_DT, "listing_url", "texto", "URL do anúncio.", _X, pessoal=True, motivo="URL leva ao anúncio e ao anfitrião (invariante 9)"),
    _b(_DT, "scrape_id", "int64", "Id da coleta.", _X, motivo="constante (20260614073253)"),
    _b(_DT, "last_scraped", "texto (data)", "Data da coleta.", _M),
    _b(_DT, "source", "texto", "Origem no scrape.", _M),
    _b(_DT, "name", "texto", "Título.", _M, pessoal=True),
    _b(_DT, "description", "texto", "Descrição livre do anúncio.", _X, pessoal=True,
       motivo="texto livre do anfitrião (pode conter nome, telefone, endereço)"),
    _b(_DT, "neighborhood_overview", "texto", "Texto do anfitrião sobre o bairro.", _X, pessoal=True, motivo=_VAZIA),
    _b(_DT, "picture_url", "texto", "Foto do anúncio.", _X, pessoal=True, motivo="foto (invariante 9)"),
    _b(_DT, "host_id", "int64", "Id do anfitrião.", _M, pessoal=True),
    _b(_DT, "host_url", "texto", "URL do perfil.", _X, pessoal=True, motivo="URL de perfil (invariante 9)"),
    _b(_DT, "host_profile_id", "float64", "Id do perfil novo do anfitrião.", _X, pessoal=True, motivo="identificador pessoal redundante com host_id"),
    _b(_DT, "host_profile_url", "texto", "URL do perfil novo.", _X, pessoal=True, motivo="URL de perfil (invariante 9)"),
    _b(_DT, "host_name", "texto", "Nome do anfitrião.", _X, pessoal=True, motivo="dado pessoal (invariante 9); homônimos (Q3)"),
    _b(_DT, "host_since", "texto (data)", "Data de início como anfitrião.", _X, motivo=f"{_VAZIA}; substituída por hosts_time_as_host_*"),
    _b(_DT, "hosts_time_as_user_years", "float64", "Anos de conta.", _M),
    _b(_DT, "hosts_time_as_user_months", "float64", "Meses além dos anos de conta.", _M),
    _b(_DT, "hosts_time_as_host_years", "float64", "Anos como anfitrião.", _M),
    _b(_DT, "hosts_time_as_host_months", "float64", "Meses além dos anos como anfitrião.", _M),
    _b(_DT, "host_location", "texto", "Onde o anfitrião diz morar.", _X, pessoal=True, motivo="localização pessoal do anfitrião, texto livre"),
    _b(_DT, "host_about", "texto", "Texto do anfitrião sobre si.", _X, pessoal=True, motivo="texto pessoal (invariante 9)"),
    _b(_DT, "host_response_time", "texto", "Tempo de resposta.", _X, motivo=_VAZIA),
    _b(_DT, "host_response_rate", "texto (%)", "Taxa de resposta.", _X, motivo=f"{_VAZIA} — a taxa numérica pedida não pode ser derivada"),
    _b(_DT, "host_acceptance_rate", "texto (%)", "Taxa de aceitação.", _X, motivo=f"{_VAZIA} — idem"),
    _b(_DT, "host_is_superhost", "t/f", "Superhost.", _M, motivo="tipada como booleana; alimenta host_superhost"),
    _b(_DT, "host_thumbnail_url", "texto", "Miniatura da foto do anfitrião.", _X, pessoal=True, motivo=f"foto; {_VAZIA}"),
    _b(_DT, "host_picture_url", "texto", "Foto do anfitrião.", _X, pessoal=True, motivo="foto (invariante 9)"),
    _b(_DT, "host_neighbourhood", "texto", "Bairro do anfitrião.", _X, pessoal=True, motivo=_VAZIA),
    _b(_DT, "host_listings_count", "float64", "Anúncios do perfil.", _M),
    _b(_DT, "host_total_listings_count", "float64", "Anúncios totais do perfil.", _X, motivo=_VAZIA),
    _b(_DT, "host_verifications", "texto", "Meios de verificação.", _X, motivo=_VAZIA),
    _b(_DT, "host_has_profile_pic", "t/f", "Tem foto de perfil.", _M),
    _b(_DT, "host_identity_verified", "t/f", "Identidade verificada.", _M),
    _b(_DT, "neighbourhood", "texto", "Bairro em texto livre.", _X, motivo=f"{_VAZIA}; usar neighbourhood_cleansed"),
    _b(_DT, "neighbourhood_cleansed", "texto", "Bairro pela coordenada.", _M),
    _b(_DT, "neighbourhood_group_cleansed", "texto", "Distrito pela coordenada.", _M),
    _b(_DT, "latitude", "float64", "Latitude.", _M),
    _b(_DT, "longitude", "float64", "Longitude.", _M),
    _b(_DT, "property_type", "texto", "Tipo de imóvel.", _M),
    _b(_DT, "room_type", "texto", "Tipo de acomodação (4 valores).", _M),
    _b(_DT, "accommodates", "int64", "Hóspedes.", _M),
    _b(_DT, "bathrooms", "float64", "Banheiros.", _M),
    _b(_DT, "bathrooms_text", "texto", "Banheiros em texto.", _M),
    _b(_DT, "bedrooms", "float64", "Quartos.", _M),
    _b(_DT, "beds", "float64", "Camas.", _M),
    _b(_DT, "amenities", "texto (JSON)", "Comodidades.", _M),
    _b(_DT, "price", "texto", "Preço \"$1,234.00\" (28,9% nulo).", _R, destino=COL_PRECO),
    _b(_DT, "price_quote_checkin_date", "texto (data)", "Check-in da cotação.", _M),
    _b(_DT, "price_quote_checkout_date", "texto (data)", "Check-out da cotação.", _M),
    _b(_DT, "price_quote_total_price", "float64", "Total da cotação.", _M),
    _b(_DT, "price_quote_price_per_night", "float64", "Total ÷ noites.", _X,
       motivo="idêntica a price em 100% das linhas com ambos (21.514); preco já a representa"),
    _b(_DT, "price_quote_raw", "texto (JSON)", "Resposta bruta da cotação.", _D,
       destino=f"{COL_PRECO_CHEIO}, {COL_DESCONTO_PCT}", motivo="JSON bruto; os campos úteis viram derivadas"),
    *[_b(_DT, n, "float64", d, _M) for n, d in [
        ("minimum_nights", "Mínimo de noites (2 nulos)."), ("maximum_nights", "Máximo de noites."),
        ("minimum_minimum_nights", "Menor mínimo."), ("maximum_minimum_nights", "Maior mínimo."),
        ("minimum_maximum_nights", "Menor máximo."), ("maximum_maximum_nights", "Maior máximo."),
        ("minimum_nights_avg_ntm", "Mínimo médio."), ("maximum_nights_avg_ntm", "Máximo médio."),
    ]],
    _b(_DT, "calendar_updated", "texto", "Última atualização do calendário.", _X, motivo=_VAZIA),
    _b(_DT, "has_availability", "t/f", "Aceita reservas.", _M),
    *[_b(_DT, n, "int64", d, _M) for n, d in [
        ("availability_30", "Dias livres em 30."), ("availability_60", "Dias livres em 60."),
        ("availability_90", "Dias livres em 90."), ("availability_365", "Dias livres em 365."),
    ]],
    _b(_DT, "calendar_last_scraped", "texto (data)", "Coleta do calendário.", _M),
    *[_b(_DT, n, "int64", d, _M) for n, d in [
        ("number_of_reviews", "Total de avaliações."), ("number_of_reviews_ltm", "Avaliações em 12 meses."),
        ("number_of_reviews_l30d", "Avaliações em 30 dias."), ("availability_eoy", "Dias livres até o fim do ano."),
        ("number_of_reviews_ly", "Avaliações no ano anterior."),
        ("estimated_occupancy_l365d", "Ocupação estimada (noites)."),
    ]],
    _b(_DT, "estimated_revenue_l365d", "float64", "Receita estimada.", _M),
    _b(_DT, "first_review", "texto (data)", "Primeira avaliação.", _M),
    _b(_DT, "last_review", "texto (data)", "Última avaliação.", _M),
    *[_b(_DT, f"review_scores_{s}", "float64", "Nota média 0–5.", _M)
      for s in ("rating", "accuracy", "cleanliness", "checkin", "communication", "location", "value")],
    _b(_DT, "license", "texto", "Registro OSE.", _M),
    _b(_DT, "instant_bookable", "t/f", "Reserva instantânea.", _X, motivo=_VAZIA),
    *[_b(_DT, n, "int64", "Contagem de anúncios do anfitrião no scrape.", _M) for n in (
        "calculated_host_listings_count", "calculated_host_listings_count_entire_homes",
        "calculated_host_listings_count_private_rooms", "calculated_host_listings_count_shared_rooms")],
    _b(_DT, "reviews_per_month", "float64", "Avaliações por mês.", _M),
]

BRUTAS: dict[tuple[str, str], ColunaBruta] = {
    (b.arquivo, b.nome): b for b in _BRUTAS_KAGGLE + _BRUTAS_RESUMO + _BRUTAS_DETALHADO
}

#: Colunas brutas que NUNCA podem aparecer em parquet algum da silver. Os testes
#: conferem o parquet real contra esta lista — e a trava do invariante 9 na origem.
PROIBIDAS_NA_SILVER = frozenset(
    b.nome for b in BRUTAS.values()
    if b.pessoal and b.tratamento == _X
) | {"listing_url", "picture_url", "host_url", "host_profile_url", "host_profile_id",
     "host_name", "host_about", "host_picture_url", "host_thumbnail_url", "host_location",
     "host_neighbourhood", "description", "neighborhood_overview"}


def brutas(arquivo: str) -> list[ColunaBruta]:
    """Colunas de um arquivo de origem, na ordem em que aparecem nele."""
    return [b for b in BRUTAS.values() if b.arquivo == arquivo]


# --- validacao --------------------------------------------------------------------------------


def _dtype_confere(s: pd.Series, esperado: str) -> bool:
    if esperado == "str":
        return pd.api.types.is_string_dtype(s.dtype) and not isinstance(s.dtype, pd.CategoricalDtype)
    if esperado == "category":
        return isinstance(s.dtype, pd.CategoricalDtype)
    if esperado.startswith("datetime64"):
        return pd.api.types.is_datetime64_dtype(s.dtype)
    return str(s.dtype) == esperado


def validar(df: pd.DataFrame, saida: str) -> list[str]:
    """Confere o DataFrame contra o contrato; devolve as violacoes (vazio = ok).

    Nao conserta nada: coluna faltando, dtype trocado, valor fora do dominio ou
    nulo onde o contrato proibe sao erro de pipeline, nao de dado — a linha
    ruim ja deveria ter ido para a quarentena antes daqui.
    """
    erros: list[str] = []
    esperadas = colunas(saida)
    if list(df.columns) != esperadas:
        faltam = [c for c in esperadas if c not in df.columns]
        sobram = [c for c in df.columns if c not in esperadas]
        erros.append(f"{saida}: colunas divergem do contrato (faltam {faltam}, sobram {sobram}"
                     f"{', ordem diferente' if not faltam and not sobram else ''})")
    proibidas = PROIBIDAS_NA_SILVER & set(df.columns)
    if proibidas:
        erros.append(f"{saida}: coluna pessoal na silver: {sorted(proibidas)}")
    for nome in esperadas:
        if nome not in df.columns:
            continue
        meta, s = ESQUEMA[nome], df[nome]
        if not _dtype_confere(s, meta.dtype):
            erros.append(f"{saida}.{nome}: dtype {s.dtype}, contrato {meta.dtype}")
            continue
        if not meta.aceita_nulo and s.isna().any():
            erros.append(f"{saida}.{nome}: {int(s.isna().sum())} nulos, contrato proibe")
        v = s.dropna()
        if meta.dominio is not None and len(v):
            fora = set(v.astype(str).unique()) - {str(x) for x in meta.dominio}
            if fora:
                erros.append(f"{saida}.{nome}: fora do dominio {sorted(fora)[:5]}")
        if len(v) and (meta.minimo is not None or meta.maximo is not None) and meta.dtype not in ("str", "category"):
            num = pd.to_numeric(v, errors="coerce")
            if meta.minimo is not None and (num < meta.minimo).any():
                erros.append(f"{saida}.{nome}: {int((num < meta.minimo).sum())} valores < {meta.minimo}")
            if meta.maximo is not None and (num > meta.maximo).any():
                erros.append(f"{saida}.{nome}: {int((num > meta.maximo).sum())} valores > {meta.maximo}")
    return erros


# --- dicionario (docs/dicionario-dados.md e gerado daqui) --------------------------------------

_ROTULO_SAIDA = {S2019: "2019", S2026: "2026", SRESUMO: "resumo"}
_ROTULO_ARQUIVO = {
    KAGGLE_2019: "Kaggle 2019 — `AB_NYC_2019.csv`",
    RESUMO_2026: f"Inside Airbnb {config.SNAPSHOT_ATUAL} — resumo (`visualisations/listings.csv`)",
    DETALHADO_2026: f"Inside Airbnb {config.SNAPSHOT_ATUAL} — detalhado (`data/listings.csv.gz`)",
}


def _dominio_md(c: Coluna) -> str:
    partes = []
    if c.dominio is not None:
        partes.append(", ".join(f"`{x}`" for x in c.dominio))
    if c.minimo is not None or c.maximo is not None:
        lo = "" if c.minimo is None else f"{c.minimo:g}"
        hi = "" if c.maximo is None else f"{c.maximo:g}"
        partes.append(f"[{lo}, {hi}]")
    if not c.aceita_nulo:
        partes.append("sem nulo")
    return "; ".join(partes) or "—"


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def dicionario_markdown() -> str:
    """Dicionario de dados em Markdown — o arquivo docs/dicionario-dados.md e isto."""
    L = [
        "# Dicionário de dados",
        "",
        "!!! note \"Gerado, não editado\"",
        "    Este arquivo é a saída de `python -m airbnb.schema --escrever`. A fonte é",
        "    `src/airbnb/schema.py` (invariante 1). Editar aqui é perder a edição na próxima geração.",
        "",
        "**Pessoal** = nunca sai para site nem relatório (invariante 9). Colunas pessoais que a",
        "análise precisa (ids, título) ficam na silver com a flag; as demais são descartadas na limpeza.",
        "",
        "## 1. Contrato da silver (`data/processed/`)",
        "",
        "| parquet | linhas | conteúdo |",
        "|---|---|---|",
        "| `anuncios_2019.parquet` | Kaggle limpo | 2019, sem `host_name` |",
        "| `anuncios_2026.parquet` | detalhado limpo | 2026, sem colunas pessoais/texto livre (exceto `name`) |",
        "| `anuncios_resumo.parquet` | os dois empilhados | colunas comuns + `snapshot` |",
        "",
        "| coluna | dtype | em | domínio | pessoal | descrição | origem |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in _ESQ:
        em = ", ".join(_ROTULO_SAIDA[s] for s in SAIDAS if s in c.saidas)
        L.append(f"| `{c.nome}` | {c.dtype} | {em} | {_celula(_dominio_md(c))} | "
                 f"{'**sim**' if c.pessoal else ''} | {_celula(c.descricao)} | {_celula(c.origem)} |")
    L += ["", "## 2. Colunas de origem e o que a limpeza faz com cada uma", ""]
    for arq in (KAGGLE_2019, DETALHADO_2026, RESUMO_2026):
        L += [f"### {_ROTULO_ARQUIVO[arq]}", "",
              "| coluna | tipo bruto | descrição | tratamento | pessoal | motivo |",
              "|---|---|---|---|---|---|"]
        for b in brutas(arq):
            trat = b.tratamento + (f" → `{b.destino}`" if b.destino else "")
            L.append(f"| `{b.nome}` | {b.dtype} | {_celula(b.descricao)} | {trat} | "
                     f"{'**sim**' if b.pessoal else ''} | {_celula(b.motivo)} |")
        L.append("")
    L += [
        "## 3. Quarentena (`data/processed/quarentena.parquet`)",
        "",
        "| coluna | descrição |",
        "|---|---|",
        "| `snapshot` | \"2019\" ou \"2026\" |",
        "| `id` | id do anúncio (pessoal — não publicar) |",
        "| `regra` | código da regra (B01…, P01…) |",
        "| `motivo` | texto da regra |",
        "| `escopo` | `base` (a linha sai de tudo) ou `preco` (a linha fica, mas sai das análises de preço) |",
        "",
        "Regras, contagens e cascata em `data/processed/_qualidade.json` e em",
        "[Preparação dos dados](04-preparacao-dos-dados.md).",
        "",
    ]
    return "\n".join(L)


def main() -> None:
    """Imprime o dicionario ou grava docs/dicionario-dados.md."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--escrever", action="store_true", help="grava docs/dicionario-dados.md")
    args = ap.parse_args()
    texto = dicionario_markdown()
    if args.escrever:
        destino = config.DOCS / "dicionario-dados.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        print(f"gravado {destino.relative_to(config.RAIZ)} ({len(ESQUEMA)} colunas na silver, "
              f"{len(BRUTAS)} colunas de origem)")
    else:
        print(texto)


if __name__ == "__main__":
    main()
