<#
.SYNOPSIS
    Orquestrador do projeto. Um comando reconstroi tudo a partir das fontes.

.DESCRIPTION
    Cada verbo e uma etapa do CRISP-DM. Toda execucao e registrada em
    reports/execucao.jsonl (inicio, fim, duracao, erro). `.\tasks.ps1 status`
    diz o que rodou, o que esta obsoleto e o que falta.

    Usa o Python de .venv quando existir; senao, o do PATH.

.EXAMPLE
    .\tasks.ps1 dados        # baixa e confere o hash das fontes primarias
    .\tasks.ps1 all          # fontes -> limpeza -> externos -> modelos -> site
    .\tasks.ps1 test         # ruff + pytest
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('status', 'log', 'dados', 'limpeza', 'externos', 'celulas', 'features',
                 'comparativo', 'espacial', 'preco', 'ocupacao', 'sobrevivencia', 'deriva',
                 'figuras', 'site', 'notebooks', 'docs', 'servir', 'test', 'all', 'help')]
    [string]$Task = 'help',

    # repassados a etapa (ex.: dados --verificar, externos --apenas acs)
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Extra = @()
)

$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = "$PSScriptRoot\src"
$env:PYTHONIOENCODING = 'utf-8'

$VenvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$PY = if (Test-Path $VenvPy) { $VenvPy } else { 'python' }

$KAGGLE = 'data/raw/kaggle/AB_NYC_2019.csv'
$LOG    = Join-Path $PSScriptRoot 'reports/execucao.jsonl'

function Write-Log($etapa, $evento, $extra) {
    $reg = [ordered]@{
        ts     = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
        etapa  = $etapa
        evento = $evento
        pid    = $PID
    }
    if ($extra) { foreach ($k in $extra.Keys) { $reg[$k] = $extra[$k] } }
    $dir = Split-Path $LOG -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    ($reg | ConvertTo-Json -Compress) | Add-Content -Path $LOG -Encoding utf8
}

