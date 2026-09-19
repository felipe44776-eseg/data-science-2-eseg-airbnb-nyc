| modelo | MdAPE | MAE | R² (log) | MdAPE entre folds |
| --- | ---: | ---: | ---: | ---: |
| B0 · mediana global | 53,5% | US$ 176,4 | -0,083 | 47,2% – 67,9% |
| B1 · mediana por bairro × tipo (v0) | 46,6% | US$ 159,7 | 0,130 | 37,8% – 54,7% |
| M1 · regressão linear hedônica | 27,6% | US$ 111,4 | 0,669 | 25,9% – 30,6% |
| M2 · LightGBM, só o imóvel | 24,5% | US$ 103,9 | 0,716 | 22,2% – 30,1% |
| M3 · + coordenadas e distrito | 21,7% | US$ 96,1 | 0,762 | 20,3% – 24,6% |
| M4 · + fontes externas | 22,0% | US$ 96,1 | 0,760 | 21,0% – 24,4% |
| M4 sem coordenadas (só externas) | 22,1% | US$ 96,5 | 0,760 | 21,1% – 24,9% |
| **M5 · produto (simulador)** | 25,0% | US$ 102,0 | 0,724 | 22,6% – 26,2% |
