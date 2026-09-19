"""E9 — Marcos da cidade: curadoria documentada de coordenadas.

Por que curadoria e nao consulta: sao sete pontos que nao mudam. Fixa-los no
codigo torna a feature deterministica e testavel sem rede. A coleta apenas
CONFERE cada coordenada contra a API da Wikipedia e grava o desvio em metros no
manifesto — se alguem editar um numero errado aqui, a conferencia acusa.

Coordenadas: infobox da Wikipedia em ingles (acesso 2026-09-18), que para estes
marcos cita o GNIS/USGS ou o operador (Port Authority, no caso dos aeroportos).
Central Park = ponto que a Wikipedia usa como centro do parque.

Uso das features:
  dist_centro_km    -> Times Square (centro turistico e comercial convencional)
  dist_aeroporto_km -> min(JFK, LGA) — o aeroporto mais proximo, nao o maior
  dist_marco_km     -> min dos cinco marcos turisticos (Times Square, Empire State,
                       Central Park, One WTC, Brooklyn Bridge)
"""

from __future__ import annotations

import json
import math

from airbnb import config
from airbnb.external._http import agora, artefato, obter

PASTA = config.EXTERNAL / "marcos"
ARQUIVO = PASTA / "marcos.json"
API_WIKI = "https://en.wikipedia.org/w/api.php"

#: nome -> (lat, lon, titulo na Wikipedia, tipo)
MARCOS: dict[str, tuple[float, float, str, str]] = {
    "Times Square": (40.7575, -73.9858, "Times Square", "centro"),
    "Empire State Building": (40.7483, -73.9856, "Empire State Building", "turistico"),
    "Central Park": (40.782222, -73.965278, "Central Park", "turistico"),
    "One World Trade Center": (40.713056, -74.013333, "One World Trade Center", "turistico"),
    "Brooklyn Bridge": (40.7057, -73.9964, "Brooklyn Bridge", "turistico"),
    "JFK": (40.639722, -73.778889, "John F. Kennedy International Airport", "aeroporto"),
    "LGA": (40.775, -73.875, "LaGuardia Airport", "aeroporto"),
}

CENTRO = "Times Square"
AEROPORTOS = ("JFK", "LGA")
TURISTICOS = tuple(k for k, v in MARCOS.items() if v[3] in ("centro", "turistico"))

META = {
    "titulo": "Marcos da cidade (curadoria, conferida na Wikipedia)",
    "orgao": "Wikipedia (coordenadas de infobox; GNIS/USGS e Port Authority como origem)",
    "licenca": "CC BY-SA 4.0 (texto da Wikipedia); coordenadas sao fato, nao obra",
    "atribuicao": "Coordenadas conferidas na Wikipedia (en.wikipedia.org), CC BY-SA 4.0.",
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia em metros na esfera — usada so para conferir a curadoria."""
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def coletar(forcar: bool = False) -> dict:
    """Grava os marcos e confere cada um contra a Wikipedia (se ela responder)."""
    PASTA.mkdir(parents=True, exist_ok=True)
    conferencia = {}
    try:
        titulos = "|".join(v[2] for v in MARCOS.values())
        r = obter(API_WIKI, params={"action": "query", "prop": "coordinates",
                                    "titles": titulos, "format": "json",
                                    "redirects": 1}, timeout=30, tentativas=2)
        paginas = r.json()["query"]["pages"].values()
        por_titulo = {p["title"]: p.get("coordinates", [{}])[0] for p in paginas}
        for nome, (lat, lon, titulo, _) in MARCOS.items():
            c = por_titulo.get(titulo, {})
            if "lat" in c:
                conferencia[nome] = {"wikipedia": [c["lat"], c["lon"]],
                                     "desvio_m": round(haversine_m(lat, lon, c["lat"],
                                                                   c["lon"]), 1)}
            else:
                conferencia[nome] = {"wikipedia": None, "desvio_m": None}
    except Exception as e:  # noqa: BLE001 — conferencia opcional; curadoria segue valendo
        conferencia = {"erro": f"{type(e).__name__}: {e}"}

    dados = {"acessado_em": agora(), "fonte": "curadoria (ver src/airbnb/external/marcos.py)",
             "marcos": [{"nome": k, "lat": v[0], "lon": v[1], "wikipedia": v[2],
                         "tipo": v[3]} for k, v in MARCOS.items()],
             "conferencia_wikipedia": conferencia}
    ARQUIVO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    desvios = [c.get("desvio_m") for c in conferencia.values()
               if isinstance(c, dict) and c.get("desvio_m") is not None]
    return {**META, "estado": "ok",
            "artefatos": [artefato(ARQUIVO, url=API_WIKI,
                                   parametros={"prop": "coordinates"})],
            "resumo": {"n_marcos": len(MARCOS),
                       "maior_desvio_m": max(desvios) if desvios else None,
                       "conferencia": conferencia}}
