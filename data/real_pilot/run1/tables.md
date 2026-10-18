Table: baseline and re-evaluated configurations (us). Median of runs; pooled p99.9 with 95% bootstrap CI.

| Configuration | Runs | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | max | Cliff's delta |
|---|---|---|---|---|---|---|---|
| bo#0: FIFO p1, cpu10 | 5 | 5 | 10 | 19 | 54 [14, 87] | 453 | -0.998 |
| bo#1: FIFO p52, cpu10 | 5 | 5 | 10 | 17 | 17 [14, 23] | 20000 | -0.999 |
| bo#2: FIFO p1, unpinned | 5 | 5 | 10 | 27 | 50 [17, 80] | 2322 | -0.998 |
| bo#3: FIFO p99, unpinned | 5 | 5 | 10 | 31 | 58 [26, 79] | 2392 | -0.998 |
| bo#4: FIFO p1, unpinned | 5 | 5 | 9 | 14 | 14 [12, 17] | 454 | -1.000 |
| default: untuned default | 5 | 56 | 75 | 2385 | 2541 [2159, 2780] | 18913 | 0.000 |
| random#0: FIFO p80, unpinned | 5 | 5 | 10 | 67 | 59 [15, 87] | 6505 | -0.998 |
| random#1: FIFO p36, unpinned | 5 | 5 | 10 | 17 | 21 [14, 60] | 494 | -0.999 |
| random#2: FIFO p64, cpu6 | 5 | 5 | 10 | 25 | 30 [14, 69] | 535 | -0.999 |
| random#3: FIFO p76, cpu1 | 5 | 5 | 10 | 61 | 63 [22, 82] | 2521 | -0.998 |
| random#4: FIFO p20, cpu2 | 5 | 5 | 11 | 69 | 69 [44, 81] | 8414 | -0.997 |

Table: factorial phase (us).

| Configuration | Runs | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | max | LOC Hz | IRQ Hz |
|---|---|---|---|---|---|---|---|---|
| OTHER, cpu0 | 3 | 56 | 105 | 2264 | 2458 [2115, 2732] | 20000 | 5804 | 5918 |
| OTHER, cpu5 | 3 | 56 | 70 | 2865 | 2642 [2031, 2928] | 20000 | 5911 | 5949 |
| OTHER, cpu0, isolated | 3 | 57 | 531 | 3251 | 3189 [2771, 3513] | 20000 | 5698 | 5890 |
| OTHER, cpu5, isolated | 3 | 57 | 444 | 2888 | 2890 [2761, 3009] | 20000 | 6218 | 6268 |
| OTHER, cpu0, isolated + sibling free | 3 | 57 | 206 | 1647 | 1685 [1616, 1758] | 20000 | 5114 | 5225 |
| OTHER, cpu5, isolated + sibling free | 3 | 56 | 213 | 1861 | 1803 [1670, 1866] | 20000 | 5473 | 5586 |
| FIFO p80, cpu0 | 3 | 5 | 11 | 58 | 77 [29, 96] | 9388 | 6198 | 6262 |
| FIFO p80, cpu5 | 3 | 5 | 11 | 91 | 90 [87, 97] | 3835 | 6251 | 6303 |
| FIFO p80, cpu0, isolated | 3 | 6 | 20 | 113 | 102 [74, 117] | 611 | 6674 | 6737 |
| FIFO p80, cpu5, isolated | 3 | 6 | 14 | 108 | 109 [100, 120] | 574 | 6747 | 6794 |
| FIFO p80, cpu0, isolated + sibling free | 3 | 5 | 35 | 61 | 58 [54, 62] | 642 | 6265 | 6352 |
| FIFO p80, cpu5, isolated + sibling free | 3 | 6 | 33 | 49 | 50 [45, 59] | 903 | 6256 | 6334 |

Table: main effects on log10 p999 (multiplicative factor = 10^coef).

| Term | coef | se | factor |
|---|---|---|---|
| intercept | 3.352 | 0.036 | 2249.402 |
| fifo | -1.502 | 0.032 | 0.031 |
| isolate | 0.129 | 0.040 | 1.344 |
| sibling_free | -0.260 | 0.040 | 0.549 |
| cpu5_vs_cpu0 | 0.038 | 0.032 | 1.092 |

Table: main effects on log10 p99 (multiplicative factor = 10^coef).

| Term | coef | se | factor |
|---|---|---|---|
| intercept | 2.043 | 0.068 | 110.467 |
| fifo | -1.060 | 0.060 | 0.087 |
| isolate | 0.497 | 0.074 | 3.138 |
| sibling_free | -0.052 | 0.074 | 0.887 |
| cpu5_vs_cpu0 | -0.054 | 0.060 | 0.882 |
