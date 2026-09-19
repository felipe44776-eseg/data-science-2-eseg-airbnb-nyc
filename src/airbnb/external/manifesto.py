"""Manifesto das fontes externas — `data/external/_manifesto_externos.json`.

O dado baixado nao vai para o git (invariante 5); o manifesto vai. Ele e o que
permite provar, meses depois, QUAL arquivo gerou cada numero publicado: URL,
parametros da consulta, data de acesso, bytes e SHA-256.

Fonte que falhou tambem entra, com o erro — ausencia silenciosa seria pior que
ausencia documentada.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from airbnb import config
from airbnb.external._http import USER_AGENT, agora

CAMINHO = config.EXTERNAL / "_manifesto_externos.json"


def ler(caminho: Path = CAMINHO) -> dict:
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {"fontes": {}}


@contextmanager
def _trava(caminho: Path, espera_max: float = 60):
    """Trava por arquivo: duas coletas em paralelo (fontes em servidores
    diferentes) nao podem ler-modificar-gravar o manifesto ao mesmo tempo."""
    trava = caminho.with_name(caminho.name + ".lock")
    t0 = time.time()
    while True:
        try:
            fd = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - t0 > espera_max:
                trava.unlink(missing_ok=True)  # trava orfa de execucao interrompida
                continue
            time.sleep(0.2)
    try:
        yield
    finally:
        os.close(fd)
        trava.unlink(missing_ok=True)


def registrar(chave: str, registro: dict, caminho: Path = CAMINHO) -> None:
    """Grava/atualiza a entrada de uma fonte e regrava o manifesto inteiro."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with _trava(caminho):
        m = ler(caminho)
        m["atualizado_em"] = agora()
        m["user_agent"] = USER_AGENT
        m.setdefault("fontes", {})[chave] = registro
        m["fontes"] = dict(sorted(m["fontes"].items()))
        caminho.write_text(json.dumps(m, ensure_ascii=False, indent=2, default=str) + "\n",
                           encoding="utf-8")


def anterior(chave: str, caminho: Path = CAMINHO) -> dict:
    """Registro previo de uma fonte (para preservar URL e data de acesso ao pular)."""
    return ler(caminho).get("fontes", {}).get(chave, {})
