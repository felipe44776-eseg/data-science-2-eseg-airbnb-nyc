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

**Cinco dos sete critérios atendidos, dois não.** Nenhum foi ajustado depois do
resultado. C6 e C7 estão na tabela acima junto com os demais — o placar não é
sobre cinco critérios, é sobre sete.

**C1–C3 · o produto funciona.** O modelo do simulador erra 25% na mediana (MdAPE),
36% menos que a mediana por bairro × tipo — a melhor resposta que a análise descritiva
daria — e o intervalo de 80% cobre de 78% a 80% em **cada** tipo de acomodação, medido
fora dos blocos que o calibraram. Para quem pergunta "quanto cobrar aqui?", o simulador
dá uma resposta útil e uma faixa honesta.

**C4 · as fontes externas não melhoraram a acurácia do preço.** É um resultado nulo e
está publicado como tal ([Modelagem](07-modelagem.md) §2.2). Três ressalvas o tornam
menos decepcionante do que parece:

1. elas **substituem** a coordenada quase sem perda (22,1% × 21,7%) — o modelo prefere
   usá-las (23,8% do SHAP contra 1,7% das coordenadas), o que torna a explicação
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

!!! note "C4 e C5 não são duas decepções: são o mesmo achado"
    Os dois critérios reprovaram pelo mesmo motivo, e ele é um resultado, não um
    fracasso. **Dado o ponto no mapa, o resto da geografia é redundante.**

    - no preço, as externas não somam à coordenada porque *são* a coordenada: a
      mediana do η² delas explicado pela célula r8 é **0,85**, e as distâncias a
      marcos, 0,997–0,999;
    - na sobrevivência, tirar toda a localização **melhora** o modelo (0,6676 ×
      0,6659), e o espalhamento entre distritos é de 1,8 p.p. (Manhattan 14,6%,
      Brooklyn 16,3%);
    - no preço, o imóvel sozinho (M2) dá R² 0,716 contra 0,760 do modelo completo:
      **todo o aparato espacial e as oito fontes externas compram 4,4 pontos de R².**

    A localização importa para o *nível* de preço — o I de Moran de 0,44 e o prêmio
    que, em 95% das células, vai de −15% ao dobro (e passa disso nos 5% mais caros,
    até +445%) não são ilusão. O que ela não faz é acrescentar informação depois que o
    modelo já sabe onde o anúncio está.

### Quanto do encolhimento a Local Law 18 explica

O grupo de controle sempre esteve na base e ninguém o tinha usado: um anúncio que em
2019 **já exigia 30+ noites** nunca esteve no alcance do registro. Comparando com o
resto:

| grupo | n em 2019 | sobreviveu até 2026 |
|---|---:|---:|
| exposto (menos de 30 noites em 2019) | 44.388 | 14,79% |
| controle (já exigia 30+ noites) | 4.507 | 21,14% |

Se os expostos tivessem morrido à taxa dos controles, **2.823 anúncios a mais** teriam
sobrevivido — sobre 41.379 mortes observadas, uma fração atribuível de **6,8%**.

!!! warning "Isto é uma ordem de grandeza sob um desenho contestável, não um efeito causal"
    Em 2019 o grupo de 30+ noites era 9,2% do mercado e atípico: estadia longa
    mobiliada, outro público, outra sazonalidade. A hipótese de tendências paralelas
    não é testável com dois pontos no tempo, e a pandemia atravessa o intervalo inteiro.

    **O viés pode ir para os dois lados**, e por isso o número não é nem piso nem teto:

    - o anúncio de estadia longa é, por natureza, um negócio mais estável — ele
      sobreviveria mais mesmo sem lei nenhuma, o que **infla** a diferença e faz os
      6,8% superestimarem o efeito da lei;
    - parte do grupo de controle pode ter sido atingida de forma indireta (varreduras
      da plataforma, anúncios que mudaram de regime depois de 2019), o que **reduz** a
      diferença e faz os 6,8% subestimarem.

    O número **não** mede o efeito da lei. Ele serve para descartar uma afirmação forte
    demais: que a LL18 explica *quase tudo* do encolhimento. Para chegar de 7% a "quase
    tudo", a lei teria de ter derrubado também a maior parte dos anúncios que ela nem
    alcançava. As outras saídas aconteceram entre quem a lei não alcançava tanto quanto
    entre quem ela alcançava.

    Versões anteriores deste texto chamavam o número de "piso" aqui e de "no máximo" no
    portal. As duas leituras não podiam estar certas ao mesmo tempo; nenhuma está.

**O que muda no negócio:**

- **para o anfitrião**, o preço de um imóvel depende 3/4 do imóvel e 1/4 do lugar — e o
  lugar, pelo simulador, pode dobrar o preço do mesmo apartamento;
- **para a política pública**, a oferta de estadia curta encolheu junto com a LL18
  (−38% de anúncios, estadia curta de 91% para 18%) — embora só ~6,8% do encolhimento
  se sustente como atribuível a ela pelo controle acima. No mesmo período o mercado
  concentrou-se (o 1% de anfitriões com mais anúncios passou de 10% para 25% dos
  anúncios) e sobrou um nicho de estadia curta legal que fatura 1,7 vez o aluguel
  tradicional;
- **para o hóspede**, a diária da estadia curta que **restou legal** custa de 2 a 3
  vezes mais que a de 2019 em termos reais (+97% em apartamento inteiro, +175% em
  quarto privativo, +318% em compartilhado). É o preço do que sobrou, não o preço da
  mesma coisa: o estrato perdeu 87% dos anúncios no caminho. Na estadia longa, o
  apartamento inteiro subiu **4,0%** em sete anos.

!!! note "Os preços comparam a mesma definição nos dois anos"
    O `price` de 2019 é a diária anunciada; o de 2026 é a cotação de uma estadia do
    mínimo de noites **já com desconto** — 4,4% na mediana da estadia de 30+ noites.
    Toda comparação de preço entre os dois anos usa, para 2026, o `preco_cheio`: a
    diária sem desconto, que tem a mesma definição de 2019 e foi separada para isso
    ainda no [entendimento dos dados](02-entendimento-dos-dados.md). Com o preço
    descontado, o apartamento inteiro de 30+ noites parecia **6,4% mais barato** que em
    2019; na mesma definição, está **4,0% mais caro**. O desconto escondia a alta.

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
