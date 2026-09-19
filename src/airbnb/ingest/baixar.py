"""Fontes primarias do Airbnb: baixa o que falta e CONFERE o hash de tudo.

Invariante 5: dado nao e versionado, manifesto com hash e. O manifesto
(`data/raw/_manifesto.json`) e a referencia: a primeira execucao REGISTRA
arquivo, URL, bytes, SHA-256, data de acesso e licenca; as seguintes
CONFEREM e ABORTAM se um hash divergir. Registrar sem conferir nao prova nada
— se o Inside Airbnb republicar o arquivo com outro conteudo na mesma URL (ja
aconteceu de uma coleta ser refeita), todo numero a jusante mudaria em
silencio e o manifesto seria reescrito com o hash novo sem ninguem notar.

Duas origens:

* **Inside Airbnb** (CC BY 4.0) — snapshot `config.SNAPSHOT_ATUAL`, baixado da
  URL publica. O snapshot de 2019 NAO e publico (a URL de arquivo responde
  403), por isso 2019 vem do Kaggle.
* **Kaggle** `dgomonov/new-york-city-airbnb-open-data` (CC0) — exige conta.
  Ordem de tentativa: arquivo ja presente -> `--kaggle CAMINHO` (arquivo,
  pasta ou .zip baixado a mao) -> API do Kaggle com credencial
  (`KAGGLE_USERNAME`/`KAGGLE_KEY` ou `~/.kaggle/kaggle.json`) -> erro com a
  instrucao de onde baixar.

Uso:
    python -m airbnb.ingest.baixar                    # baixa o que falta e confere tudo
    python -m airbnb.ingest.baixar --verificar        # so confere; nao baixa
    python -m airbnb.ingest.baixar --forcar           # rebaixa tudo (e confere contra o manifesto)
    python -m airbnb.ingest.baixar --kaggle ~/Downloads/archive.zip
    python -m airbnb.ingest.baixar --aceitar-fonte-nova   # troca DELIBERADA de versao
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from airbnb import config
from airbnb.produto.autoria import REPOSITORIO

MANIFESTO = config.RAW / "_manifesto.json"

#: Leitura em blocos: o calendario tem 26 MB comprimido; nada precisa caber inteiro na memoria.
BLOCO = 8 << 20

#: O Inside Airbnb pede que coleta automatizada se identifique. Identificar o
#: projeto (e onde encontra-lo) e a cortesia minima com quem mantem o dado aberto.
USER_AGENT = f"airbnb-nyc-eseg/0.1 (projeto academico ESEG; {REPOSITORIO})"

LICENCA_INSIDE = ("CC BY 4.0 — Inside Airbnb (insideairbnb.com), Murray Cox. "
                  "Atribuição obrigatória em toda superfície publicada.")
LICENCA_KAGGLE = "CC0 1.0 (domínio público) — Kaggle dgomonov/new-york-city-airbnb-open-data, versão 3"

KAGGLE_PAGINA = f"https://www.kaggle.com/datasets/{config.KAGGLE_DATASET}"
KAGGLE_API = f"https://www.kaggle.com/api/v1/datasets/download/{config.KAGGLE_DATASET}/AB_NYC_2019.csv"


@dataclass(frozen=True)
class Fonte:
    """Um arquivo de origem. `url` e de onde o arquivo vem (para o Kaggle, a
    pagina do dataset: o download exige autenticacao). `usada_no_pipeline=False`
    marca o que e baixado e conferido mas nao entra na limpeza (ver FONTES.md)."""

    chave: str
    destino: Path
    url: str
    licenca: str
    descricao: str
    usada_no_pipeline: bool = True


def _inside(caminho: str) -> str:
    return f"{config.INSIDE_AIRBNB_BASE}/{config.SNAPSHOT_ATUAL}/{caminho}"


_DIR = config.RAW_INSIDE

FONTES: list[Fonte] = [
    Fonte("kaggle_ab_nyc_2019", config.RAW_KAGGLE, KAGGLE_PAGINA, LICENCA_KAGGLE,
          "resumo de 2019 (scrape de 2019-07-08): 48.895 × 16"),
    Fonte("insideairbnb_listings", _DIR / "listings.csv.gz", _inside("data/listings.csv.gz"),
          LICENCA_INSIDE, "detalhado de 2026: 30.259 × 90"),
    Fonte("insideairbnb_listings_resumo", _DIR / "listings_resumo.csv",
          _inside("visualisations/listings.csv"), LICENCA_INSIDE,
          "resumo de 2026: 30.555 × 19 (conferência do detalhado)"),
    Fonte("insideairbnb_reviews_resumo", _DIR / "reviews_resumo.csv",
          _inside("visualisations/reviews.csv"), LICENCA_INSIDE,
          "avaliações de 2026: listing_id, date (990.170 linhas)"),
    Fonte("insideairbnb_neighbourhoods_geojson", _DIR / "neighbourhoods.geojson",
          _inside("visualisations/neighbourhoods.geojson"), LICENCA_INSIDE,
          "polígonos dos bairros (233 feições, 230 bairros)"),
    Fonte("insideairbnb_neighbourhoods_csv", _DIR / "neighbourhoods.csv",
          _inside("visualisations/neighbourhoods.csv"), LICENCA_INSIDE,
          "lista bairro → distrito (230 linhas)"),
    Fonte("insideairbnb_calendar", _DIR / "calendar.csv.gz", _inside("data/calendar.csv.gz"),
          LICENCA_INSIDE,
          "calendário de 365 dias — FORA do pipeline: não tem mais coluna de preço", usada_no_pipeline=False),
]


# --- hash e manifesto -------------------------------------------------------------------


def sha256(caminho: Path) -> str:
    """SHA-256 do arquivo inteiro, lido em blocos."""
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for b in iter(lambda: fh.read(BLOCO), b""):
            h.update(b)
    return h.hexdigest()


def ler_manifesto(caminho: Path = MANIFESTO) -> dict:
    """Manifesto existente, ou esqueleto vazio. JSON corrompido e erro — nao
    pode ser lido como 'sem referencia', senao um manifesto estragado
    desligaria a conferencia em silencio."""
    if not caminho.exists():
        return {"arquivos": {}}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"manifesto ilegivel ({caminho}): {e}. Restaure-o do git.") from e


def gravar_manifesto(man: dict, caminho: Path = MANIFESTO) -> None:
    man["descricao"] = ("Fontes primárias do Airbnb. Gerado e CONFERIDO por "
                        "`python -m airbnb.ingest.baixar`; hash divergente aborta a ingestão.")
    man["snapshot_2019"] = config.SNAPSHOT_2019
    man["snapshot_atual"] = config.SNAPSHOT_ATUAL
    ordem = ["descricao", "snapshot_2019", "snapshot_atual", "arquivos"]
    saida = {k: man[k] for k in ordem if k in man}
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relativo(p: Path) -> str:
    try:
        return p.resolve().relative_to(config.RAIZ).as_posix()
    except ValueError:
        return p.as_posix()


def registro(f: Fonte, caminho: Path, acesso: str) -> dict:
    """Entrada do manifesto para um arquivo presente e integro."""
    return {
        "arquivo": _relativo(caminho),
        "url": f.url,
        "bytes": caminho.stat().st_size,
        "sha256": sha256(caminho),
        "acesso": acesso,
        "licenca": f.licenca,
        "conteudo": f.descricao,
        "usada_no_pipeline": f.usada_no_pipeline,
    }


def conferir(caminho: Path, esperado: dict | None) -> dict:
    """Compara o arquivo com a entrada do manifesto. Nao baixa nada.

    Estados: `ausente`, `sem-referencia` (primeira execucao), `ok`,
    `tamanho-errado`, `hash-errado`. O tamanho vem antes do hash porque e
    instantaneo e pega o caso comum (download interrompido).
    """
    if not caminho.exists():
        return {"estado": "ausente"}
    tam = caminho.stat().st_size
    if esperado is None:
        return {"estado": "sem-referencia", "bytes": tam}
    if tam != esperado["bytes"]:
        return {"estado": "tamanho-errado", "esperado": esperado["bytes"], "obtido": tam}
    obtido = sha256(caminho)
    if obtido != esperado["sha256"]:
        return {"estado": "hash-errado", "esperado": esperado["sha256"], "obtido": obtido}
    return {"estado": "ok", "bytes": tam}


# --- aquisicao ---------------------------------------------------------------------------


def _baixar_url(url: str, destino: Path, headers: dict | None = None) -> None:
    """Baixa para `.parcial` e so renomeia no fim: conexao que cai nao deixa
    arquivo truncado com o nome certo (a proxima execucao o trataria como valido)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    lidos = 0
    with urllib.request.urlopen(req, timeout=180) as r, parcial.open("wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        while bloco := r.read(BLOCO):
            fh.write(bloco)
            lidos += len(bloco)
            if total:
                print(f"\r    {lidos / 1e6:,.1f} / {total / 1e6:,.1f} MB", end="", flush=True)
    print()
    parcial.replace(destino)


def _extrair_csv_kaggle(origem: Path, destino: Path) -> None:
    """Aceita o CSV, a pasta que o contem ou o .zip do Kaggle (`archive.zip`)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origem.is_dir():
        candidatos = list(origem.rglob(destino.name))
        if not candidatos:
            raise SystemExit(f"  {destino.name} nao encontrado dentro de {origem}")
        origem = candidatos[0]
    if zipfile.is_zipfile(origem):
        with zipfile.ZipFile(origem) as z:
            nomes = [n for n in z.namelist() if n.endswith(destino.name)]
            if not nomes:
                raise SystemExit(f"  {destino.name} nao esta dentro de {origem}")
            with z.open(nomes[0]) as src, destino.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        return
    shutil.copyfile(origem, destino)


def _credencial_kaggle() -> tuple[str, str] | None:
    usuario, chave = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
    if usuario and chave:
        return usuario, chave
    arq = Path.home() / ".kaggle" / "kaggle.json"
    if arq.exists():
        cred = json.loads(arq.read_text(encoding="utf-8"))
        return cred.get("username"), cred.get("key")
    return None


def _baixar_kaggle_api(destino: Path, cred: tuple[str, str]) -> None:
    """Download autenticado pela API REST do Kaggle (sem o pacote `kaggle`).

    A resposta pode vir como CSV ou como zip, conforme o tamanho do arquivo.
    Caminho nao exercitado no ambiente de desenvolvimento (sem credencial) —
    a conferencia de hash contra o manifesto e o que garante o resultado.
    """
    token = base64.b64encode(f"{cred[0]}:{cred[1]}".encode()).decode()
    bruto = destino.with_name(destino.name + ".download")
    _baixar_url(KAGGLE_API, bruto, headers={"Authorization": f"Basic {token}"})
    with bruto.open("rb") as fh:
        e_zip = fh.read(2) == b"PK"
    if e_zip:
        with zipfile.ZipFile(io.BytesIO(bruto.read_bytes())) as z:
            nome = next(n for n in z.namelist() if n.endswith(destino.name))
            destino.write_bytes(z.read(nome))
        bruto.unlink()
    else:
        bruto.replace(destino)


def obter_kaggle(destino: Path, origem_local: Path | None) -> str:
    """Poe o CSV do Kaggle em `destino`. Devolve como foi obtido."""
    if origem_local is not None:
        if not origem_local.exists():
            raise SystemExit(f"  --kaggle aponta para caminho inexistente: {origem_local}")
        _extrair_csv_kaggle(origem_local, destino)
        return f"copiado de {origem_local}"
    cred = _credencial_kaggle()
    if cred:
        _baixar_kaggle_api(destino, cred)
        return "API do Kaggle"
    raise SystemExit(
        "  AB_NYC_2019.csv ausente e sem como obte-lo automaticamente.\n"
        f"    1. Baixe em {KAGGLE_PAGINA} (botao Download; exige conta, licenca CC0)\n"
        "    2. Rode:  python -m airbnb.ingest.baixar --kaggle <caminho do CSV, da pasta ou do .zip>\n"
        "    ou configure KAGGLE_USERNAME/KAGGLE_KEY (ou ~/.kaggle/kaggle.json) e rode de novo.\n"
        "    O hash do arquivo obtido e conferido contra data/raw/_manifesto.json."
    )


# --- orquestracao ----------------------------------------------------------------------------


def processar(f: Fonte, man: dict, *, verificar: bool, forcar: bool, aceitar_nova: bool,
              kaggle: Path | None) -> tuple[str, bool]:
    """Garante uma fonte. Devolve (linha de status, ok?). Atualiza `man` in-place
    so quando ha registro novo ou troca deliberada (`aceitar_nova`)."""
    esperado = man["arquivos"].get(f.chave)
    r = conferir(f.destino, esperado)

    if r["estado"] == "ok" and not forcar:
        return f"[ok]      {f.chave:38} {r['bytes']:>12,} bytes · hash confere", True

    if r["estado"] == "sem-referencia" and not forcar:
        # primeira execucao com o arquivo ja no disco: registra. A data de
        # acesso e a do arquivo (quando foi obtido), nao a de hoje.
        acesso = datetime.fromtimestamp(f.destino.stat().st_mtime).date().isoformat()
        man["arquivos"][f.chave] = registro(f, f.destino, acesso)
        return f"[registro] {f.chave:37} {r['bytes']:>12,} bytes · hash registrado", True

    if r["estado"] in ("tamanho-errado", "hash-errado") and not forcar:
        if aceitar_nova:
            man["arquivos"][f.chave] = registro(f, f.destino, date.today().isoformat())
            return f"[TROCA]   {f.chave:38} versao nova aceita deliberadamente", True
        return (f"[{r['estado'].upper()}] {f.chave}\n"
                f"            esperado {r['esperado']}\n            obtido   {r['obtido']}\n"
                "            A FONTE MUDOU. Nada a jusante roda com dado diferente do manifesto.\n"
                "            Troca deliberada: --aceitar-fonte-nova (e reprocessar tudo)."), False

    if verificar:
        return f"[{r['estado'].upper()}] {f.chave:38} {_relativo(f.destino)}", False

    # ausente, ou --forcar: obtem de novo e confere o que chegou
    print(f"  obtendo {f.chave}…")
    if f.chave.startswith("kaggle"):
        como = obter_kaggle(f.destino, kaggle)
    else:
        _baixar_url(f.url, f.destino)
        como = "baixado"
    r2 = conferir(f.destino, esperado)
    if r2["estado"] == "sem-referencia" or (aceitar_nova and r2["estado"] != "ok"):
        man["arquivos"][f.chave] = registro(f, f.destino, date.today().isoformat())
        return f"[registro] {f.chave:37} {como}; hash registrado", True
    if r2["estado"] != "ok":
        return (f"[{r2['estado'].upper()}] {f.chave} ({como})\n"
                f"            esperado {r2.get('esperado')}\n            obtido   {r2.get('obtido')}\n"
                "            O ARQUIVO OBTIDO NAO E O DO MANIFESTO — nao use."), False
    return f"[ok]      {f.chave:38} {como}; hash confere", True


def main(argv: list[str] | None = None) -> int:
    """Baixa o que falta, confere tudo e sai com 1 se algo divergir."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verificar", action="store_true", help="so confere o que existe; nao baixa")
    ap.add_argument("--forcar", action="store_true", help="rebaixa tudo e confere contra o manifesto")
    ap.add_argument("--kaggle", type=Path, metavar="CAMINHO",
                    help="CSV, pasta ou .zip do Kaggle baixado a mao")
    ap.add_argument("--aceitar-fonte-nova", action="store_true",
                    help="aceita hash diferente do manifesto e o reescreve (troca deliberada)")
    args = ap.parse_args(argv)

    man = ler_manifesto()
    antes = json.dumps(man, sort_keys=True)
    problemas: list[str] = []
    print(f"  manifesto: {_relativo(MANIFESTO)} "
          f"({len(man['arquivos'])} registros)" if man["arquivos"] else "  manifesto: novo")
    for f in FONTES:
        linha, ok = processar(f, man, verificar=args.verificar, forcar=args.forcar,
                              aceitar_nova=args.aceitar_fonte_nova, kaggle=args.kaggle)
        print("  " + linha.replace(",", "."))
        if not ok:
            problemas.append(f.chave)

    # o manifesto so e regravado sem problema pendente: com hash divergente ele
    # e a prova do que era esperado e nao pode ser sobrescrito.
    if not problemas and json.dumps(man, sort_keys=True) != antes:
        gravar_manifesto(man)
        print(f"\n  manifesto atualizado: {_relativo(MANIFESTO)}")

    if problemas:
        print(f"\n  PENDENTE: {', '.join(problemas)}")
        return 1
    print("\n  Fontes primarias presentes e integras.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
