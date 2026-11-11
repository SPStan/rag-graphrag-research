# E4: токенная стоимость и окупаемость

При неполном учёте показан известный минимум; полная стоимость остаётся неизвестной.
LLM input+output и локальные BGE input tokens считаются отдельно; это не денежные цены.

| Dataset | Method | EM | I LLM known | q LLM known | I BGE known | q BGE known | I LLM complete | I BGE complete |
|---|---|---:|---:|---:|---:|---:|---|---|
| musique | dense | 34.8% | 0.0 | 1 504.5 | 684 560.0 | 25.8 | True | True |
| hotpotqa | dense | 59.6% | 0.0 | 1 398.4 | 776 137.0 | 24.3 | True | False |
| musique | hipporag2 | 43.4% | 7 443 878.0 | 4 679.7 | 2 721 136.0 | 25.8 | False | False |
| hotpotqa | hipporag2 | 66.6% | 7 817 801.0 | 4 532.9 | 2 856 226.0 | 24.3 | False | False |
| musique | raptor | 32.4% | 3 342 184.0 | 3 917.2 | 2 314 512.0 | 25.8 | False | False |
| hotpotqa | raptor | 60.6% | 3 593 135.0 | 3 238.7 | 2 513 083.0 | 24.3 | False | False |

## llm: projected tokens

| Dataset | Method | N | T known minimum | C known minimum | C/EM known minimum | Full cost |
|---|---|---:|---:|---:|---:|---|
| musique | dense | 100 | 150 451.2 | 1 504.5 | 4 323.3 | complete |
| musique | dense | 1000 | 1 504 512.0 | 1 504.5 | 4 323.3 | complete |
| musique | dense | 10000 | 15 045 120.0 | 1 504.5 | 4 323.3 | complete |
| musique | dense | 100000 | 150 451 200.0 | 1 504.5 | 4 323.3 | complete |
| hotpotqa | dense | 100 | 139 838.0 | 1 398.4 | 2 346.3 | complete |
| hotpotqa | dense | 1000 | 1 398 380.0 | 1 398.4 | 2 346.3 | complete |
| hotpotqa | dense | 10000 | 13 983 800.0 | 1 398.4 | 2 346.3 | complete |
| hotpotqa | dense | 100000 | 139 838 000.0 | 1 398.4 | 2 346.3 | complete |
| musique | hipporag2 | 100 | 7 911 844.8 | 79 118.4 | 182 300.6 | неизвестно |
| musique | hipporag2 | 1000 | 12 123 546.0 | 12 123.5 | 27 934.4 | неизвестно |
| musique | hipporag2 | 10000 | 54 240 558.0 | 5 424.1 | 12 497.8 | неизвестно |
| musique | hipporag2 | 100000 | 475 410 678.0 | 4 754.1 | 10 954.2 | неизвестно |
| hotpotqa | hipporag2 | 100 | 8 271 088.0 | 82 710.9 | 124 190.5 | неизвестно |
| hotpotqa | hipporag2 | 1000 | 12 350 671.0 | 12 350.7 | 18 544.6 | неизвестно |
| hotpotqa | hipporag2 | 10000 | 53 146 501.0 | 5 314.7 | 7 980.0 | неизвестно |
| hotpotqa | hipporag2 | 100000 | 461 104 801.0 | 4 611.0 | 6 923.5 | неизвестно |
| musique | raptor | 100 | 3 733 901.0 | 37 339.0 | 115 243.9 | неизвестно |
| musique | raptor | 1000 | 7 259 354.0 | 7 259.4 | 22 405.4 | неизвестно |
| musique | raptor | 10000 | 42 513 884.0 | 4 251.4 | 13 121.6 | неизвестно |
| musique | raptor | 100000 | 395 059 184.0 | 3 950.6 | 12 193.2 | неизвестно |
| hotpotqa | raptor | 100 | 3 917 009.4 | 39 170.1 | 64 637.1 | неизвестно |
| hotpotqa | raptor | 1000 | 6 831 879.0 | 6 831.9 | 11 273.7 | неизвестно |
| hotpotqa | raptor | 10000 | 35 980 575.0 | 3 598.1 | 5 937.4 | неизвестно |
| hotpotqa | raptor | 100000 | 327 467 535.0 | 3 274.7 | 5 403.8 | неизвестно |

## embedding: projected tokens

