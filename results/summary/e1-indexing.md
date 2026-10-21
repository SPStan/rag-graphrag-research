# E1: индексация

| Метод | Датасет | Статус | LLM in/out | Embed | POST | Секунды | Полнота | Run ID / index |
|---|---|---|---:|---:|---:|---:|---|---|
| dense | musique | completed | 0/0 | 684560 (+cache 0) | 172 | 113.705 | True | 72cc4f85-7656-44a2-87c0-bbb3df5df81c / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/dense/musique` |
| dense | hotpotqa | completed | 0/0 | 776137 (+cache 0) | 175 | 558.277 | False | f93e2e87-e6e8-4a3a-a2c0-2b88e1bf3319 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/dense/hotpotqa-continuation1` |
| hipporag2 | musique | failed | 2296256/945308 | 684560 (+cache 0) | 4839 | 9964.785 | False | 1379a939-228d-458f-bb90-f120b165f2f8 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/musique-cycle1` |
| hipporag2 | hotpotqa | pending | —/— | — (+cache 0) | — | — | False | 122d943f-7597-4038-863a-ec03f314bafa / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/hotpotqa` |
| raptor | musique | completed | 1720918/1621266 | 1629952 (+cache 684560) | 3852 | 17253.733 | False | 957006e6-5d60-43f6-990d-027851323111 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/raptor/musique-cluster1` |
| raptor | hotpotqa | failed | 928888/884398 | 884117 (+cache 0) | 2828 | 10158.547 | False | ff75d8dd-69d6-4d9e-8e70-fdd63119741c / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/raptor/hotpotqa` |
