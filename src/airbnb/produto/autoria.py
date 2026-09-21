"""Autoria do trabalho — fonte unica dos nomes que aparecem nas superficies.

Mesmo motivo de `schema.py`: nome escrito a mao em varios arquivos diverge no
dia em que um deles muda. O site, a documentacao e o README leem daqui.

RA ausente e `None` e aparece como "RA a confirmar", nao some: integrante sem
numero tem de ser pendencia visivel.

Uso:
    from airbnb.produto.autoria import GRUPO, autores, CREDITO
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DISCIPLINA = "Data Science 2"
INSTITUICAO = "ESEG"
PROFESSOR = "Prof. Marino Catarino"

CREDITO = f"{DISCIPLINA} · {INSTITUICAO} · {PROFESSOR}"

REPOSITORIO = "https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc"


@dataclass(frozen=True)
class Autor:
    """Um integrante do grupo. `ra` e None enquanto o numero nao foi informado."""

    nome: str
    ra: str | None = None
    github: str | None = None

    def rotulo(self) -> str:
        """Nome com RA, ou com a pendencia explicita quando o RA falta."""
        return f"{self.nome} (RA {self.ra})" if self.ra else f"{self.nome} (RA a confirmar)"


#: Ordem alfabetica pelo primeiro nome, de proposito: nao ha primeiro autor.
GRUPO: tuple[Autor, ...] = (
    Autor("Felipe Marins", "44776", "felipe44776-eseg"),
    Autor("Otavio Bonfochi", "44585", "otaviobonfochisilva1-rgb"),
    Autor("Phelipe Torres Pamponet da França", "46643", "phelipe-061"),
    Autor("Tadeu Radovan Graça", "46305", "tadeu46305-prog"),
)


def autores(com_ra: bool = True, separador: str = " · ") -> str:
    """Os integrantes numa linha. `com_ra=False` onde o espaco nao cabe o numero."""
    if not com_ra:
        return separador.join(a.nome for a in GRUPO)
    return separador.join(a.rotulo() for a in GRUPO)


def lista_markdown() -> str:
    """Tabela dos integrantes para README e docs — mesma fonte que o site."""
    linhas = ["| integrante | RA | GitHub |", "|---|---|---|"]
    for a in GRUPO:
        ra = f"**{a.ra}**" if a.ra else "*a confirmar*"
        gh = f"[@{a.github}](https://github.com/{a.github})" if a.github else "—"
        linhas.append(f"| {a.nome} | {ra} | {gh} |")
    return "\n".join(linhas)


def equipe_json() -> list[dict]:
    """Integrantes no formato que o site le (`site/data/resumo.json` -> equipe)."""
    return [{"nome": a.nome, "ra": a.ra, "github": a.github} for a in GRUPO]


def gravar_snippet_docs() -> Path:
    """Grava a tabela da equipe como trecho incluido pelas paginas do MkDocs.

    A documentacao inclui `_snippets/equipe.md` (pymdownx.snippets) em vez de
    repetir os nomes — e `tests/test_autoria.py` falha se o trecho divergir.
    """
    from airbnb.config import DOCS

    destino = DOCS / "_snippets" / "equipe.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(lista_markdown() + "\n", encoding="utf-8")
    return destino


MARCA_INICIO = "<!-- equipe:inicio -->"
MARCA_FIM = "<!-- equipe:fim -->"


def atualizar_readme() -> bool:
    """Reescreve a tabela da equipe no README entre as marcas. True se mudou."""
    from airbnb.config import RAIZ

    readme = RAIZ / "README.md"
    texto = readme.read_text(encoding="utf-8")
    ini = texto.index(MARCA_INICIO) + len(MARCA_INICIO)
    fim = texto.index(MARCA_FIM)
    novo = texto[:ini] + "\n" + lista_markdown() + "\n" + texto[fim:]
    if novo != texto:
        readme.write_text(novo, encoding="utf-8")
    return novo != texto


if __name__ == "__main__":  # pragma: no cover - conferencia manual
    print(CREDITO)
    print(autores())
    print()
    print(lista_markdown())
    print(f"\ntrecho gravado em {gravar_snippet_docs()}")
    print(f"README {'atualizado' if atualizar_readme() else 'ja estava em dia'}")
