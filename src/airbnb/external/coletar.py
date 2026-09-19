"""Coleta de todas as fontes externas (nao-Kaggle) e manifesto com hash.

Cada fonte e um modulo com `coletar(forcar) -> dict`; este CLI so orquestra:
baixa o que falta, pula o que existe (salvo `--forcar`) e grava, fonte a fonte,
`data/external/_manifesto_externos.json` — inclusive a fonte que FALHOU, com o
erro. Uma fonte fora do ar nao derruba as outras: a celula fica com a feature
nula e a cobertura em `_celulas.json` mostra o buraco.

Uso:
    python -m airbnb.external.coletar                  # todas
    python -m airbnb.external.coletar --apenas acs cpi # so algumas
    python -m airbnb.external.coletar --forcar         # rebaixa
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
import traceback

from airbnb.external import manifesto

#: chave -> (modulo, descricao). A ordem e a de dependencia: geometria antes de
#: quem agrega por ela (311 precisa do MODZCTA; NYPD, dos poligonos de delegacia).
FONTES: dict[str, tuple[str, str]] = {
    "cpi": ("airbnb.external.cpi", "E7 CPI-U NY (deflator)"),
    "marcos": ("airbnb.external.marcos", "E9 marcos da cidade"),
    "metro": ("airbnb.external.metro", "E4 estacoes do metro (MTA)"),
    "tracts": ("airbnb.external.tracts", "E2 geometria dos tracts (Census)"),
    "modzcta": ("airbnb.external.modzcta", "MODZCTA (ponte ZIP -> area)"),
    "acs": ("airbnb.external.acs", "E1 ACS 5 anos por tract (Census)"),
    "nypd": ("airbnb.external.nypd", "E3 queixas criminais (NYPD)"),
    "ruido311": ("airbnb.external.ruido311", "E5 311 barulho"),
    "zillow": ("airbnb.external.zillow", "E6 Zillow ZORI por ZIP"),
    "osm": ("airbnb.external.osm", "E8 POIs do OpenStreetMap"),
    "ll18": ("airbnb.external.ll18", "E10 Local Law 18 / OSE"),
}


def preservar(anterior: dict, novo: dict) -> dict:
    """Arquivo pulado mantem a proveniencia da coleta que o baixou.

    Sem isto, cada execucao que pula um arquivo existente regravaria a data de
    acesso como "agora" e perderia os parametros da consulta original — o
    manifesto deixaria de dizer QUANDO e COMO o dado foi obtido. Se o hash mudou
    desde o registro, o arquivo foi trocado por fora: fica o registro novo,
    marcado.
    """
    antigos = {a["arquivo"]: a for a in anterior.get("artefatos", [])}
    out = []
    for a in novo.get("artefatos", []):
        velho = antigos.get(a["arquivo"])
        pulado = "ja existia" in str(a.get("nota", ""))
        if pulado and velho and velho.get("sha256") == a["sha256"]:
            out.append({**velho, "verificado_em": a["acessado_em"]})
            continue
        if pulado and velho and velho.get("sha256") != a["sha256"]:
            a["hash_diverge_do_registro_anterior"] = velho.get("sha256")
        out.append(a)
    return {**novo, "artefatos": out}


def rodar(chave: str, forcar: bool) -> bool:
    modulo, descricao = FONTES[chave]
    print(f"==> {chave}: {descricao}", flush=True)
    t0 = time.time()
    try:
        registro = importlib.import_module(modulo).coletar(forcar=forcar)
        registro = preservar(manifesto.anterior(chave), registro)
        registro["segundos"] = round(time.time() - t0, 1)
        manifesto.registrar(chave, registro)
        print(f"    ok em {registro['segundos']}s", flush=True)
        return True
    except Exception as e:  # noqa: BLE001 — falha de uma fonte e registrada, nao fatal
        traceback.print_exc()
        anterior = manifesto.anterior(chave)
        manifesto.registrar(chave, {**anterior, "estado": "falhou",
                                    "erro": f"{type(e).__name__}: {e}",
                                    "segundos": round(time.time() - t0, 1)})
        print(f"    FALHOU: {e}", flush=True)
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apenas", nargs="+", metavar="FONTE", choices=list(FONTES),
                    help="limita as fontes: " + ", ".join(FONTES))
    ap.add_argument("--forcar", action="store_true", help="rebaixa mesmo se ja existir")
    args = ap.parse_args()

    alvos = args.apenas or list(FONTES)
    falhas = [k for k in alvos if not rodar(k, args.forcar)]
    print(f"\n  {len(alvos) - len(falhas)}/{len(alvos)} fontes ok"
          + (f" · falharam: {', '.join(falhas)}" if falhas else ""))
    # falha parcial nao interrompe o pipeline: as celulas saem com a feature nula
    # e a cobertura declara o buraco. Sai com 1 so se TODAS falharem.
    sys.exit(1 if falhas and len(falhas) == len(alvos) else 0)


if __name__ == "__main__":
    main()
