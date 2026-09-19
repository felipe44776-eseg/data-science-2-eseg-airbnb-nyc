"""E8 — Pontos de interesse do OpenStreetMap (Overpass API).

Pergunta de negocio: o que ha EM VOLTA do anuncio — restaurantes, bares, cafes,
atracoes, hoteis, parques? E o "a pe" que o hospede compra junto com a cama.
Hotel e a concorrencia formal do Airbnb; entra pelo mesmo motivo.

Uma consulta por grupo, no envelope de NYC alargado em ~1 km (0,01 grau) — sem a
folga, a celula da divisa com Nassau/Westchester perderia os POIs do outro lado.
`out center` da o centro de way/relation (restaurante mapeado como predio).

Licenca ODbL 1.0: atribuicao obrigatoria "(c) OpenStreetMap contributors" em
qualquer produto que exiba ou derive do dado — o site reproduz o credito.

Anacronismo declarado: os POIs sao os de HOJE, aplicados tambem a 2019. O
OSM nao tem um "estado em 2019" acessivel sem baixar o historico completo.
Restaurante que fechou na pandemia conta em 2019 so se ainda estiver mapeado.
Viés: o OSM e colaborativo; Manhattan e Brooklyn estao mais bem mapeados que o
Bronx e Staten Island — densidade de POI mede tambem densidade de mapeador.
"""

from __future__ import annotations

import json
import time

import pandas as pd

from airbnb import config
from airbnb.external._http import artefato, obter

ENDPOINTS = ("https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter")

#: grupo -> (chave OSM, valores). Um grupo = uma consulta = uma feature poi_<grupo>_k1.
GRUPOS: dict[str, tuple[str, tuple[str, ...]]] = {
    "restaurantes": ("amenity", ("restaurant", "fast_food")),
    "cafes": ("amenity", ("cafe",)),
    "bares": ("amenity", ("bar", "pub", "nightclub")),
    "atracoes": ("tourism", ("attraction", "museum", "gallery", "viewpoint")),
    "hoteis": ("tourism", ("hotel", "hostel", "guest_house")),
    "parques": ("leisure", ("park",)),
}

FOLGA_GRAUS = 0.01
TIMEOUT_SERVIDOR = 85

PASTA = config.EXTERNAL / "osm"

META = {
    "titulo": "OpenStreetMap — POIs via Overpass API",
    "orgao": "OpenStreetMap Foundation / contribuidores do OpenStreetMap",
    "licenca": "Open Database License (ODbL) 1.0 — atribuicao e compartilhamento pela mesma licenca",
    "atribuicao": "Dados de pontos de interesse (c) OpenStreetMap contributors, ODbL 1.0 "
                  "(openstreetmap.org/copyright).",
}


def envelope() -> tuple[float, float, float, float]:
    """(sul, oeste, norte, leste) — a ordem que o Overpass espera."""
    lon0, lat0, lon1, lat1 = config.NYC_BBOX
    f = FOLGA_GRAUS
    return (lat0 - f, lon0 - f, lat1 + f, lon1 + f)


def consulta(chave: str, valores: tuple[str, ...]) -> str:
    s, w, n, e = envelope()
    bbox = f"{s},{w},{n},{e}"
    regex = "^(" + "|".join(valores) + ")$"
    corpo = "".join(f'{t}["{chave}"~"{regex}"]({bbox});' for t in ("node", "way", "relation"))
    return f"[out:json][timeout:{TIMEOUT_SERVIDOR}];({corpo});out center qt;"


def parse(dados: dict, grupo: str, chave: str) -> pd.DataFrame:
    """Elementos do Overpass -> (grupo, tipo, id, valor, lat, lon). Sem coordenada sai."""
    linhas = []
    for el in dados.get("elements", []):
        if "lat" in el:
            lat, lon = el["lat"], el["lon"]
        elif "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue
        linhas.append({"grupo": grupo, "tipo": el.get("type"), "id": el.get("id"),
                       "valor": el.get("tags", {}).get(chave), "lat": lat, "lon": lon})
    return pd.DataFrame(linhas, columns=["grupo", "tipo", "id", "valor", "lat", "lon"])


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    artefatos, resumo = [], {}
    for grupo, (chave, valores) in GRUPOS.items():
        destino = PASTA / f"{grupo}.json"
        q = consulta(chave, valores)
        if destino.exists() and not forcar:
            artefatos.append(artefato(destino, url=ENDPOINTS[0], consulta=q, nota="ja existia"))
        else:
            ultimo = None
            for url in ENDPOINTS:
                try:
                    r = obter(url, metodo="POST", data={"data": q}, timeout=90,
                              tentativas=3, espera=15)
                    dados = r.json()
                    if dados.get("remark", "").lower().startswith("runtime error"):
                        raise RuntimeError(dados["remark"])
                    destino.write_bytes(r.content)
                    artefatos.append(artefato(destino, url=url, consulta=q,
                                              osm_base=dados.get("osm3s", {}).get(
                                                  "timestamp_osm_base")))
                    break
                except Exception as e:  # noqa: BLE001 — tenta o espelho
                    ultimo = e
                    print(f"      {grupo}: {url} falhou ({type(e).__name__}); proximo espelho",
                          flush=True)
            else:
                raise RuntimeError(f"Overpass indisponivel para {grupo}") from ultimo
            time.sleep(5)  # intervalo entre consultas: o Overpass limita por IP
        dados = json.loads(destino.read_bytes())
        df = parse(dados, grupo, chave)
        resumo[grupo] = {"elementos": int(len(df)),
                         "osm_base": dados.get("osm3s", {}).get("timestamp_osm_base"),
                         "por_valor": df["valor"].value_counts().to_dict(),
                         "por_tipo": df["tipo"].value_counts().to_dict()}
        print(f"    OSM {grupo}: {len(df):,} elementos", flush=True)
    # Espelho do Overpass pode estar semanas atras do principal (em 2026-09-19 o
    # kumi.systems servia a base de 2026-06-01). Grupos de datas diferentes nao sao
    # comparaveis entre si: a divergencia fica registrada, nao escondida.
    bases = [pd.Timestamp(r["osm_base"]) for r in resumo.values() if r["osm_base"]]
    coerentes = bool(bases) and (max(bases) - min(bases)) <= pd.Timedelta(days=1)
    if not coerentes:
        print("    ATENCAO: grupos do OSM com bases de datas diferentes — ver manifesto")
    return {**META, "estado": "ok", "artefatos": artefatos,
            "resumo": {"envelope_sul_oeste_norte_leste": envelope(),
                       "bases_coerentes": coerentes, "grupos": resumo}}


def carregar() -> pd.DataFrame | None:
    """Todos os POIs (grupo, lat, lon, ...); None se algum grupo faltar."""
    partes = []
    for grupo, (chave, _) in GRUPOS.items():
        p = PASTA / f"{grupo}.json"
        if not p.exists():
            return None
        partes.append(parse(json.loads(p.read_bytes()), grupo, chave))
    return pd.concat(partes, ignore_index=True)
