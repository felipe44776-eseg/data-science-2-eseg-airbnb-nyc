"""Rotulos de exibicao em portugues para valores categoricos do dado.

O dado guarda o valor da origem ("Entire home/apt") — e o que liga a linha ao
dicionario do Inside Airbnb. Superficie publicada (site, docs, figuras) mostra o
rotulo daqui; nenhuma outra traducao e escrita a mao.
"""

from __future__ import annotations

from airbnb import schema as S

TIPO_QUARTO_PT: dict[str, str] = dict(zip(S.ROOM_TYPES, (
    "Casa ou apê inteiro", "Quarto privativo", "Quarto compartilhado", "Quarto de hotel"),
    strict=True))


def tipo(valor: str) -> str:
    """Rotulo em portugues de um room_type; valor desconhecido passa como veio."""
    return TIPO_QUARTO_PT.get(str(valor), str(valor))


#: Nome legivel de cada feature dos modelos do produto (o site mostra no
#: "como chegamos nesse numero?"). Feature sem rotulo aparece com o nome cru.
FEATURE_PT: dict[str, str] = {
    "room_type_cod": "Tipo de acomodação",
    "accommodates": "Hóspedes",
    "bedrooms": "Quartos",
    "beds": "Camas",
    S.COL_BANHEIROS: "Banheiros",
    S.COL_BANHEIRO_COMPARTILHADO: "Banheiro compartilhado",
    S.COL_MIN30: "Mínimo de 30 noites",
    S.COL_HOST_SUPERHOST: "Superhost",
    "review_scores_rating": "Nota média",
    "lat": "Latitude do lugar",
    "lon": "Longitude do lugar",
    "distrito_cod": "Distrito",
    "acs_renda_mediana": "Renda domiciliar mediana do entorno (Census)",
    "acs_aluguel_mediano": "Aluguel mediano do setor censitário (Census)",
    "acs_pop_densidade": "Densidade populacional",
    "acs_pct_alugado": "Domicílios de aluguel",
    "acs_pct_vago": "Unidades vagas",
    "acs_valor_imovel": "Valor mediano dos imóveis (Census)",
    "crime_graves_km2": "Crimes graves por km² (delegacia)",
    "crime_total_km2": "Queixas criminais por km² (delegacia)",
    "ruido_311_km2": "Reclamações de barulho ao 311 por km²",
    "zori": "Aluguel de longo prazo do CEP (Zillow)",
    "metro_dist_m": "Distância ao metrô",
    "metro_n_800m": "Estações de metrô a até 800 m",
    "metro_linhas_800m": "Linhas de metrô a até 800 m",
    "poi_restaurantes_k1": "Restaurantes no entorno",
    "poi_bares_k1": "Bares no entorno",
    "poi_cafes_k1": "Cafés no entorno",
    "poi_atracoes_k1": "Atrações e museus no entorno",
    "poi_hoteis_k1": "Hotéis no entorno",
    "poi_parques_k1": "Parques no entorno",
    "dist_centro_km": "Distância a Times Square",
    "dist_aeroporto_km": "Distância ao aeroporto",
    "dist_marco_km": "Distância ao marco turístico mais próximo",
}
