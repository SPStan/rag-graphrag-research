# E2 pilot200: completed

Run `20a6360f-24f4-4151-a70c-76632d0a81aa`; plan `125dfe5e75afc2fe1bdb2eb4e2d3c174ef113b7ff847cd72dcba2b955472b24b`.

**Учтено1200/1200:**1199completed,1transport failure,0not_attempted.

Development/tuning pilot; one fixed shared-answer-only-v1, cap512. Not independent quality evidence.

| Dataset | Method | EM % | F1 % | Completed / failed / not attempted | Failure % | Passage recall@5 % | RAPTOR provenance % | Fresh E2E s (n) | Reader call s (n) | New R(in/out); F(in/out); BGE(in) | Reused R(in/out); F(in/out); BGE(in) |
|---|---|---:|---:|---|---:|---:|---:|---|---|---|---|
| musique | dense | 33.000 | 43.598 | 200 / 0 / 0 | 0.000 | 61.042 | — | 0.826 (190) | 0.467 (198) | R 295849/1617; F 0/0; BGE 5103 | R 2902/16; F 0/0; BGE 241 |
| musique | hipporag2 | 42.500 | 52.613 | 200 / 0 / 0 | 0.000 | 72.042 | — | 1.842 (190) | 0.456 (198) | R 312657/1543; F 578783/11243; BGE 5103 | R 2933/16; F 30436/647; BGE 241 |
| musique | raptor | 32.500 | 43.491 | 200 / 0 / 0 | 0.000 | — | 62.167 | 3.007 (189) | 0.777 (198) | R 771238/1732; F 0/0; BGE 5103 | R 5867/14; F 0/0; BGE 241 |
| hotpotqa | dense | 59.000 | 70.814 | 200 / 0 / 0 | 0.000 | 87.500 | — | 0.844 (190) | 0.434 (198) | R 276044/1399; F 0/0; BGE 4711 | R 2529/18; F 0/0; BGE 244 |
| hotpotqa | hipporag2 | 69.000 | 79.290 | 200 / 0 / 0 | 0.000 | 94.500 | — | 2.063 (190) | 0.501 (198) | R 282821/1381; F 578474/11809; BGE 4711 | R 2796/18; F 30417/684; BGE 244 |
| hotpotqa | raptor | 57.000 | 70.511 | 199 / 1 / 0 | 0.500 | — | 87.250 | 3.412 (190) | 0.855 (198) | R 641912/1369; F 0/0; BGE 4711 | R 11105/18; F 0/0; BGE 244 |

Reader/filter LLM input/output and embedding tokens are separated in JSON; each cell separates reader(R) input/output, filter(F) input/output and BGE input. Not-attempted is not a wrong answer; incomplete groups have null EM/F1. Known reader failures count as0 only in completed groups.
Cached context/reader results are not fresh latency; source timing provenance stays in private per-case data and is never added across runs. RAPTOR provenance coverage is not passage recall@5.

Pilot physical lineage known: {'llm_input_tokens': 3737778, 'llm_output_tokens': 32093, 'embedding_input_tokens': 29442}; total POST=2708; current run POST=276; new unknown=0; inherited unknown=1; cost_complete=false. Reused source costs are a subset of the separately reported development expense, not additional physical cost. E1known32601955/unknown reserve61588/cost_complete=false separate.

Парные различия (процентные пункты,95%bootstrap CI;2000resamples/seed42,n=200):
- musique, dense−hipporag2: ΔEM -9.50 [-15.00;-3.50]; ΔF1 -9.01 [-14.61;-3.16].
- musique, dense−raptor: ΔEM 0.50 [-4.00;5.00]; ΔF1 0.11 [-4.19;4.49].
- musique, hipporag2−raptor: ΔEM 10.00 [4.00;16.00]; ΔF1 9.12 [3.19;14.86].
- hotpotqa, dense−hipporag2: ΔEM -10.00 [-15.00;-5.00]; ΔF1 -8.48 [-12.76;-4.64].
- hotpotqa, dense−raptor: ΔEM 2.00 [-2.51;7.00]; ΔF1 0.30 [-3.16;3.90].
- hotpotqa, hipporag2−raptor: ΔEM 12.00 [7.00;17.00]; ΔF1 8.78 [5.20;12.89].

