"""Testes da limpeza (clean/) com frames sinteticos — rodam sem o dado real.

O que cada teste trava:
  * parse de preco, banheiros, amenidades, licenca e cotacao (price_quote_raw);
  * quarentena: toda exclusao tem regra, motivo e escopo, e a cascata fecha;
  * `preco` (escopo) nao tira a linha da base; `base` tira;
  * idempotencia: mesma entrada, mesmo resultado;
  * NENHUMA coluna pessoal nas saidas (invariante 9).
Os testes marcados `dados` leem os parquets reais e sao pulados sem eles.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from airbnb import config, schema
from airbnb.clean import derivadas as dv
from airbnb.clean import pipeline as pl
from airbnb.clean import regras

BAIRROS = frozenset({"Harlem", "Williamsburg", "Astoria"})


# --- preco ------------------------------------------------------------------------------------


def test_parse_preco_texto_numero_e_invalido():
    s = pd.Series(["$1,234.00", "$52.00", None, "abc", "$0.00", " $10,000.50 "])
    out = dv.parse_preco(s)
    assert out.tolist()[:2] == [1234.0, 52.0]
    assert np.isnan(out[2]) and np.isnan(out[3])
    assert out[4] == 0.0 and out[5] == 10000.5
    assert dv.parse_preco(pd.Series([149, 0])).tolist() == [149.0, 0.0]


# --- cotacao (price_quote_raw) ------------------------------------------------------------------


def _cotacao_json(total, itens, is_available=True):
    return json.dumps({"quote": {"total_price": None if total is None else str(total),
                                 "is_available": is_available,
                                 "raw_price_line_items": itens}})


COM_DESCONTO = _cotacao_json("3419.19", [
    {"amount": "10398.19", "item_type": "other", "description": "Average monthly price"},
    {"amount": "-6979.00", "item_type": "discount_amount", "description": "Monthly stay discount"},
    {"amount": "3419.19", "item_type": "discounted_subtotal", "description": "Price after discount"},
])
SEM_DESCONTO = _cotacao_json("453.00", [
    {"amount": "453.00", "item_type": "nightly_subtotal", "description": "3 nights x $151.00"},
    {"amount": "453.00", "item_type": "discounted_subtotal", "description": "Price after discount"},
])
POUPANCA_AIRBNB = _cotacao_json("3804.30", [
    {"amount": "4113.27", "item_type": "other", "description": "Average monthly price"},
    {"amount": "-308.97", "item_type": "other", "description": "Airbnb monthly stay savings"},
    {"amount": "3804.30", "item_type": "discounted_subtotal", "description": "Price after discount"},
])
INDISPONIVEL = _cotacao_json(None, [], is_available=False)


def test_cotacao_com_e_sem_desconto_malformada_e_ausente():
    raw = pd.Series([COM_DESCONTO, SEM_DESCONTO, POUPANCA_AIRBNB, "{ nao e json", None, INDISPONIVEL])
    ci = pd.Series(["2026-07-11", "2026-07-01", "2026-06-23", "2026-07-01", None, "2026-07-01"])
    co = pd.Series(["2026-08-10", "2026-07-04", "2026-07-23", "2026-07-31", None, "2026-07-31"])
    c = dv.cotacao(raw, ci, co)
    assert c["preco_cotacao_noites"].tolist()[:4] == [30, 3, 30, 30]
    assert pd.isna(c["preco_cotacao_noites"][4])
    # com desconto: diaria cheia = "Average monthly price" / 30; desconto = 6979 / 10398,19
    assert c["preco_cheio"][0] == pytest.approx(10398.19 / 30)
    assert c["desconto_pct"][0] == pytest.approx(6979.00 / 10398.19)
    # sem item de desconto: 0, nao nulo
    assert c["preco_cheio"][1] == pytest.approx(151.0)
    assert c["desconto_pct"][1] == 0.0
    # "Airbnb monthly stay savings" e item 'other' negativo: tambem e desconto
    assert c["desconto_pct"][2] == pytest.approx(308.97 / 4113.27)
    # JSON malformado, sem cotacao e cotacao sem valor -> NaN
    for i in (3, 4, 5):
        assert np.isnan(c["preco_cheio"][i]) and np.isnan(c["desconto_pct"][i])


# --- banheiros --------------------------------------------------------------------------------------


def test_parse_banheiros():
    texto = pd.Series(["1.5 shared baths", "Half-bath", "Shared half-bath", "2 baths", None,
                       "0 shared baths", "1 private bath"])
    numero = pd.Series([np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 1.0])
    b = dv.banheiros(numero, texto)
    assert b["banheiros"].tolist()[:4] == [1.5, 0.5, 0.5, 2.0]
    assert np.isnan(b["banheiros"][4])
    assert b["banheiros"][5] == 0.0 and b["banheiros"][6] == 1.0
    comp = b["banheiro_compartilhado"]
    assert comp.dtype == "boolean"
    assert comp.tolist()[:4] == [True, False, True, False]
    assert pd.isna(comp[4])
    assert comp[5] and not comp[6]


def test_banheiros_prefere_o_numero_quando_existe():
    b = dv.banheiros(pd.Series([3.0]), pd.Series(["2 baths"]))
    assert b["banheiros"][0] == 3.0


# --- amenidades --------------------------------------------------------------------------------------


def test_amenidades_string_json_e_malformada():
    s = pd.Series([
        '["Wifi", "Kitchen", "Hair dryer", "Free washer \\u2013 In unit", "Pool table"]',
        '["Dishwasher", "Paid dryer \\u2013 In building", "Shared gym nearby"]',
        "[]",
        "nao e json",
    ])
    out, invalidas = dv.amenidades(s)
    assert invalidas == 1
    assert out["n_amenidades"].tolist() == [5, 3, 0, 0]
    assert out.loc[0, ["amen_wifi", "amen_cozinha", "amen_lavadora"]].all()
    assert not out.loc[0, ["amen_secadora", "amen_piscina"]].any()
    assert out.loc[1, "amen_lava_loucas"] and out.loc[1, "amen_secadora"]
    assert not out.loc[1, "amen_lavadora"] and not out.loc[1, "amen_academia"]
    assert not out.loc[[2, 3], schema.COLS_AMENIDADES].any().any()
    assert set(schema.COLS_AMENIDADES) <= set(out.columns)


# --- licenca, tipo de imovel, ocupacao --------------------------------------------------------------------


def test_licenca_status():
    s = pd.Series(["OSE-STRREG-0001234", "ose-strreg-0000823", "Exempt", None, "", "12345"])
    assert dv.licenca_status(s).astype(str).tolist() == [
        "registrada", "registrada", "isenta", "ausente", "ausente", "outra"]


@pytest.mark.parametrize(("prop", "room", "grupo"), [
    ("Entire rental unit", "Entire home/apt", "apartamento_inteiro"),
    ("Entire condo", "Entire home/apt", "apartamento_inteiro"),
    ("Entire townhouse", "Entire home/apt", "casa_inteira"),
    ("Entire guest suite", "Entire home/apt", "casa_inteira"),
    ("Private room in rental unit", "Private room", "quarto_em_apartamento"),
    ("Private room in home", "Private room", "quarto_em_casa"),
    ("Private room in houseboat", "Private room", "atipico"),
    ("Room in hotel", "Hotel room", "hotel_pousada"),
    ("Private room in hostel", "Private room", "hotel_pousada"),
    ("Shared room in rental unit", "Shared room", "quarto_compartilhado"),
    ("Camper/RV", "Entire home/apt", "atipico"),
    ("Tiny home", "Entire home/apt", "casa_inteira"),
    ("Algo novo", "Private room", "quarto_em_casa"),
])
def test_tipo_imovel_grupo(prop, room, grupo):
    assert str(dv.tipo_imovel_grupo(pd.Series([prop]), pd.Series([room]))[0]) == grupo


def test_ocupacao_modelo():
    rpm = pd.Series([1.0, 1.0, 1.0, np.nan, 5.0])
    minimo = pd.Series([1, 30, 1, 1, 1])
    dias = pd.Series([10, 10, 400, pd.NA, 10], dtype="Int64")
    occ = dv.ocupacao_modelo(rpm, minimo, dias)
    assert occ[0] == pytest.approx(1 / 0.5 * 12 * 6.4 / 365)
    assert occ[1] == dv.TETO_OCUPACAO           # 2 reservas x 30 noites/mes -> teto
    assert occ[2] == 0.0                          # sem avaliacao em 365 dias
    assert occ[3] == 0.0                          # sem avaliacao
    assert occ[4] == dv.TETO_OCUPACAO
    sem_janela = dv.ocupacao_modelo(rpm, minimo, dias, janela=None)
    assert sem_janela[2] == pytest.approx(occ[0])


# --- frames sinteticos no formato das origens ---------------------------------------------------------------


def _kaggle(n: int = 8) -> pd.DataFrame:
    df = pd.DataFrame({
        "id": np.arange(1, n + 1),
        "name": [f"Quarto {i}" for i in range(n)],
        "host_id": [10, 10, 11, 12, 13, 14, 15, 16][:n],
        "host_name": ["Ana"] * n,
        "neighbourhood_group": ["Manhattan"] * n,
        "neighbourhood": ["Harlem"] * n,
        "latitude": [40.81] * n,
        "longitude": np.linspace(-73.95, -73.93, n),
        "room_type": ["Private room"] * n,
        "price": [100] * n,
        "minimum_nights": [2] * n,
        "number_of_reviews": [3] * n,
        "last_review": ["2019-06-01"] * n,
        "reviews_per_month": [0.5] * n,
        "calculated_host_listings_count": [2, 2, 1, 1, 1, 1, 1, 1][:n],
        "availability_365": [100] * n,
    })
    df.loc[1, "name"] = None           # name nulo nao tira a linha (correcao c da v0)
    df.loc[2, "price"] = 0             # escopo preco
    df.loc[3, "latitude"] = 10.0       # fora de NYC -> base
    df.loc[4, "neighbourhood"] = "Atlantida"  # bairro desconhecido -> base
    df.loc[5, ["number_of_reviews", "last_review", "reviews_per_month"]] = [0, None, None]
    df.loc[7, "id"] = 1                # id repetido -> base
    return df


def _detalhado(n: int = 6) -> pd.DataFrame:
    cols = [b.nome for b in schema.brutas(schema.DETALHADO_2026)]
    df = pd.DataFrame({c: [np.nan] * n for c in cols})
    raw_30 = COM_DESCONTO
    valores = {
        "id": np.arange(101, 101 + n), "listing_url": [f"https://www.airbnb.com/rooms/{i}" for i in range(n)],
        "scrape_id": 1, "last_scraped": "2026-06-14", "source": "city scrape",
        "name": [f"Apto {i}" for i in range(n)], "description": "texto livre", "picture_url": "https://x",
        "host_id": [20, 20, 21, 22, 23, 24][:n], "host_url": "https://h", "host_profile_id": 1.0,
        "host_profile_url": "https://p", "host_name": "Bia", "hosts_time_as_user_years": 5.0,
        "hosts_time_as_user_months": 3.0, "hosts_time_as_host_years": 4.0, "hosts_time_as_host_months": 6.0,
        "host_location": "New York", "host_about": "sobre mim", "host_is_superhost": "t",
        "host_picture_url": "https://f", "host_listings_count": 2.0, "host_has_profile_pic": "t",
        "host_identity_verified": "f", "neighbourhood_cleansed": "Williamsburg",
        "neighbourhood_group_cleansed": "Brooklyn", "latitude": 40.71, "longitude": -73.95,
        "property_type": "Entire rental unit", "room_type": "Entire home/apt", "accommodates": 2,
        "bathrooms": np.nan, "bathrooms_text": "1.5 shared baths", "bedrooms": 1.0, "beds": 1.0,
        "amenities": '["Wifi", "Elevator"]', "price": "$113.97",
        "price_quote_checkin_date": "2026-07-11", "price_quote_checkout_date": "2026-08-10",
        "price_quote_total_price": 3419.19, "price_quote_price_per_night": 113.97, "price_quote_raw": raw_30,
        "minimum_nights": 30.0, "maximum_nights": 365.0, "minimum_minimum_nights": 30.0,
        "maximum_minimum_nights": 30.0, "minimum_maximum_nights": 365.0, "maximum_maximum_nights": 365.0,
        "minimum_nights_avg_ntm": 30.0, "maximum_nights_avg_ntm": 365.0, "has_availability": "t",
        "availability_30": 10, "availability_60": 20, "availability_90": 30, "availability_365": 100,
        "calendar_last_scraped": "2026-06-14", "number_of_reviews": 5, "number_of_reviews_ltm": 1,
        "number_of_reviews_l30d": 0, "availability_eoy": 50, "number_of_reviews_ly": 1,
        "estimated_occupancy_l365d": 60, "estimated_revenue_l365d": 6838.2,
        "first_review": "2020-01-01", "last_review": "2026-05-01",
        "license": "OSE-STRREG-0000001", "calculated_host_listings_count": 1,
        "calculated_host_listings_count_entire_homes": 1, "calculated_host_listings_count_private_rooms": 0,
        "calculated_host_listings_count_shared_rooms": 0, "reviews_per_month": 0.8,
    }
    for s in ("rating", "accuracy", "cleanliness", "checkin", "communication", "location", "value"):
        valores[f"review_scores_{s}"] = 4.8
    for c, v in valores.items():
        df[c] = v
    df.loc[1, ["price", "price_quote_total_price", "price_quote_price_per_night"]] = [None, np.nan, np.nan]
    df.loc[1, "price_quote_raw"] = INDISPONIVEL                        # P01 preco ausente
    df.loc[2, ["price_quote_checkout_date", "price", "minimum_nights"]] = ["2027-07-11", "$9.37", 365.0]  # P03
    df.loc[3, "minimum_nights"] = np.nan                               # B07 -> base
    df.loc[4, "price"] = "$15,000.00"                                  # P05
    df.loc[5, ["license", "host_is_superhost"]] = [None, None]
    return df


# --- limpeza de ponta a ponta --------------------------------------------------------------------------------


def test_limpar_2019_quarentena_tem_regra_motivo_e_escopo():
    silver, quar, rel = pl.limpar_2019(_kaggle(), BAIRROS, ids_2026={2, 3})
    assert set(quar.columns) == {"snapshot", "id", "regra", "motivo", "escopo"}
    assert quar["motivo"].str.len().gt(10).all()
    por_regra = dict(zip(quar["regra"], quar["escopo"], strict=True))
    assert por_regra == {"B01": "base", "B03": "base", "B05": "base", "P02": "preco"}
    # base: 8 - (id repetido, fora de NYC, bairro desconhecido) = 5; preco zero fica na base
    assert len(silver) == 5
    assert rel["cascata"]["base_final"] == 5 and rel["cascata"]["preco_valido"] == 4
    assert not silver.loc[silver["id"] == 3, "preco_valido"].item()
    assert silver["name"].isna().sum() == 1, "name nulo nao pode derrubar a linha"
    assert silver["presente_2026"].sum() == 2
    assert schema.validar(silver, schema.S2019) == []


def test_limpar_2026_regras_de_preco_e_base():
    silver, quar, rel = pl.limpar_2026(_detalhado(), BAIRROS)
    regras_por_id = dict(zip(quar["id"], quar["regra"], strict=True))
    assert regras_por_id == {102: "P01", 103: "P03", 104: "B07", 105: "P05"}
    assert len(silver) == 5 and silver["preco_valido"].sum() == 2
    assert rel["cascata"]["fora_do_preco"] == 3
    linha = silver.loc[silver["id"] == 101].iloc[0]
    assert linha["preco"] == pytest.approx(113.97)
    assert linha["preco_cotacao_noites"] == 30
    assert linha["desconto_pct"] == pytest.approx(6979.00 / 10398.19)
    assert linha["banheiros"] == 1.5 and linha["banheiro_compartilhado"]
    assert linha["amen_wifi"] and linha["amen_elevador"] and not linha["amen_piscina"]
    assert linha["host_anos"] == pytest.approx(4.5)
    assert linha["min30"] and linha["host_superhost"]
    sem_licenca = silver.loc[silver["id"] == 106].iloc[0]
    assert sem_licenca["licenca_status"] == "ausente" and not sem_licenca["host_superhost"]
    assert schema.validar(silver, schema.S2026) == []


def test_nenhuma_coluna_pessoal_nas_saidas_sinteticas():
    s19, _, _ = pl.limpar_2019(_kaggle(), BAIRROS)
    s26, _, _ = pl.limpar_2026(_detalhado(), BAIRROS)
    res = pl.empilhar_resumo(s19, s26)
    for df in (s19, s26, res):
        assert not schema.PROIBIDAS_NA_SILVER & set(df.columns)
        assert "host_name" not in df.columns


def test_limpeza_e_idempotente():
    a19, qa, _ = pl.limpar_2019(_kaggle(), BAIRROS)
    b19, qb, _ = pl.limpar_2019(_kaggle(), BAIRROS)
    pd.testing.assert_frame_equal(a19, b19)
    pd.testing.assert_frame_equal(qa, qb)
    a26, _, _ = pl.limpar_2026(_detalhado(), BAIRROS)
    b26, _, _ = pl.limpar_2026(_detalhado(), BAIRROS)
    pd.testing.assert_frame_equal(a26, b26)
    assert pl.hash_conteudo(a26) == pl.hash_conteudo(b26)


def test_resumo_empilha_e_renomeia_o_bairro_de_2026():
    s19, _, _ = pl.limpar_2019(_kaggle(), BAIRROS)
    s26, _, _ = pl.limpar_2026(_detalhado(), BAIRROS)
    res = pl.empilhar_resumo(s19, s26)
    assert len(res) == len(s19) + len(s26)
    assert res["snapshot"].value_counts().to_dict() == {"2019": len(s19), "2026": len(s26)}
    assert set(res.loc[res["snapshot"] == "2026", "neighbourhood"]) == {"Williamsburg"}
    assert schema.validar(res, schema.SRESUMO) == []


def test_cascata_atribui_cada_linha_a_uma_unica_regra():
    df = _kaggle()
    df.loc[3, "price"] = 0  # fora de NYC E preco zero: sai da base, nao conta no preco
    df = df.assign(preco=dv.parse_preco(df["price"])).drop(columns=["price"])
    fb, fp, quar, rel = regras.aplicar(df, regras.Contexto(config.ROTULO_2019, BAIRROS))
    assert not (fb & fp).any()
    # a linha 4 casa com B03 e com P02, mas entra na quarentena uma vez so (pela primeira)
    assert not quar["id"].duplicated().any()
    assert quar.loc[quar["id"] == 4, "regra"].tolist() == ["B03"]
    p02 = next(r for r in rel if r["codigo"] == "P02")
    assert p02["casam"] == 2 and p02["cascata"] == 1


# --- dado real -------------------------------------------------------------------------------------------------


def _exige(*caminhos):
    faltam = [c for c in caminhos if not c.exists()]
    if faltam:
        pytest.skip(f"silver ainda nao gerada: {[f.name for f in faltam]}")


@pytest.mark.dados
def test_silver_real_confere_com_o_contrato():
    _exige(pl.SAIDA_2019, pl.SAIDA_2026, pl.SAIDA_RESUMO)
    for caminho, saida in ((pl.SAIDA_2019, schema.S2019), (pl.SAIDA_2026, schema.S2026),
                           (pl.SAIDA_RESUMO, schema.SRESUMO)):
        df = pd.read_parquet(caminho)
        assert schema.validar(df, saida) == [], saida
        assert not schema.PROIBIDAS_NA_SILVER & set(df.columns), saida


@pytest.mark.dados
def test_silver_real_fecha_com_o_relatorio_de_qualidade():
    _exige(pl.SAIDA_2019, pl.SAIDA_2026, pl.SAIDA_QUARENTENA, pl.SAIDA_QUALIDADE)
    rel = json.loads(pl.SAIDA_QUALIDADE.read_text(encoding="utf-8"))
    s19, s26 = pd.read_parquet(pl.SAIDA_2019), pd.read_parquet(pl.SAIDA_2026)
    quar = pd.read_parquet(pl.SAIDA_QUARENTENA)
    assert len(s19) + (quar.query("snapshot == '2019' and escopo == 'base'").shape[0]) == 48_895
    assert len(s26) + (quar.query("snapshot == '2026' and escopo == 'base'").shape[0]) == 30_259
    assert rel["cascata"]["2019"]["preco_valido"] == int(s19["preco_valido"].sum())
    assert rel["cascata"]["2026"]["preco_valido"] == int(s26["preco_valido"].sum())
    assert rel["saidas"]["anuncios_2026.parquet"]["hash_conteudo"] == pl.hash_conteudo(s26)
