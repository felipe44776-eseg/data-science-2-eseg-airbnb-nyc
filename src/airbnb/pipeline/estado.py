"""Observabilidade do pipeline: o que rodou, o que esta velho, o que falta.

O grafo de etapas e declarado UMA vez em `ETAPAS`. A partir dele:

  ausente   — alguma saida nao existe
  obsoleto  — alguma entrada e mais nova que a saida mais antiga (o caso perigoso:
              o numero publicado nao reflete mais o dado)
  ok        — todas as saidas existem e sao mais novas que tudo que as gerou

Entrada que e codigo (`src/...py`) conta: mudar a regra de limpeza torna a
limpeza obsoleta, mesmo que o dado nao tenha mudado.

Uso:
    python -m airbnb.pipeline.estado             # tabela de status
    python -m airbnb.pipeline.estado --json      # para script
    python -m airbnb.pipeline.estado --execucoes # historico de reports/execucao.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass

from airbnb.config import RAIZ

LOG_EXECUCAO = RAIZ / "reports" / "execucao.jsonl"


@dataclass(frozen=True)
class Etapa:
    chave: str
    titulo: str
    entradas: tuple[str, ...]
    saidas: tuple[str, ...]
    fase: str


P = "data/processed/"
ETAPAS: list[Etapa] = [
    # sem entrada de codigo: o dado baixado nao "envelhece" porque o downloader mudou —
    # quem garante que a fonte e a mesma e o hash do manifesto (`dados --verificar`)
    Etapa("dados", "Fontes primarias (hash conferido)",
          (),
          ("data/raw/kaggle/AB_NYC_2019.csv", "data/raw/_manifesto.json"), "2"),
    Etapa("limpeza", "Limpeza, quarentena e perguntas da equipe",
          ("data/raw/kaggle/AB_NYC_2019.csv", "src/airbnb/schema.py",
           "src/airbnb/clean/pipeline.py", "src/airbnb/eda/qualidade.py"),
          (P + "anuncios_2019.parquet", P + "anuncios_2026.parquet",
           P + "anuncios_resumo.parquet", P + "_qualidade.json",
           P + "_perguntas_equipe.json", P + "_correcoes_v0.json"), "3"),
    Etapa("externos", "Fontes externas",
          ("src/airbnb/external/coletar.py",),
          ("data/external/_manifesto_externos.json",), "2"),
    Etapa("celulas", "Celulas H3 r9 com features de localizacao",
          ("data/external/_manifesto_externos.json", "src/airbnb/features/celulas.py"),
          (P + "celulas_r9.parquet", P + "_celulas.json"), "3"),
    Etapa("features", "Tabelas de modelagem",
          (P + "anuncios_2019.parquet", P + "anuncios_2026.parquet", P + "celulas_r9.parquet",
           "src/airbnb/features/anuncios.py"),
          (P + "modelagem_2019.parquet", P + "modelagem_2026.parquet", P + "_features.json"), "3"),
    Etapa("comparativo", "Comparativo 2019 -> atual",
          (P + "anuncios_resumo.parquet", P + "cpi_ny.parquet", "src/airbnb/eda/comparativo.py"),
          (P + "_comparativo.json", P + "comparativo_r8.parquet"), "2/5"),
    Etapa("preco", "Modelo de preco",
          (P + "modelagem_2026.parquet", "src/airbnb/models/preco.py",
           "src/airbnb/models/validacao.py", "src/airbnb/models/especificacao.py"),
          (P + "_preco.json", P + "preco_oof.parquet"), "4"),
    Etapa("espacial", "Testes de localizacao",
          (P + "modelagem_2026.parquet", P + "preco_oof.parquet", "src/airbnb/eda/espacial.py",
           "src/airbnb/eda/estatistica_espacial.py"),
          (P + "_espacial.json",), "2/5"),
    Etapa("ocupacao", "Modelo de ocupacao",
          (P + "modelagem_2026.parquet", P + "preco_oof.parquet", "src/airbnb/models/ocupacao.py"),
          (P + "_ocupacao.json",), "4"),
    Etapa("sobrevivencia", "Sobrevivencia 2019 -> atual",
          (P + "modelagem_2019.parquet", "src/airbnb/models/sobrevivencia.py"),
          (P + "_sobrevivencia.json",), "4"),
    Etapa("deriva", "Validacao temporal",
          (P + "modelagem_2019.parquet", P + "modelagem_2026.parquet",
           "src/airbnb/models/deriva.py"),
          (P + "_deriva.json",), "5"),
    Etapa("site", "Dados do site + paridade JS",
          (P + "_preco.json", P + "_comparativo.json", P + "_espacial.json",
           P + "_sobrevivencia.json", P + "_ocupacao.json", P + "_deriva.json",
           "src/airbnb/produto/exportar.py", "src/airbnb/produto/modelo_js.py"),
          ("site/data/resumo.json", "site/data/modelo_preco.json",
           "site/data/celulas_r8.json", "site/data/celulas_r9.json"), "6"),
    Etapa("figuras", "Tabelas e figuras da documentacao",
          (P + "_preco.json", P + "_comparativo.json", P + "_sobrevivencia.json",
           P + "_deriva.json", P + "premio_r9.parquet", "src/airbnb/produto/figuras.py"),
          ("docs/assets/figuras/escada.svg", "docs/assets/figuras/mapa_premio.png"), "6"),
]


def _mtime(caminho: str) -> float | None:
    p = RAIZ / caminho
    return p.stat().st_mtime if p.exists() else None


def status() -> list[dict]:
    """Estado de cada etapa, na ordem do grafo."""
    linhas = []
    for e in ETAPAS:
        saidas = {s: _mtime(s) for s in e.saidas}
        faltando = [s for s, t in saidas.items() if t is None]
        if faltando:
            linhas.append({**asdict(e), "estado": "ausente", "motivo": faltando[0]})
            continue
        mais_velha = min(saidas.values())
        novas = [x for x in e.entradas if (t := _mtime(x)) is not None and t > mais_velha]
        estado = "obsoleto" if novas else "ok"
        linhas.append({**asdict(e), "estado": estado, "motivo": novas[0] if novas else ""})
    return linhas


def _execucoes(n: int = 30) -> None:
    if not LOG_EXECUCAO.exists():
        print("nenhuma execucao registrada ainda (reports/execucao.jsonl)")
        return
    regs = [json.loads(x) for x in LOG_EXECUCAO.read_text(encoding="utf-8").splitlines() if x]
    for r in regs[-n:]:
        extra = r.get("segundos", "")
        print(f"{r['ts']}  {r['etapa']:<14} {r['evento']:<7} {extra}  {r.get('detalhe', '')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--execucoes", action="store_true")
    args = ap.parse_args()
    if args.execucoes:
        _execucoes()
        return 0
    linhas = status()
    if args.json:
        print(json.dumps(linhas, ensure_ascii=False, indent=2))
        return 0
    cor = {"ok": "\033[32m", "obsoleto": "\033[33m", "ausente": "\033[31m"}
    for x in linhas:
        c = cor[x["estado"]]
        print(f"{c}{x['estado']:<9}\033[0m fase {x['fase']:<4} {x['chave']:<14} "
              f"{x['titulo']:<45} {x['motivo']}")
    n_ok = sum(x["estado"] == "ok" for x in linhas)
    print(f"\n{n_ok}/{len(linhas)} etapas ok")
    proxima = next((x for x in linhas if x["estado"] != "ok"), None)
    if proxima:
        print(f"proxima acionavel: .\\tasks.ps1 {proxima['chave']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
