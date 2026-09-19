"""Leitor minimo de XLSX (zip + XML), sem openpyxl.

Por que nao `pandas.read_excel`: exigiria `openpyxl`, que nao esta em
`requirements.txt` (arquivo compartilhado). O XLSX e um formato aberto (ECMA-376):
um zip com o XML de cada aba e uma tabela de textos compartilhados. Para ler
tabelas simples de relatorio — que e o caso dos relatorios da OSE — bastam 40
linhas e nenhuma dependencia nova.

Devolve cada aba como lista de linhas; cada linha e a lista de valores das
celulas NAO vazias, na ordem das colunas (texto, ou numero como texto).
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

_M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS = {"m": _M, "r": _R}


def _textos_compartilhados(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{{{_M}}}t"))
            for si in raiz.findall("m:si", _NS)]


def ler_abas(conteudo: bytes) -> dict[str, list[list[str]]]:
    z = zipfile.ZipFile(io.BytesIO(conteudo))
    textos = _textos_compartilhados(z)
    livro = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    alvo = {r.get("Id"): r.get("Target") for r in rels}
    abas: dict[str, list[list[str]]] = {}
    for aba in livro.find("m:sheets", _NS):
        caminho = alvo[aba.get(f"{{{_R}}}id")].lstrip("/")
        caminho = caminho if caminho.startswith("xl/") else "xl/" + caminho
        linhas = []
        for row in ET.fromstring(z.read(caminho)).iter(f"{{{_M}}}row"):
            valores = []
            for c in row.findall("m:c", _NS):
                v, tipo = c.find("m:v", _NS), c.get("t")
                if tipo == "s" and v is not None:
                    valores.append(textos[int(v.text)])
                elif tipo == "inlineStr":
                    valores.append("".join(x.text or "" for x in c.iter(f"{{{_M}}}t")))
                elif v is not None and v.text not in (None, ""):
                    valores.append(v.text)
            linhas.append([x for x in valores if str(x).strip() != ""])
        abas[aba.get("name")] = linhas
    return abas
