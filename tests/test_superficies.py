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
EXECUTIVA = RAIZ / "site" / "executiva" / "index.html"
MAPA = RAIZ / "site" / "mapa" / "index.html"
DECKS = [p for p in (DECK, EXECUTIVA)]


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


def test_o_preco_publicado_e_o_comparavel():
    """O portal e o deck exibem a diaria de 2026 SEM desconto, a definicao de 2019.

    Com o preco descontado, o apartamento inteiro de 30+ noites parecia 6,4% mais
    barato que em 2019; na mesma definicao, esta 4,0% mais caro. Este teste amarra
    o numero publicado ao resultado do pipeline, para que ele nao volte a escorregar.
    """
    comp = RAIZ / "data" / "processed" / "_comparativo.json"
    if not (comp.exists() and PORTAL.exists() and DECK.exists()):
        pytest.skip("_comparativo.json ou superficie ausente")
    estratos = {(e["estrato"], e["tipo"]): e
                for e in json.loads(comp.read_text(encoding="utf-8"))["preco_por_estrato"]}
    longa = estratos[("30+ noites", "Entire home/apt")]
    esperado = _pt(longa["variacao_real_pct"]) + "%"
    for nome, p in (("portal", PORTAL), ("deck", DECK)):
        html = p.read_text(encoding="utf-8")
        assert esperado in html, f"{nome}: a variacao comparavel ({esperado}) nao aparece"
    # no deck, "−6,4%" so poderia ser rotulo de grafico com o preco descontado. No
    # portal ele aparece de proposito, no texto que explica a correcao.
    assert "−6,4%" not in DECK.read_text(encoding="utf-8"), \
        "deck: ainda publica a variacao calculada com o preco descontado"


@pytest.mark.parametrize("deck", DECKS, ids=lambda p: p.parent.name)
def test_cada_slide_tem_o_proprio_frame(deck):
    """Um slide fora do seu `.frame` divide a tela com o vizinho.

    Aconteceu: ao trocar um slide, o `</div>` que fechava o frame dele e o
    `<div class="frame">` que abria o seguinte sairam junto. Os dois slides
    ficaram lado a lado no mesmo frame, o contador passou a dizer 19 em vez de 20
    — e nenhum slide transbordava a propria caixa, entao a medicao de geometria
    nao acusou nada.
    """
    import re
    if not deck.exists():
        pytest.skip(f"{deck.parent.name} ausente")
    html = deck.read_text(encoding="utf-8")
    slide = re.compile(r'<section class="[^"]*\bslide\b')
    blocos = re.split(r'<div class="frame"', html)[1:]
    assert blocos, "o deck nao tem nenhum .frame"
    por_frame = [len(slide.findall(b)) for b in blocos]
    assert all(n == 1 for n in por_frame), (
        f"frames com numero de slides diferente de 1: "
        f"{[(i + 1, n) for i, n in enumerate(por_frame) if n != 1]}")
    assert len(slide.findall(html)) == len(blocos)


def test_a_executiva_nao_escreve_nome_de_integrante(resumo):
    """Nome de integrante so existe em produto/autoria.py (CLAUDE.md, invariante da
    equipe). A versao executiva le os nomes de site/data/resumo.json em tempo de
    execucao; se algum aparecer escrito no HTML, ele vai envelhecer sozinho."""
    if not EXECUTIVA.exists():
        pytest.skip("versao executiva ausente")
    html = EXECUTIVA.read_text(encoding="utf-8")
    escritos = [p["nome"] for p in resumo["equipe"] if p["nome"] in html]
    assert not escritos, f"nomes escritos a mao na versao executiva: {escritos}"
    assert "data-equipe-cartoes" in html and "resumo.json" in html


def test_nenhuma_superficie_diz_que_o_mercado_nao_encolheu():
    """O mercado encolheu: -38% de anuncios, -59% de oferta operada. O que o dado
    mostra ALEM disso e que ele foi trocado. "Nao encolheu" confundiu quem leu."""
    for p in (PORTAL, DECK, EXECUTIVA):
        if p.exists():
            assert "não encolheu" not in p.read_text(encoding="utf-8").lower(), \
                f"{p.parent.name}: diz que o mercado nao encolheu"


def test_o_deck_nao_inventa_precisao_na_cobertura(resumo, paginas):
    """0,79578 exibido como '80%' vira a tautologia 'a faixa de 80% acerta 80%'."""
    cobertura = _pt(100 * resumo["modelo_preco"]["cobertura_80"]) + "%"
    assert cobertura == "79,6%", f"cobertura mudou: {cobertura}"
    for nome, html in paginas.items():
        assert "acertou 80%" not in html, f"{nome}: arredonda a cobertura ate virar tautologia"