Includes mixed Hippo extraction configuration and disclosed source errors; no architecture-only causality. Refs #14; Draft, no merge/holdout/S500.

Сохранённая транспортная ошибка даёт pipeline EM/F1=0, не считается неверным
ответом reader. Её usage остаётсяnull;22545tokens — консервативный reserve, неactual.
Один infrastructure case влияет на200-case mean максимум на0.5pp; POST не повторялся.

Времена собраны в разных прогонах и включают SHA/claim/persistence overhead;
проверка lineage после continuation стала больше. Поэтому E2E — instrumented
query latency, не чистое контролируемое сравнение скорости архитектур. Reader
transport показан отдельно; source/cache времена не складываются с новыми.

Pilot physical known3799313tokens/2708POST; использованный source91871 входит в
development237340, не добавляется дважды. Совокупный E2known4036653tokens/2860POST
плюс1unknown reader (reserve22545), cost_complete=false. E1 учитывается отдельно.

Local tracking:6verified views×200cases, по1000retrieved passages/nodes вкаждой;
reader usage и1unknown проверены,66artifact round-trip SHA совпали. Экспорт —
posthoc представление трёх runs, не новые model calls.

Полнота tracking дополнительно подтверждена по самим traces: в каждом сервисе
точно совпали все6000retrieval и6000generation documents (title,text,order);
в MLflow также совпали все answers, включая отсутствующий ответ unknown case.
Для RAPTOR/MuSiQue33BGE tokens внутреннего stage reuse остаются pilot physical
cost. В Langfuse корректировка атрибуции отмечена событием
`cost-attribution-correction`; старое root metadata поле историческое и заменено
этой явной аннотацией. Суммы physical journal и model usage не менялись.

## Выбор метода по завершённому пилоту

Рабочий выбор для дальнейшего сравнения с Dense — **HippoRAG2 в проверенной
конфигурации**, на двух датасетах, без добавления 2Wiki. Это выбор по tuning pilot,
а не подтверждённое преимущество архитектуры на независимых данных. Reader,
параметры retrieval и индексы после просмотра F1 не меняются.

По сравнению с RAPTOR прирост F1 составляет 9,12 п.п. в MuSiQue
(описательный парный 95% CI [3,19;14,86]) и 8,78 п.п. в HotpotQA
([5,20;12,89]); прирост EM — 10 и 12 п.п. соответственно. Dense и RAPTOR
близки по F1: интервалы их парных различий включают ноль; это не доказательство
эквивалентности. Интервалы описательные, без поправки на множественные сравнения.

Выбор связан с более высоким расходом: известная логическая стоимость запроса,
включая reader, fact filter, BGE и атрибуцию использованного source cache,
составляет около 4718/4567 токенов у HippoRAG2 против 3921/3297 у RAPTOR
(MuSiQue/HotpotQA). Это средние известные суммы на 200 случаев, не цена в деньгах
и не только новые POST. У RAPTOR/HotpotQA дополнительно остаётся один unknown;
его резерв не прибавляется как фактический расход. Fact filter Hippo потребляет
около 3106/3107 токенов на вопрос и не исключён из сравнения стоимости.

Hippo завершил 400/400 случаев; один transport failure RAPTOR не доказывает
ненадёжность его архитектуры. Даже максимально возможные +0,5 п.п. от этого
ответа не устранили бы наблюдаемый разрыв F1. Cross-run latency не служит
основанием утверждать преимущество по скорости. E1 имеет неполный учёт;
полную стоимость жизненного цикла и окупаемость индексации установить нельзя.

**Готовность следующего этапа:** артефакты пилота и рабочий выбор подготовлены
для научного ревью. Запуск задачи 9 пока не разрешён: нужны согласование текущих
O/N/R/H и принятие раскрытых ограничений mixed Hippo/source errors/unknown,
а затем отдельный план и бюджет следующего этапа. Разбор 12 прежних диагностических
ответов не выдаётся за анализ типичных ошибок всех 1200 случаев пилота.
Issue #14 остаётся открытым; Ready/merge и новые эксперименты не выполняются.

**Следующий шаг:** научное ревью этой tuning-таблицы и её ограничений перед
отдельным решением о следующем этапе. Новые эксперименты автоматически не запускаются.