| Dataset | Method | N | T known minimum | C known minimum | C/EM known minimum | Full cost |
|---|---|---:|---:|---:|---:|---|
| musique | dense | 100 | 687 135.4 | 6 871.4 | 19 745.3 | complete |
| musique | dense | 1000 | 710 314.0 | 710.3 | 2 041.1 | complete |
| musique | dense | 10000 | 942 100.0 | 94.2 | 270.7 | complete |
| musique | dense | 100000 | 3 259 960.0 | 32.6 | 93.7 | complete |
| hotpotqa | dense | 100 | 778 570.4 | 7 785.7 | 13 063.3 | неизвестно |
| hotpotqa | dense | 1000 | 800 471.0 | 800.5 | 1 343.1 | неизвестно |
| hotpotqa | dense | 10000 | 1 019 477.0 | 101.9 | 171.1 | неизвестно |
| hotpotqa | dense | 100000 | 3 209 537.0 | 32.1 | 53.9 | неизвестно |
| musique | hipporag2 | 100 | 2 723 711.4 | 27 237.1 | 62 758.3 | неизвестно |
| musique | hipporag2 | 1000 | 2 746 890.0 | 2 746.9 | 6 329.2 | неизвестно |
| musique | hipporag2 | 10000 | 2 978 676.0 | 297.9 | 686.3 | неизвестно |
| musique | hipporag2 | 100000 | 5 296 536.0 | 53.0 | 122.0 | неизвестно |
| hotpotqa | hipporag2 | 100 | 2 858 659.4 | 28 586.6 | 42 922.8 | неизвестно |
| hotpotqa | hipporag2 | 1000 | 2 880 560.0 | 2 880.6 | 4 325.2 | неизвестно |
| hotpotqa | hipporag2 | 10000 | 3 099 566.0 | 310.0 | 465.4 | неизвестно |
| hotpotqa | hipporag2 | 100000 | 5 289 626.0 | 52.9 | 79.4 | неизвестно |
| musique | raptor | 100 | 2 317 087.4 | 23 170.9 | 71 515.0 | неизвестно |
| musique | raptor | 1000 | 2 340 266.0 | 2 340.3 | 7 223.0 | неизвестно |
| musique | raptor | 10000 | 2 572 052.0 | 257.2 | 793.8 | неизвестно |
| musique | raptor | 100000 | 4 889 912.0 | 48.9 | 150.9 | неизвестно |
| hotpotqa | raptor | 100 | 2 515 516.4 | 25 155.2 | 41 510.2 | неизвестно |
| hotpotqa | raptor | 1000 | 2 537 417.0 | 2 537.4 | 4 187.2 | неизвестно |
| hotpotqa | raptor | 10000 | 2 756 423.0 | 275.6 | 454.9 | неизвестно |
| hotpotqa | raptor | 100000 | 4 946 483.0 | 49.5 | 81.6 | неизвестно |

## Окупаемость относительно Dense

| Dataset | Method | Unit | Known-cost scenario | N* | Full-cost conclusion |
|---|---|---|---|---:|---|
| musique | hipporag2 | llm | Dense дешевле при всех N>0 | нет | Dense дешевле при всех N>0 |
| musique | hipporag2 | embedding | Dense дешевле при равных q | нет | Dense дешевле при всех N>0 |
| hotpotqa | hipporag2 | llm | Dense дешевле при всех N>0 | нет | Dense дешевле при всех N>0 |
| hotpotqa | hipporag2 | embedding | Dense дешевле при равных q | нет | не определяется: неполный учёт |
| musique | raptor | llm | Dense дешевле при всех N>0 | нет | Dense дешевле при всех N>0 |
| musique | raptor | embedding | Dense дешевле при равных q | нет | Dense дешевле при всех N>0 |
| hotpotqa | raptor | llm | Dense дешевле при всех N>0 | нет | Dense дешевле при всех N>0 |
| hotpotqa | raptor | embedding | Dense дешевле при равных q | нет | не определяется: неполный учёт |

[График C(N): пунктир — известный минимум](e4-cost.svg)

Источники, фазы, повторы и неизвестные части: [JSON](e4-cost.json).
Формулы и выводы: [протокол](../../docs/E4_COST.md).

- I is standalone attributed construction including recorded failed histories and RAPTOR Dense leaves.
- q is logical request usage/500, not fresh physical POST expense; reusable pilot usage is not charged again.
- Reader/filter/query embedding included; failures remain in the offered-question denominator.
- EM is aggregate exact match on the same500 IDs, including failures; not F1.
- Quality and mean request mix are assumed stationary for projected N; no additional inference.
- Known minima are lower bounds, not measurements of full cost; reservations are not usage.
- LLM and local BGE tokens are separate units, not money; LLM input/output and mixed indexing models retained.
- Development S500 and historical control-score disclosure retained; no signal selection or control per-case export.
