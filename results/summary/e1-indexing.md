# E1: индексация

| Метод | Датасет | Статус | LLM in/out | Embed | POST | Секунды | Полнота | Run ID / index |
|---|---|---|---:|---:|---:|---:|---|---|
| dense | musique | completed | 0/0 | 684560 (+cache 0) | 172 | 113.705 | True | 72cc4f85-7656-44a2-87c0-bbb3df5df81c / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/dense/musique` |
| dense | hotpotqa | completed | 0/0 | 776137 (+cache 0) | 175 | 558.277 | False | f93e2e87-e6e8-4a3a-a2c0-2b88e1bf3319 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/dense/hotpotqa-continuation1` |
| hipporag2 | musique | failed | 1620008/664046 | 684560 (+cache 0) | 3476 | 6916.831 | False | 2548f65f-0dd5-4fba-8cc1-d09bf7da6fe1 / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/musique-network1` |
| hipporag2 | hotpotqa | pending | —/— | — (+cache 0) | — | — | False | 122d943f-7597-4038-863a-ec03f314bafa / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/hipporag2/hotpotqa` |
| raptor | musique | pending | —/— | — (+cache 0) | — | — | False | a22458e3-2528-4fa9-b752-a32c15d8b85b / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/raptor/musique` |
| raptor | hotpotqa | pending | —/— | — (+cache 0) | — | — | False | ff75d8dd-69d6-4d9e-8e70-fdd63119741c / `indexes/e1/edff74df-c567-49de-a834-f9f1fc6f7f74/raptor/hotpotqa` |

Seconds include the prior failed run when cumulative_seconds is present. Unknown usage remains unknown.
