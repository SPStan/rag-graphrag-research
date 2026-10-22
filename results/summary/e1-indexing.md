# E1: индексация

| Метод | Датасет | Статус | LLM in/out | Embed | POST | Секунды | Полнота | Run ID / index |
|---|---|---|---:|---:|---:|---:|---|---|
| dense | musique | completed | 0/0 | 684560 (+cache 0) | 172 | 113.705 | True | 72cc4f85-7656-44a2-87c0-bbb3df5df81c / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/dense/musique` |
| dense | hotpotqa | completed | 0/0 | 776137 (+cache 0) | 175 | 558.277 | False | f93e2e87-e6e8-4a3a-a2c0-2b88e1bf3319 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/dense/hotpotqa-continuation1` |
| hipporag2 | musique | failed | 5430111/2013767 | 1172238 (+cache 0) | 12901 | 33462.565 | False | acdf13d5-7a3b-4748-8e34-348a02b28788 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/musique-mixed-counter1` |
| hipporag2 | hotpotqa | pending | —/— | — (+cache 0) | — | — | False | b35858cb-cdd6-4697-885c-aba960a2b526 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/hotpotqa-mixed-counter1` |
| raptor | musique | completed | 1720918/1621266 | 1629952 (+cache 684560) | 3852 | 17253.733 | False | 957006e6-5d60-43f6-990d-027851323111 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/raptor/musique-cluster1` |
| raptor | hotpotqa | completed | 1852868/1740267 | 1736946 (+cache 776137) | 4180 | 19623.594 | False | bb177a66-f03d-4a43-979e-d53c11821903 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/raptor/hotpotqa-summary-network1` |
