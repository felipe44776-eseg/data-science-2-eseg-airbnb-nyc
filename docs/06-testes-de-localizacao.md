# Testes de localização

> "Localização importa" é a frase mais repetida sobre imóveis — e a menos testada.
> Aqui ela vira hipótese, com estatística de teste, p-valor e tamanho de efeito.
> Código em `src/airbnb/eda/espacial.py` e `estatistica_espacial.py`; números em
> `data/processed/_espacial.json`.

## 1. O que separa "onde" de "o quê"

O preço de um bairro mistura duas coisas: **onde** ele está e **o que** se anuncia
lá (Manhattan tem mais apartamento inteiro; o Bronx, mais quarto privativo). Para
isolar o "onde", usamos o **prêmio de localização observado**: o resíduo fora do fold
de um modelo que só vê o imóvel (M2 — sem coordenada nem fonte externa), médio por
célula. Se a localização não importasse, esse resíduo seria ruído sem padrão espacial.

## 2. Autocorrelação espacial global — I de Moran

Unidade: célula H3 r8 (~0,7 km²) com pelo menos 5 anúncios com preço. Vizinhança:
os seis hexágonos adjacentes (anel k=1), padronizada por linha; células sem vizinho
são removidas. Significância por **999 permutações**, p-valor **bilateral**
(o pseudo p-valor do `esda` é unilateral na direção observada — publicá-lo cru
dobraria o falso positivo).

\(H_0\): o valor de uma célula não se parece com o das vizinhas (\(I \approx -1/(n-1)\)).

--8<-- "_snippets/tabela_moran.md"

**H₀ rejeitada nos três casos**, com folga: nenhuma das 999 permutações chegou perto do
valor observado (z entre 13 e 21). O resultado que importa é a terceira linha: mesmo
**depois de descontar tudo o que o imóvel explica**, o resíduo de preço continua
fortemente parecido entre células vizinhas (I = 0,44). Há um "efeito lugar" que não é
só "que tipo de imóvel existe ali" — e é esse efeito que as features de localização
dos modelos capturam.

A autocorrelação do preço bruto caiu de 0,62 (2019) para 0,58 (2026): o mapa de preços
ficou um pouco menos segregado, compatível com a oferta mais espalhada pelos distritos
periféricos ([Comparativo](05-comparativo-2019-2026.md) §5).

## 3. Onde estão os aglomerados — LISA

O Moran local classifica cada célula em Alto-Alto (cara cercada de caras),
Baixo-Baixo, Alto-Baixo e Baixo-Alto (discrepantes). Com milhares de células, 5%
delas sairiam "significativas" por acaso: a significância é corrigida por **FDR
(Benjamini-Hochberg) a 5%**. Os aglomerados estão no [mapa](https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/mapa/), métrica
"Aglomerados de preço (LISA)".

Com a correção, sobrevivem 19 aglomerados Alto-Alto e 2 Baixo-Baixo de prêmio de
localização, entre 515 células (no preço bruto, 37 e 8). A FDR é conservadora de
propósito: o que ela aponta é o núcleo onde o "efeito lugar" é inequívoco, não todo
lugar caro.

## 4. Distritos: diferença e tamanho do efeito

Dentro de cada tipo de quarto (comparar tipos diferentes seria composição),
Kruskal-Wallis entre os cinco distritos, com **ε²** como tamanho de efeito — com
dezenas de milhares de anúncios, qualquer diferença tem p minúsculo; o que informa é
o tamanho. Pares com Mann-Whitney, correção de **Holm** e correlação
**rank-biserial**. Resultados completos em `_espacial.json` → `distritos`.

| tipo | Kruskal-Wallis H | ε² | medianas (US$/noite) |
|---|---:|---:|---|
| casa ou apê inteiro | 1.212,9 | 0,108 | Manhattan 268 · Brooklyn 201 · Queens 163 · Bronx 138 · Staten Island 117 |
| quarto privativo | 887,3 | 0,096 | Manhattan 155 · Staten Island 95 · Brooklyn 93 · Queens 84 · Bronx 78 |

O efeito do distrito é **moderado** (ε² ≈ 0,10): o distrito separa bem os extremos
(Manhattan × Staten Island em casa inteira: rank-biserial 0,68), mas explica pouco
sozinho — o bairro e a célula explicam bem mais (seção 5). Em quarto privativo, Brooklyn
× Staten Island e Queens × Staten Island **não** diferem (p de Holm = 0,40).

## 5. Quanto da variância é lugar, quanto é imóvel

--8<-- "_snippets/tabela_variancia.md"

Sozinha, a localização explica muito (a média da célula r8 dá conta de 36% da variância
do log-preço). Mas o imóvel já carrega boa parte dela — Manhattan tem outro tipo de
anúncio —, e **depois de conhecer o imóvel, a localização acrescenta 4,4 pontos de R²**
fora do fold (de 71,6% para 76,0%). Pequeno em R², não em dinheiro: pelo modelo do
simulador, o mesmo apartamento de referência vale de 15% abaixo a mais que o dobro da
mediana da cidade conforme a célula — em 5% das células com anúncio, 140% acima ou mais
(ver o mapa em [Modelagem](07-modelagem.md) §2.3). A distribuição é assimétrica: quase
toda a cidade fica perto da mediana, e o prêmio se concentra em poucas áreas.

!!! note "Por que os dois tipos de número"
    O η² de bairro e de célula é **dentro da amostra** (cada grupo usa a própria
    média) e fica otimista quanto menores os grupos. Os R² dos modelos são **fora do
    fold, com validação espacial** — comparáveis entre si e sem esse viés.

## 6. O teste de localização do site

O simulador do [mapa](https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/mapa/) é o mesmo teste, aplicado a um ponto: escolhido o lugar
e o imóvel, o modelo do produto (M5) devolve o preço esperado com intervalo de 80%,
e o **prêmio de localização** = previsão aqui ÷ previsão do mesmo imóvel na célula
de referência da cidade − 1.
