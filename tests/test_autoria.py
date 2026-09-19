"""Autoria: uma fonte, todas as superficies iguais."""

from __future__ import annotations

import json

from airbnb.config import DOCS, SITE_DADOS
from airbnb.produto.autoria import GRUPO, equipe_json, lista_markdown


def test_grupo_em_ordem_alfabetica():
    nomes = [a.nome for a in GRUPO]
    assert nomes == sorted(nomes)


def test_ra_ausente_vira_pendencia_visivel():
    tabela = lista_markdown()
    for a in GRUPO:
        assert a.nome in tabela
    if any(a.ra is None for a in GRUPO):
        assert "a confirmar" in tabela


def test_snippet_da_documentacao_bate_com_o_grupo():
    trecho = DOCS / "_snippets" / "equipe.md"
    assert trecho.exists(), "rode: python -m airbnb.produto.autoria"
    assert trecho.read_text(encoding="utf-8").strip() == lista_markdown().strip()


def test_readme_bate_com_o_grupo():
    from airbnb.config import RAIZ
    from airbnb.produto.autoria import MARCA_FIM, MARCA_INICIO

    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    bloco = texto[texto.index(MARCA_INICIO) + len(MARCA_INICIO):texto.index(MARCA_FIM)]
    assert bloco.strip() == lista_markdown().strip(), "rode: python -m airbnb.produto.autoria"


def test_site_carrega_todos_os_integrantes():
    resumo = SITE_DADOS / "resumo.json"
    if not resumo.exists():
        return
    dado = json.loads(resumo.read_text(encoding="utf-8"))
    if dado.get("provisorio"):
        return
    assert dado["equipe"] == equipe_json()
