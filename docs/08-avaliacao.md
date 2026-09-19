# 5 · Avaliação

> Fase 5 do CRISP-DM: os modelos respondem às perguntas de negócio com a
> qualidade que prometemos **antes** de treiná-los? A régua é a de
> [docs/01](01-entendimento-do-negocio.md) §5 — não foi mexida depois.

## 1. Critérios de sucesso × resultado

--8<-- "_snippets/tabela_criterios.md"

C6 (paridade Python ↔ JavaScript) é verificado a cada exportação e no CI —
ver [Implantação](09-implantacao.md). C7 (reprodutibilidade) é verificado por
`.\tasks.ps1 status`.

## 2. Leitura dos resultados

**Três critérios atendidos, dois não.** Nenhum foi ajustado depois do resultado.

**C1–C3 · o produto funciona.** O modelo do simulador erra 25% na mediana (MdAPE),
36% menos que a mediana por bairro × tipo — a melhor resposta que a análise descritiva
daria — e o intervalo de 80% cobre de 78% a 80% em **cada** tipo de acomodação, medido
fora dos blocos que o calibraram. Para quem pergunta "quanto cobrar aqui?", o simulador
dá uma resposta útil e uma faixa honesta.

**C4 · as fontes externas não melhoraram a acurácia do preço.** É um resultado nulo e
está publicado como tal ([Modelagem](07-modelagem.md) §2.2). Três ressalvas o tornam
menos decepcionante do que parece:

1. elas **substituem** a coordenada quase sem perda (22,1% × 21,7%) — o modelo prefere
   usá-las (25,5% do SHAP contra 1,7% das coordenadas), o que torna a explicação
   de "por que este lugar é caro" possível: aluguel do entorno, distância aos marcos,
   renda;
2. foram elas que **mudaram conclusões** fora do modelo de preço: sem o CPI regional
   não haveria comparação honesta com 2019; sem o Zillow, não haveria a descoberta de
   que o aluguel mensal pelo Airbnb fatura menos que o aluguel tradicional; sem a OSE,
   não haveria a medida do mercado registrado;
3. a granularidade de parte delas é grossa (crime por delegacia, barulho por CEP) — e a
   ablação mostra que justamente NYPD e marcos são as que ajudam de forma consistente.

**C5 · a sobrevivência não é previsível o bastante (AUC 0,67).** O achado é
substantivo: a saída do mercado entre 2019 e 2026 foi ampla e pouco seletiva; o que
diferencia os sobreviventes é o tipo de operação (já mensal, calendário fechado), não o
lugar. O modelo fica explicativo, como previsto no pré-registro.

**O que muda no negócio:**

- **para o anfitrião**, o preço de um imóvel depende 3/4 do imóvel e 1/4 do lugar — e o
  lugar, pelo simulador, pode dobrar o preço do mesmo apartamento;
- **para a política pública**, a LL18 fez o que pretendia com a oferta (−38% de anúncios,
  estadia curta de 91% para 18%), mas concentrou o mercado (o 1% maior de anfitriões
  passou de 10% para 25% dos anúncios) e criou um nicho de estadia curta legal que fatura
  1,7 vez o aluguel tradicional;
- **para o hóspede**, a estadia curta ficou de 2 a 3 vezes mais cara em termos reais.

## 3. Ameaças à validade

| ameaça | onde pesa | o que fizemos | o que sobra |
|---|---|---|---|
| **preço anunciado ≠ preço pago** | todo o modelo de preço | resíduo lido como "acima/abaixo do que anúncios parecidos pedem", nunca como "caro/barato" | descontos, taxas e preço dinâmico ficam de fora |
| **coordenada deslocada** (até ~150 m) | features de localização, mapa | unidade H3 r9 (ADR 0001) | nada abaixo de ~200 m é interpretável |
| **cotação com desconto em 2026** | comparação 2019 × 2026 | estratificação por mínimo de noites; `preco_cheio` (sem desconto) disponível | o desconto mensal é escolha do anfitrião — parte do "preço" |
| **ocupação estimada** | modelo O3, receita | fórmula do Inside Airbnb reproduzida e declarada | anúncios cujos hóspedes avaliam menos parecem menos ocupados |
| **sobrevivência por id** | modelo O4 | definição explícita | reanúncio com id novo conta como saída |
| **anacronismo de fontes** | features de 2019 | ACS, crimes, 311 e aluguel por safra; metrô, OSM e marcos atuais nos dois | POIs de 2026 aplicados a 2019 |
| **dependência espacial residual** | intervalos | CV espacial + conformal com cobertura honesta | a cobertura é média sobre blocos, não garantida em cada bairro |

## 4. O que o negócio leva

| quem | pergunta | resposta entregue |
|---|---|---|
| anfitrião / investidor | quanto cobrar e quanto fatura aqui? | simulador do site: preço esperado com faixa de 80%, noites ocupadas se ativo, prêmio da localização |
| hóspede | este preço é justo? | pontos do mapa: acima/abaixo do que anúncios parecidos pedem |
| poder público | o que a LL18 mudou? | comparativo em dólar constante + decomposição + sobrevivência |
| banca | o método é honesto? | critérios pré-registrados, CV espacial, ablação, paridade verificada |

## 5. Próximos passos (frentes abertas)

- **Série temporal de snapshots.** O Inside Airbnb publica NYC trimestralmente; um
  painel de snapshots permitiria um desenho de diferenças-em-diferenças em torno de
  2023-09-05 (LL18), com grupo de controle nos anúncios de 30+ noites.
- **Dados de registro da OSE**, se publicados por endereço: validar `licenca_status`.
- **Calendário diário** (`calendar.csv.gz`, já baixado): sazonalidade da
  disponibilidade — sem preço desde que o Inside Airbnb deixou de publicá-lo.
- **Recalibração trimestral do produto**, disparada por `.\tasks.ps1 all` com o
  snapshot novo — o gatilho do ADR 0003 para automatizar.
