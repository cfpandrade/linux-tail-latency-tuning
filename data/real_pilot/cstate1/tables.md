| Condition | Runs | p50 | p99 | p99.9 | p99.9 pooled [95% CI] | max (median) | idle entries/s (C1E or deeper) |
|---|---|---|---|---|---|---|---|
| FIFO 80, CPU 5 shared with load | 5 | 5 | 12 | 93 | 93 [50, 118] | 2358 | 5 |
| FIFO 80, CPU 5 + sibling free | 5 | 7 | 33 | 66 | 65 [60, 71] | 498 | 6312 |
| FIFO 80, CPU 5 + sibling free, keep-awake | 5 | 5 | 14 | 59 | 53 [38, 71] | 481 | 0 |
| OTHER, CPU 5 + sibling free | 5 | 57 | 272 | 1935 | 2176 [1767, 2668] | 16524 | 6638 |
| OTHER, CPU 5 + sibling free, keep-awake | 5 | 54 | 111 | 830 | 985 [614, 1328] | 12650 | 0 |
| OTHER, CPU 5 + sibling free, slack 1 ns | 5 | 57 | 302 | 2180 | 2768 [1903, 3418] | 18844 | 6151 |
| OTHER, CPU 5 + sibling free, keep-awake, slack 1 ns | 5 | 54 | 115 | 895 | 817 [577, 950] | 11039 | 0 |
