# Como reproduzir

Escrito para quem não estava lá — outro integrante, a banca, ou você daqui a seis
meses. **Nada aqui depende de contexto de conversa**: se `.\tasks.ps1 status` fechar
com todas as etapas `ok`, o que está publicado reflete o dado atual.

## Pré-requisitos

| | |
|---|---|
| Python | **3.11** (as versões de `requirements.txt` foram testadas nela) |
| Node | 18+ — **só** para a paridade Python ↔ JavaScript; sem dependência de npm |
| Shell | PowerShell 7 — `tasks.ps1` é PowerShell |
| Disco | ~1 GB (fontes + Parquet derivado) |
| Rede | Inside Airbnb, US Census, NYC Open Data, data.ny.gov, Zillow, FRED, Overpass (OSM) |

## Passo a passo

```powershell
git clone https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc.git
cd data-science-2-eseg-airbnb-nyc

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

O arquivo do Kaggle **não tem download anônimo**: baixe `AB_NYC_2019.csv` em
<https://www.kaggle.com/datasets/dgomonov/new-york-city-airbnb-open-data>
(ou com a CLI `kaggle datasets download dgomonov/new-york-city-airbnb-open-data`,
se você tiver credencial) e coloque em `data/raw/kaggle/AB_NYC_2019.csv`.
O hash esperado está em `data/raw/_manifesto.json` — um arquivo diferente aborta
a ingestão, de propósito.

```powershell
.\tasks.ps1 dados      # baixa o snapshot do Inside Airbnb e confere o SHA-256 de tudo
.\tasks.ps1 all        # dados -> limpeza -> externos -> células -> modelos -> site -> docs
.\tasks.ps1 status     # todas as etapas têm de fechar ok
.\tasks.ps1 test       # ruff + pytest
.\tasks.ps1 servir     # site + documentação em http://localhost:8000
```

Cada etapa isolada tem verbo próprio (`.\tasks.ps1 help`).

## O que não vem no git, e por quê

**Dado não é versionado; manifesto com hash é** (invariante 5).

| insumo | como obter |
|---|---|
| `AB_NYC_2019.csv` (Kaggle, CC0) | download manual (acima) |
| snapshot Inside Airbnb NYC (CC BY 4.0) | `.\tasks.ps1 dados` |
| fontes externas (Census, NYPD, MTA, 311, Zillow, CPI, OSM) | `.\tasks.ps1 externos` |

O que **vem** no git: resultados (`data/**/_*.json`), os dados agregados do site
(`site/data/`), código, documentação.

## Se `status` não fechar

| aparece | significa | fazer |
|---|---|---|
| `ausente` | a etapa nunca rodou | rodar o verbo dela |
| `obsoleto` | uma entrada (dado **ou código**) mudou depois da última execução | rodar de novo; o `status` diz qual entrada |
| `ok`, mas número diferente do publicado | a fonte mudou na origem | `.\tasks.ps1 dados --verificar` antes de qualquer coisa |

## Atualizar para um snapshot mais novo do Inside Airbnb

1. Ver a data do snapshot de NYC mais recente em <https://insideairbnb.com/get-the-data/>.
2. Trocar `SNAPSHOT_ATUAL` em `src/airbnb/config.py`.
3. `.\tasks.ps1 dados --forcar` e `.\tasks.ps1 all`.
4. Revisar os documentos cujos números mudaram (eles leem os `_*.json`) e fazer commit
   de `site/data/`.
