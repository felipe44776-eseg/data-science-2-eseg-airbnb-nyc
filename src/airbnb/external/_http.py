"""Acesso HTTP comum a todas as fontes externas.

Tres regras de convivencia com servico publico ficam aqui, para que nenhum
modulo de fonte precise lembrar delas:

* User-Agent que identifica o projeto — quem opera o servidor sabe quem somos;
* retry com backoff exponencial para 429/5xx e queda de conexao, sem martelar;
* nenhuma concorrencia: uma requisicao por vez.

E duas de integridade (invariante 5 — dado nao e versionado, manifesto com hash e):

* download vai para `.parcial` e so e renomeado no fim: conexao que cai nao deixa
  arquivo truncado com o nome certo, que a proxima execucao trataria como valido;
* todo artefato sai com bytes e SHA-256, para o manifesto.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from airbnb import config

USER_AGENT = "data-science-2-eseg-airbnb-nyc (projeto academico)"

#: status que justificam nova tentativa; 4xx restante e erro de consulta, nao de rede
STATUS_TRANSITORIOS = {429, 500, 502, 503, 504}

#: leitura em blocos de 1 MB
BLOCO = 1 << 20

_SESSAO: requests.Session | None = None


def sessao() -> requests.Session:
    """Sessao unica, com o User-Agent do projeto (reaproveita conexao TLS)."""
    global _SESSAO
    if _SESSAO is None:
        _SESSAO = requests.Session()
        _SESSAO.headers.update({"User-Agent": USER_AGENT})
    return _SESSAO


def agora() -> str:
    """Instante UTC em ISO 8601 — data de acesso gravada no manifesto."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def relativo(caminho: Path) -> str:
    """Caminho relativo a raiz, com barra normal (o manifesto roda em Windows e Linux)."""
    try:
        return Path(caminho).resolve().relative_to(config.RAIZ).as_posix()
    except ValueError:
        return Path(caminho).as_posix()


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with Path(caminho).open("rb") as fh:
        for b in iter(lambda: fh.read(BLOCO), b""):
            h.update(b)
    return h.hexdigest()


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def obter(url: str, *, params: dict | None = None, metodo: str = "GET",
          data: dict | None = None, headers: dict | None = None,
          timeout: float = 120, tentativas: int = 5, espera: float = 5.0,
          stream: bool = False) -> requests.Response:
    """GET/POST com retry e backoff exponencial (5 s, 10 s, 20 s, ...).

    Honra `Retry-After` quando o servidor manda (Overpass e Socrata mandam em 429).
    Erro 4xx que nao seja 429 sobe na hora: e consulta errada, repetir nao ajuda.
    """
    ultimo: Exception | None = None
    for k in range(tentativas):
        try:
            r = sessao().request(metodo, url, params=params, data=data, headers=headers,
                                 timeout=(30, timeout), stream=stream)
            if r.status_code in STATUS_TRANSITORIOS:
                pausa = float(r.headers.get("Retry-After") or espera * 2 ** k)
                ultimo = requests.HTTPError(f"HTTP {r.status_code}", response=r)
                print(f"      HTTP {r.status_code} — nova tentativa em {pausa:.0f}s", flush=True)
                time.sleep(min(pausa, 300))
                continue
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            ultimo = e
            pausa = espera * 2 ** k
            print(f"      {type(e).__name__} — nova tentativa em {pausa:.0f}s", flush=True)
            time.sleep(pausa)
    raise RuntimeError(f"falhou apos {tentativas} tentativas: {url}") from ultimo


def baixar_arquivo(url: str, destino: Path, *, timeout: float = 90,
                   tentativas: int = 4) -> dict:
    """Baixa `url` para `destino` via `.parcial`; devolve a entrada do manifesto."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    r = obter(url, timeout=timeout, stream=True, tentativas=tentativas)
    with parcial.open("wb") as fh:
        for bloco in r.iter_content(BLOCO):
            fh.write(bloco)
    parcial.replace(destino)
    return artefato(destino, url=url)


def artefato(caminho: Path, **extra) -> dict:
    """Entrada de manifesto para um arquivo ja gravado."""
    caminho = Path(caminho)
    return {"arquivo": relativo(caminho), "bytes": caminho.stat().st_size,
            "sha256": sha256_arquivo(caminho), "acessado_em": agora(), **extra}


def socrata_csv(dominio: str, dataset: str, *, select: str, where: str, destino: Path,
                ordem: str = ":id", pagina: int = 50_000, timeout: float = 900) -> dict:
    """Resultado inteiro de uma consulta SoQL, paginado, gravado num CSV.

    Cada pagina vai para um arquivo proprio em `<destino>.paginas/`: se a conexao
    cair na pagina 15, a proxima execucao retoma dali em vez de refazer 14
    consultas (a primeira pagina do NYPD Historic leva minutos — o servidor varre
    10 milhoes de linhas antes de responder). `$order=:id` torna a paginacao
    estavel. So no fim as paginas viram um CSV unico, com hash.
    """
    destino = Path(destino)
    pasta = destino.with_name(destino.name + ".paginas")
    pasta.mkdir(parents=True, exist_ok=True)
    url = f"https://{dominio}/resource/{dataset}.csv"
    params = {"$select": select, "$where": where, "$order": ordem, "$limit": pagina}

    k, total = 0, 0
    while True:
        arq = pasta / f"p{k:05d}.csv"
        if arq.exists():
            texto = arq.read_text(encoding="utf-8")
        else:
            t0 = time.time()
            r = obter(url, params={**params, "$offset": k * pagina}, timeout=timeout)
            texto = r.content.decode("utf-8")
            arq.write_text(texto, encoding="utf-8")
            print(f"      {dataset} pagina {k}: {texto.count(chr(10)) - 1:,} linhas "
                  f"em {time.time() - t0:.0f}s", flush=True)
        n = max(texto.count("\n") - 1, 0)
        total += n
        if n < pagina:
            break
        k += 1

    # junta as paginas mantendo um unico cabecalho
    partes = sorted(pasta.glob("p*.csv"))
    parcial = destino.with_name(destino.name + ".parcial")
    with parcial.open("w", encoding="utf-8", newline="") as fh:
        for i, p in enumerate(partes):
            linhas = p.read_text(encoding="utf-8").splitlines(keepends=True)
            fh.writelines(linhas if i == 0 else linhas[1:])
    parcial.replace(destino)
    shutil.rmtree(pasta, ignore_errors=True)
    return artefato(destino, url=url, parametros={k_: v for k_, v in params.items()
                                                  if k_ != "$limit"},
                    registros=total, paginas=len(partes))


def ler_csv_texto(texto: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(texto))
