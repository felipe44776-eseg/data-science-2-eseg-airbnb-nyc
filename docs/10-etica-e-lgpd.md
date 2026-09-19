# Ética, privacidade e LGPD

Os dados do Airbnb são públicos — o Inside Airbnb os coleta do site aberto e
os publica sob CC BY 4.0. *Público* não quer dizer *sem pessoas dentro*. Este
documento registra o que publicamos, o que deliberadamente não publicamos e por quê.

## 1. O que há de pessoal nas bases

| dado | onde | tratamento |
|---|---|---|
| nome do anfitrião (`host_name`) | Kaggle 2019 e Inside Airbnb 2026 | **removido na limpeza** — não identifica (homônimos, ver [docs/02](02-entendimento-dos-dados.md) Q3) e não é necessário para nenhuma análise |
| texto "sobre o anfitrião", foto, URLs de perfil | Inside Airbnb 2026 | **removidos na limpeza** |
| descrição do anúncio e do bairro (texto livre) | Inside Airbnb 2026 | **removidos** — texto livre pode conter nome, telefone, endereço |
| `host_id` | ambas | mantido **só** internamente, para medir concentração (anfitrião com vários anúncios); nunca publicado |
| id do anúncio | ambas | mantido internamente para ligar 2019 a 2026 (sobrevivência); **não vai para o site** |
| coordenada | ambas | já vem deslocada até ~150 m pelo Airbnb; no site os pontos aparecem com 4 casas decimais e sem nenhum identificador |

A invariante 9 do projeto proíbe qualquer um desses campos nas superfícies publicadas,
e `tests/` verifica a ausência de colunas pessoais nas saídas da limpeza e nos JSON do site.

## 2. LGPD e o dado de terceiros

A LGPD (Lei 13.709/2018) se aplica ao tratamento de dados pessoais realizado no
Brasil, inclusive de titulares estrangeiros. O tratamento aqui é **acadêmico**
(art. 7º, IV — estudos por órgão de pesquisa; e art. 4º, II, *b*, para fins
exclusivamente acadêmicos), mas adotamos os princípios do art. 6º como regra de
projeto, não como obrigação mínima:

- **Finalidade e necessidade**: cada coluna mantida tem uso declarado no
  [dicionário](dicionario-dados.md). O que não tem uso, sai.
- **Minimização na publicação**: o site recebe só agregados por célula H3 e pontos
  sem identificador.
- **Transparência**: fontes, licenças e transformações estão em
  [Fontes externas](03-fontes-externas.md) e no código.

## 3. Riscos de uso indevido dos resultados

| resultado | uso indevido possível | o que fizemos |
|---|---|---|
| mapa de crimes por célula | estigmatizar bairros; "redlining" digital | crime entra agregado por **delegacia** (77–78 áreas, queixas por km² em 12 meses), nunca por ponto; o texto lembra que **crime registrado ≠ crime ocorrido** e que o registro depende de policiamento |
| renda do entorno (ACS) como preditor de preço | reforçar segregação ao precificar | a variável é reportada com sua contribuição medida (SHAP) e discutida — não escondida dentro do modelo |
| anúncios "abaixo do previsto" | pressionar anfitriões individuais | o site não mostra id, título nem anfitrião; o resíduo é apresentado como "abaixo do que anúncios parecidos pedem", não como erro do anfitrião |
| modelo de sobrevivência pós-LL18 | orientar evasão da fiscalização | o modelo explica *quem saiu do mercado*; não há recomendação de como operar sem registro |

## 4. Vieses conhecidos

- **Preço anunciado ≠ preço pago.** Descontos, taxas e preços dinâmicos não aparecem.
- **Ocupação é estimada** pelo Inside Airbnb a partir de avaliações — anúncios cujos
  hóspedes avaliam menos parecem menos ocupados.
- **OpenStreetMap é colaborativo**: bairros com mais mapeadores voluntários têm mais
  POIs registrados — o que pode confundir "mais comércio" com "mais mapeamento".
- **Sobreviventes**: avaliações de anúncios que saíram do ar antes de 2026 não estão no
  arquivo de avaliações atual.

## 5. Atribuição

Toda fonte é citada com a licença exigida no rodapé do site e em
[Fontes externas](03-fontes-externas.md). Inside Airbnb: CC BY 4.0 — *"Data from
Inside Airbnb"*, com link. OpenStreetMap: ODbL — *"© colaboradores do OpenStreetMap"*.
