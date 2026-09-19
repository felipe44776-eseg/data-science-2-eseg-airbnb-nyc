"""Gera e executa os notebooks da apresentacao — que nao contem logica (invariante 6).

Cada celula de codigo importa de `src/airbnb` ou le um resultado `_*.json`; o
notebook e so a vitrine. Por isso ele e GERADO: editar a mao um notebook que se
regenera seria trabalho perdido. Para mudar o conteudo, mude aqui.
"""

from __future__ import annotations

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from airbnb.config import RAIZ

PASTA = RAIZ / "notebooks"

PREAMBULO = """\
import json, sys
from pathlib import Path
RAIZ = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(RAIZ / "src"))
import pandas as pd
from IPython.display import Markdown, SVG, Image, display
pd.set_option("display.max_columns", 30)
def resultado(nome):
    return json.loads((RAIZ / "data" / "processed" / nome).read_text(encoding="utf-8"))
def tabela(nome):
    return Markdown((RAIZ / "docs" / "_snippets" / f"{nome}.md").read_text(encoding="utf-8"))
def figura(nome):
    p = RAIZ / "docs" / "assets" / "figuras" / nome
    return SVG(filename=str(p)) if p.suffix == ".svg" else Image(filename=str(p))
"""

NOTEBOOKS: dict[str, list[tuple[str, str]]] = {
    "01-entendimento-dos-dados.ipynb": [
        ("md", "# 1 · Entendimento dos dados\n\nPerguntas da equipe (reports/v0/Análise.txt) "
               "respondidas com contagem, e as correções da v0. Lógica em "
               "`src/airbnb/eda/qualidade.py`; aqui só o resultado."),
        ("code", PREAMBULO),
        ("code", "q = resultado('_perguntas_equipe.json')\n"
                 "pd.DataFrame(q['Q1_id_unico_e_duplicatas']).T"),
        ("code", "pd.DataFrame(q['Q3_host_id_x_host_name']).T"),
        ("code", "c = resultado('_correcoes_v0.json')['a_ocupacao']\n"
                 "pd.DataFrame({'v0 (1 − disponibilidade)': c['v0_reproduzido']['por_distrito'],\n"
                 "              'modelo de avaliações (Inside Airbnb)': "
                 "c['ocupacao_2019_modelo']['por_distrito']})"),
        ("md", "## 2019 × 2026"),
        ("code", "display(tabela('tabela_kpis'))\ndisplay(figura('min30_distritos.svg'))"),
        ("code", "display(tabela('tabela_estratos'))\ndisplay(figura('estratos.svg'))"),
        ("code", "display(tabela('tabela_decomposicao'))"),
    ],
    "02-modelagem-e-avaliacao.ipynb": [
        ("md", "# 2 · Modelagem e avaliação\n\nEscada de modelos sob validação cruzada "
               "espacial, ablação das fontes externas, intervalo conformal, sobrevivência e "
               "deriva temporal. Lógica em `src/airbnb/models/`."),
        ("code", PREAMBULO),
        ("code", "display(tabela('tabela_escada'))\ndisplay(figura('escada.svg'))"),
        ("code", "display(tabela('tabela_ablacao'))\ndisplay(figura('ablacao.svg'))"),
        ("code", "display(figura('shap_grupos.svg'))\ndisplay(figura('dependencia.svg'))"),
        ("code", "display(tabela('tabela_conformal'))"),
        ("code", "display(tabela('tabela_moran'))\ndisplay(tabela('tabela_variancia'))"),
        ("code", "display(tabela('tabela_sobrevivencia_or'))\n"
                 "display(figura('sobrevivencia.svg'))"),
        ("code", "display(tabela('tabela_deriva'))\ndisplay(figura('deriva.svg'))"),
        ("code", "display(tabela('tabela_criterios'))"),
    ],
}


def gerar() -> list:
    PASTA.mkdir(exist_ok=True)
    feitos = []
    for nome, celulas in NOTEBOOKS.items():
        nb = new_notebook(cells=[new_markdown_cell(t) if k == "md" else new_code_cell(t)
                                 for k, t in celulas])
        nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3",
                                     "language": "python"}
        NotebookClient(nb, timeout=300, kernel_name="python3",
                       resources={"metadata": {"path": str(PASTA)}}).execute()
        nbformat.write(nb, PASTA / nome)
        feitos.append(nome)
    return feitos


if __name__ == "__main__":
    print("executados:", ", ".join(gerar()))
