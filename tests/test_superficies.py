"""As superficies publicadas nao podem divergir do pipeline.

O deck e o portal escrevem numeros no proprio HTML — o deck porque e uma peca de
apresentacao e nao busca dado, o portal porque a espinha precisa existir antes de
qualquer fetch. Isso significa que um `.\\tasks.ps1 all` pode mudar o resultado e
deixar as duas paginas mentindo em silencio, sem que nada acuse.

Este teste e o que acusa: pega os numeros canonicos de site/data/resumo.json —
que sai do pipeline — e exige que cada superficie os exiba com a mesma grafia.
Se o modelo mudar, o teste quebra e obriga a atualizar a pagina no mesmo commit.

Quando um numero mudar de proposito: rode `.\\tasks.ps1 site`, atualize o texto
das paginas e so entao o teste volta a passar. E esse o ponto.
"""

from __future__ import annotations

import json

import pytest

from airbnb.config import RAIZ, SITE_DADOS

PORTAL = RAIZ / "site" / "index.html"
DECK = RAIZ / "site" / "apresentacao" / "index.html"
MAPA = RAIZ / "site" / "mapa" / "index.html"


def _pt(valor: float, casas: int = 1) -> str:
    """Numero na grafia que as paginas usam: virgula decimal, ponto de milhar."""
    return f"{valor:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@pytest.fixture(scope="module")
def resumo() -> dict:
    caminho = SITE_DADOS / "resumo.json"
    if not caminho.exists():
        pytest.skip("site/data/resumo.json ausente — rode .\\tasks.ps1 site")
    return json.loads(caminho.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def paginas() -> dict[str, str]:
    faltando = [p.name for p in (PORTAL, DECK) if not p.exists()]
    if faltando:
        pytest.skip(f"superficie ausente: {faltando}")
    return {"portal": PORTAL.read_text(encoding="utf-8"),
            "deck": DECK.read_text(encoding="utf-8")}


def _canonicos(resumo: dict) -> dict[str, str]:
    k19, k26 = resumo["kpis"]["2019"], resumo["kpis"]["2026"]
    m = resumo["modelo_preco"]
    return {
        "anuncios 2019": f"{k19['anuncios']:,}".replace(",", "."),
        "anuncios 2026": f"{k26['anuncios']:,}".replace(",", "."),
        "mdape do simulador": _pt(100 * m["mdape"]) + "%",
        "sobrevivencia": _pt(100 * resumo["sobrevivencia"]["pct"]) + "%",
        "min30 em 2026": _pt(100 * k26["pct_min30"]) + "%",
    }


@pytest.mark.parametrize("superficie", ["portal", "deck"])
def test_superficie_concorda_com_o_pipeline(resumo, paginas, superficie):
    html = paginas[superficie]
    divergentes = {k: v for k, v in _canonicos(resumo).items() if v not in html}
    assert not divergentes, (
        f"{superficie}: estes numeros do pipeline nao aparecem na pagina — "
        f"ela ficou para tras de site/data/resumo.json: {divergentes}"
    )


def test_nenhuma_superficie_anuncia_dado_provisorio():
    """O aviso de 'dados provisorios' era resto de andaime e nunca podia disparar."""
    for p in (PORTAL, DECK, MAPA):
        if p.exists():
            texto = p.read_text(encoding="utf-8").lower()
            assert "dados provisórios" not in texto, f"{p.name} ainda anuncia dado provisorio"
            assert "faixa-provisoria" not in texto, f"{p.name} ainda tem a faixa provisoria"


def test_o_deck_nao_inventa_precisao_na_cobertura(resumo, paginas):
    """0,79578 exibido como '80%' vira a tautologia 'a faixa de 80% acerta 80%'."""
    cobertura = _pt(100 * resumo["modelo_preco"]["cobertura_80"]) + "%"
    assert cobertura == "79,6%", f"cobertura mudou: {cobertura}"
    for nome, html in paginas.items():
        assert "acertou 80%" not in html, f"{nome}: arredonda a cobertura ate virar tautologia"
