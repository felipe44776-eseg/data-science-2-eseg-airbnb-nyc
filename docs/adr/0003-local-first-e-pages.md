# ADR 0003 — Local-first; site estático no GitHub Pages, sem backend

**Status:** aceito · **Data:** 2026-09-18

## Contexto
O maior insumo é o snapshot detalhado do Inside Airbnb (16 MB comprimido); as fontes
externas somam algumas dezenas de MB. A tabela de modelagem cabe em memória com folga.
O entregável público precisa de um mapa e de um simulador acessíveis por link, para
banca e público, sem custo recorrente.

## Decisão
- Pipeline **local** (Python + Parquet), orquestrado por `tasks.ps1`. Nenhum recurso
  de nuvem provisionado. A config gcloud `eseg` existe, mas não é usada.
- Site **estático** no GitHub Pages: HTML/CSS/JS + JSON gerados pelo pipeline e
  versionados em `site/data/`. A documentação (MkDocs) é publicada junto, em `/docs/`.
- O CI **não** reconstrói os dados: publica o que foi gerado e verificado localmente
  (mesma decisão do projeto anterior do grupo). O CI roda lint, testes e a paridade JS.

## Consequências
- Custo zero, sem credencial, sem risco de contaminação entre tenants.
- Atualizar o site para um snapshot novo do Inside Airbnb = trocar `SNAPSHOT_ATUAL`,
  rodar `.\tasks.ps1 all` e fazer commit de `site/data/`.

**Gatilhos que reabrem:** (1) atualização trimestral automática dos dados; (2) modelo
grande demais para o navegador; (3) consumo por API de terceiros. Nesses casos, a
arquitetura seria Cloud Run Job + Cloud Scheduler no tenant **ESEG**
(`southamerica-east1`), nunca sob conta de cliente.