# Envelopa uma etapa: registra inicio/fim, cronometra e propaga a falha.
function Invoke-Etapa($chave, $titulo, [scriptblock]$corpo) {
    Write-Host "==> $titulo" -ForegroundColor Cyan
    Write-Log $chave 'inicio' @{ detalhe = $titulo }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        & $corpo
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "saida $LASTEXITCODE" }
        $sw.Stop()
        $s = [math]::Round($sw.Elapsed.TotalSeconds, 1)
        Write-Log $chave 'fim' @{ segundos = $s }
        Write-Host "    concluido em ${s}s" -ForegroundColor DarkGray
    }
    catch {
        $sw.Stop()
        Write-Log $chave 'erro' @{
            segundos = [math]::Round($sw.Elapsed.TotalSeconds, 1)
            detalhe  = $_.Exception.Message
        }
        Write-Host "    FALHOU: $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

# --- etapas (uma por fase do CRISP-DM) ---------------------------------------

# Fase 2 — entendimento dos dados
function Invoke-Dados {
    Invoke-Etapa 'dados' 'Fontes primarias: Kaggle 2019 + Inside Airbnb atual (hash conferido)' {
        & $PY -m airbnb.ingest.baixar @Extra
    }
}

# Fase 3 — preparacao
function Invoke-Limpeza {
    Invoke-Etapa 'limpeza' 'Limpeza: bronze -> silver, quarentena e perguntas da equipe' {
        & $PY -m airbnb.clean.pipeline
    }
}

function Invoke-Externos {
    Invoke-Etapa 'externos' 'Fontes externas: ACS, NYPD, MTA, 311, Zillow, CPI, OSM' {
        & $PY -m airbnb.external.coletar @Extra
    }
}

function Invoke-Celulas {
    Invoke-Etapa 'celulas' 'Celulas H3 r9 com features de localizacao' {
        & $PY -m airbnb.features.celulas
    }
}

function Invoke-Features {
    Invoke-Etapa 'features' 'Tabelas de modelagem: anuncio x celula' {
        & $PY -m airbnb.features.anuncios
    }
}

# Fases 2/5 — analise comparativa e testes espaciais
function Invoke-Comparativo {
    Invoke-Etapa 'comparativo' 'Comparativo 2019 -> atual (precos reais, LL18)' {
        & $PY -m airbnb.eda.comparativo
    }
}

function Invoke-Espacial {
    Invoke-Etapa 'espacial' 'Testes de localizacao: Moran global, LISA, Kruskal-Wallis' {
        & $PY -m airbnb.eda.espacial
    }
}

# Fase 4 — modelagem
function Invoke-Preco {
    Invoke-Etapa 'preco' 'Modelo de preco: escada, CV espacial, conformal, SHAP' {
        & $PY -m airbnb.models.preco
    }
}

function Invoke-Ocupacao {
    Invoke-Etapa 'ocupacao' 'Modelo de ocupacao e receita' {
        & $PY -m airbnb.models.ocupacao
    }
}

function Invoke-Sobrevivencia {
    Invoke-Etapa 'sobrevivencia' 'Sobrevivencia dos anuncios de 2019 ate hoje' {
        & $PY -m airbnb.models.sobrevivencia
    }
}

function Invoke-Deriva {
    Invoke-Etapa 'deriva' 'Validacao temporal: modelo de 2019 aplicado ao mercado atual' {
        & $PY -m airbnb.models.deriva
    }
}

# Fase 6 — implantacao
function Invoke-Figuras {
    Invoke-Etapa 'figuras' 'Tabelas e figuras da documentacao' {
        & $PY -m airbnb.produto.relatorio
        & $PY -m airbnb.produto.figuras
    }
}

function Invoke-Site {
    Invoke-Etapa 'site' 'Dados do site publico + paridade Python <-> JavaScript' {
        & $PY -m airbnb.produto.exportar
        if (Get-Command node -ErrorAction SilentlyContinue) {
            node tests/paridade_js.mjs
        }
        else {
            Write-Host '    node ausente: paridade JS nao conferida' -ForegroundColor Yellow
        }
    }
}

function Invoke-Notebooks {
    Invoke-Etapa 'notebooks' 'Notebooks da apresentacao (executados)' {
        & $PY -m airbnb.produto.notebooks
    }
}

function Invoke-Docs {
    Invoke-Etapa 'docs' 'Documentacao (mkdocs --strict)' {
        & $PY -m mkdocs build --strict --site-dir _site/docs
    }
}

# Serve site + docs juntos, na mesma estrutura de URLs do GitHub Pages.
function Invoke-Servir {
    & $PY -m mkdocs build --site-dir _site/docs | Out-Null
    Copy-Item -Recurse -Force site/* _site/
    Write-Host 'http://localhost:8000  (Ctrl+C para parar)' -ForegroundColor Cyan
    & $PY -m http.server 8000 --directory _site
}

function Invoke-Test {
    Invoke-Etapa 'test' 'Lint e testes' {
        & $PY -m ruff check src tests
        & $PY -m pytest -q
    }
}

# --- despacho ---------------------------------------------------------------

switch ($Task) {
    'status'        { & $PY -m airbnb.pipeline.estado }
    'log'           { & $PY -m airbnb.pipeline.estado --execucoes }
    'dados'         { Invoke-Dados }
    'limpeza'       { Invoke-Limpeza }
    'externos'      { Invoke-Externos }
    'celulas'       { Invoke-Celulas }
    'features'      { Invoke-Features }
    'comparativo'   { Invoke-Comparativo }
    'espacial'      { Invoke-Espacial }
    'preco'         { Invoke-Preco }
    'ocupacao'      { Invoke-Ocupacao }
    'sobrevivencia' { Invoke-Sobrevivencia }
    'deriva'        { Invoke-Deriva }
    'figuras'       { Invoke-Figuras }
    'site'          { Invoke-Site }
    'notebooks'     { Invoke-Notebooks }
    'docs'          { Invoke-Docs }
    'servir'        { Invoke-Servir }
    'test'          { Invoke-Test }
    'all' {
        if (-not (Test-Path (Join-Path $PSScriptRoot $KAGGLE))) {
            throw "arquivo ausente: $KAGGLE. Baixe de kaggle.com/datasets/dgomonov/new-york-city-airbnb-open-data (ver docs/como-reproduzir.md)."
        }
        Invoke-Dados; Invoke-Limpeza; Invoke-Externos; Invoke-Celulas; Invoke-Features
        Invoke-Comparativo
        # preco antes de espacial e ocupacao: os dois leem os residuos fora do fold dele
        Invoke-Preco; Invoke-Espacial; Invoke-Ocupacao; Invoke-Sobrevivencia; Invoke-Deriva
        # site antes de figuras: o mapa da documentacao le o premio que a exportacao grava
        Invoke-Site; Invoke-Figuras; Invoke-Docs
        & $PY -m airbnb.pipeline.estado
    }
    default { Get-Help $PSCommandPath -Detailed }
}
