# ADR-0024: общий reader на готовых E1 индексах

Дата:25 октября2026. Статус: smoke10 и отдельно разрешённый continuation v2 завершены;
43completed/17reader length/0not_attempted. Полный pilot E2 не выполнен.
Refs #14; зависит от PR33/f8b9bb8. Протокол smoke — [E2_EVALUATION](../docs/E2_EVALUATION.md).

## Контекст и выбор

Шесть E1 индексов completed, но shared loader не загружал Hippo. SDK constructor
создаёт mutable stores/locks/OpenIE; использовать его для query-only чтения нельзя.
Выбран тонкий QueryOnly adapter: проверенные artifacts → родной read-only Parquet
loader/graph → native prepare_retrieval_objects в RAM → native fact scoring,
DSPyFilter и PPR. Constructor/index/OpenIE/store writes исключены. Rebuild/копия
всех индексов не нужны; реализация собственного поиска/PPR исказила бы SDK.
Native valid-empty filter сохраняет DPR fallback; transport/parser failure fatal,
поскольку SDK иначе маскирует их под empty. Содержательные ошибки retrieval не
лечатся prompt retries. Reader/parser/evaluator едины и уже существуют.

## Последствия

Общий reader использует существующий MuSiQue one-shot на обоих наборах; это
раскрытая неоптимизированная Hotpot конфигурация. Top5 RAPTOR nodes возвращаются
без дополнительного прежнего 3000-token отсечения; после retrieval общий предел
messages32000UTF8 bytes, overflow=stop. RAPTOR passage recall не сопоставим с
Dense/Hippo: только provenance coverage отдельно. Byte gate не native tokenizer.

Query LLM только Qwen, filter512/reader512/temp0/seed42/thinkingfalse. Existing
Qwen/GPT extraction E1 не переименовывается и не пересчитывается; выводы относятся
к конкретным конфигурациям с observed extraction errors. Native query embedding
instruction_mode=ignored совпадает с E1 BGE; один normalized vector для facts и
passages внутри Hippo. Отдельные query embeddings на каждом method/question
позволяют измерять actual query latency/cost без cross-method cache ускорения.

Canonical plan claim, exact payload checkpoints и durable journal исключают
повтор при неизвестном исходе. Успешный replay физически бесплатен; логическая
стоимость и исходная latency сохраняются отдельно. Failed/not-attempted не
исключаются из знаменателя. Verification read-only, export отдельный.

## Проверка и пересмотр

Synthetic tests: gold isolation, common prompt, incompatible pins до HTTP,
reported usage/time на errors, безопасный replay и запрет uncertain resume.
На обоих real Hippo графах проверены PPR/DPR и исходный PermissionError; index/
constructor/HTTP запрещены, SHA artifacts до/после совпали. Dense/RAPTOR на обоих
наборах возвращают top5, для nodes проверены levels/provenance, HTTP запрещён.
Ни одна из этих проверок не является QA benchmark. Изменение reader/top-k/options/
SDK/evaluator/index pins делает результаты несовместимыми; отдельный план до
новых запросов. Критерии не меняются из-за неверных ответов smoke.


## 25октября: continuation v2 — reader outcomes отдельно от fatal execution

По прямому поручению после исходного stop принимается offline policy
`reader_known_response_failure_continue_v2`. Исполнение требует отдельного допуска
нового exact plan, прежнее разрешение этого изменения не покрывает.

Known-usage завершённый HTTP reader response с length/empty/непригодной формой/
неприменимым parser — attempted_failed, answer не принимается, повторного POST нет.
Другие случаи продолжаются с теми же cap512/prompt/temp0/seed42/thinkingfalse.
Отсутствующий usage, HTTP/transport/infra error, изменённые pins/config или бюджет —
fatal stop. Эта политика не переносится на Hippo filter: length, malformed и error
там fatal; valid empty facts сохраняет native DPR. Semantic correctness не определяет
retry; gold читает только evaluator после generation.

Original failed manifest/claims/журналы/ответы остаются у parent. Child pin-ит19файлов,
сверяет scientific contract и AST неизменённых reader/embedding payload functions
с5dea658; immutable retrieval/evaluator/SDK/data pins прежние. Старые три случая
(2completed+1knownlength) пропускаются целиком, не выдаются за новый cache hit под
изменённым prompt. Фактические source options/run/code/response SHA сохраняются.
Допускается один child из этого parent, новый output/journal/run, без снятия общего
запрета повторного запуска failed. При успешной технической паузе одного child
повторный вызов пропускает terminal cases; unknown/failed не ретраится.

Остаются57cases:57query embeddings+57reader+≤20filter=134POST. Conservative reserve
77×(32000+1024+2048+512)+57×(4096+1024+2048)=3148544tokens≤3271113остатка.
С учётом parent:≤140POST, known5687+новыйreserve≤3154231≤3276800.
Bound не actual usage и не денежная цена; local embedding/LLM input/output отдельны.

Completed, attempted_failed и not_attempted различаются. Только attempted failures
имеют EM/F1=0; not_attempted получает null и делает сравнение неполным. На завершённом
smoke denominator=10/cfg, failures входят; публикуются failure rate, mean attempted
latency и usage by model. Parent+child journals суммируются один раз по physical
identity,60case keys включают dataset/method/question. E1 historical cost_complete=false
и reserve61588 остаются отдельной атрибуцией. RAPTOR provenance не passage recall@5.

Проверки: actual parent/all6source manifests/artifacts offline, synthetic existing
runner/CLI на60cases, success+reader outcomes+resume; parent SHA/config/model/unknown/
budget/transport rejection, filter fatal, no duplicate expense. Новых real calls нет.
После реального smoke — одно решение: freeze reader для pilot200 либо единый пересмотр
для всех методов при технической проблеме; не выбирать конфигурацию по лучшему F1.

## Наблюдение после разрешённого continuation v2

Exact plan723a9993…0ffe6, execution537fa023, child3bee5af5…1171:
60уникальных случаев,43completed/17attempted_failed, неизвестных/незапущенных0.
Все failures — length при неизменном reader cap512; partial не приняты, retry0.
Совокупно140POST/209108known tokens с parent один раз, filter включён,
LLM188118input/19535output и BGE1455 отдельно. E1 incomplete cost не меняется.
Это диагностическая таблица конкретных конфигураций, не подтверждение H1/эффекта
архитектуры на независимых данных. Условие пересмотра reader сработало по17/60length,
поэтому предложен один общий пересмотр для всех методов до pilot200, не поиск
лучшего F1. Изменение reader ещё не принято/не запущено: отдельная версия и план,
без смешивания с этими результатами. [Таблица](../results/summary/e2-smoke10-continuation.md).

## Предложение: один shared answer-only diagnostic (не новый benchmark)

Offline-аудит actual payload/saved responses: модельQwen27b, temperature0/seed42,
max_tokens512, chat_template_kwargs.enable_thinking=false;4chat messages,
один vendor one-shot, chat template повторно клиентом не применяется. Once journal
60reader+20filter не содержит retries.17length имеют reasoning_tokens=0, но старый
system буквально требует «methodically break down the reasoning process», user
заканчивается Thought, а demonstration содержит рассуждение. Клиентская ошибка
не найдена; роль подробного text reasoning в length — гипотеза, не измеренная причина.

Выбран один кандидат shared-answer-only-v1 для всех методов/датасетов. Сохраняются
тот же demo context/question, native top5/context order, parser, модель/options/cap512.
Удаляются только Thought suffix и reasoning в assistant demo; demo Answer:1862.
System точно:

```text
Answer the question using the supplied passages. Return exactly one line: Answer: <concise answer>. Do not include reasoning, analysis or explanation.
```

Не меняются ready E1 artifacts/old reader payload function/old results/costs.
Новая reader version не совместима со старой таблицей; successes старого reader
не переносятся в результаты нового. Для диагностики заморожен уже оплаченный
retrieval output (включая Hippo filter): новых retrieval/LLM filter/embedding нет.
Это намеренно cached-context проверка output contract, не end-to-end latency/quality.

На каждом датасете фиксируются первый tuning ID с любым reader failure и первый
другой ID, completed у всех3методов; используются только completion statuses,
не правильные ответы/метки/F1. Все3метода отвечают на оба ID. Это enriched diagnostic,
не случайная/независимая оценка частоты ошибок. Gold/evaluator/holdout не читаются.

Точные payload и347source/checkpoint/response pins находятся в private plan
`.cache/e2-answer-only-diagnostic-plan.json`; full text не коммитится. File SHA:
`1b816118b0f2b5574abeb1e384fcde61a391f6bca9fe45a78b00a2649a71cf8b`.

| Dataset | Method | Question ID | New payload SHA256 |
|---|---|---|---|
| musique | dense | 2hop__21104_16334 | d078e878e9b9678c838f7ba66f77466095bb53bfbc2e96092bf8e310502fdfd2 |
| musique | hipporag2 | 2hop__21104_16334 | 035d9862461c5df5728f14db0bfbc3a0f5c6b6cfafda5f635685166d26c7eded |
| musique | raptor | 2hop__21104_16334 | c1714af5acad6cfceb3f1fbef881a3614025a54fcc7f1f4c46591a8f2bbddd86 |
| musique | dense | 3hop1__593288_720914_27537 | e74d46d5d8efa15fb60951780327ce54bc8a30aa4025c1f30b25bf32725e4485 |
| musique | hipporag2 | 3hop1__593288_720914_27537 | 62bca46508d54953e5984c273f3768543a3c0b7a92423f10d1c5456831d5d44d |
| musique | raptor | 3hop1__593288_720914_27537 | 3dc754a353b282c2e4decf612da15e3450809ee3f2240719b1dfc739d5a4f568 |
| hotpotqa | dense | 5abd882f55429924427fd045 | e98605471d45a106fc4eef9ce4f2b4978e590514534eca268b52f606bb830367 |
| hotpotqa | hipporag2 | 5abd882f55429924427fd045 | 8a57f24e987408c2f33b2db84762467bc7100621cbdfe80be51aa186e9ff15df |
| hotpotqa | raptor | 5abd882f55429924427fd045 | 9ac8d3a964af564147bd2005b6c0686959ebc047fc42da804718afa3de4374a7 |
| hotpotqa | dense | 5a78ed6855429970f5fffdd9 | 336e7becac6f1bc00dbcc488181b95e11e9efc604c20204a45d24f3a5b9bedc4 |
| hotpotqa | hipporag2 | 5a78ed6855429970f5fffdd9 | 4c661b91fd8472a43eff214393485936f1ff8eac946b7976d14882dfaf5fd838 |
| hotpotqa | raptor | 5a78ed6855429970f5fffdd9 | 84a7ac52cf0e47a12955dd0d7a3058dcaa4aca0a84c05c48632ddf5d32743e4c |

Лимит12новых внешних reader POST, по1на случай, retry0/redirect0, connect30/read300.
Резерв152350combined tokens = сумма UTF8 serialized payload bytes+2048+512 по12payload;
это conservative upper reservation, не actual tokenizer count и не денежная цена.
Новые embeddings/filter POST0. Прежние209108query tokens/140POST не переучитываются,
E1known32601955/reserve61588/cost_complete=false сохраняются отдельно.
Старый smoke POST budget исчерпан: **новый diagnostic budget требует отдельного
согласия на exact plan**; текущая подготовка не разрешает HTTP.

Первый length/empty/неоднозначный или многострочный Answer/наблюдаемый цикл
(8слов повторены3раза подряд)/unknown/transport/HTTP/pin/budget error — terminal stop,
без другого prompt/cap/model/retry. Raw responses/usage/exception остаются в новом
output; canonical once claim запрещает повтор через другую папку. Transport разрешает
только12замороженных reader bodies, блокирует embedding/filter/другие payload.

Технический pass: все12 finish_reason=stop, usage известен, ровно одна непустая
строка Answer и нет указанного цикла. Затем обязателен source-only audit всех12:
unsupported claims, потеря оговорок и несоответствие вопросу должны быть раскрыты;
неясность помечается needs_review. Технический pass не доказывает фактическое качество.
Нет автоматического принятия reader/pilot200: отдельное решение после source audit,
без перебора prompt по F1/проб по одному ответу и без смешивания версий результатов.
Existing runner/Calls/Journal переиспользованы; отдельного runner/framework нет.

## Фактическая answer-only проба — 25 октября

Пользователь ответил «Продолжай» на конкретный запрос12POST/152350tokens/exact SHA
1b816118…71cf8b. Runtime22e4553, run eb9668ff-ef12-45c5-ac4e-4c52f868a84c.
Все12ответов — stop/одиночный Answer/known usage; reasoning_tokens0, неизвестных,
unfinished и новых filter/embedding/retrieval/indexing calls0. Новые токены:
28132LLM input/100output=28232, в пределах152350; использованы все12POST.
347source pins/checkpoint/response SHA неизменны. Старые readers/results/claims
и их209108tokens/140POST не переписывались; cumulative query237340tokens/152POST.
E1known32601955/reserve61588/cost_complete=false по-прежнему отдельно.

Source-only audit всех12методических случаев (4вопроса, enriched по old completion):
7supported/2observed_error/3needs_review. Это не error rate/generalization estimate.
Оба old-length случая перешли к короткому полному ответу, но:

- MuSiQue/Hippo2hop__21104_16334 подставил результат исследования другого года/
  другого genetic comparison; искомое исследование в его retrieved context отсутствует.
- HotpotQA/Dense5abd882f55429924427fd045 подставил дату другого магазина из distractor;
  контекст идентифицирует нужную компанию, но не содержит её founding date.
- Три Roncalli case (по1на метод) содержат direct evidence причины отъезда,
  но не всю painter/death-place связку. Это needs_review полноты grounding,
  не доказанная неправильность самого короткого ответа.

Для RAPTOR ответные утверждения проверены в оригинальных descendant passages,
включая связь lake/town/population и историческую оговорку census2010. Descendant
coverage само по себе не выдаётся за сохранённый в summary факт или passage recall.
Для всех случаев source snippets/ID/SHA и raw model response сохранены private:
`results/raw/e2-answer-only-diagnostic-v1/source-audit.json`,
`original-source-proof.json`; gold/evaluator/F1/holdout не использовались.
Codex review не является независимым human review. Raw terminal manifest неизменён;
отдельная assessment завершает аудит без задней правки результатов worker.

Вывод ограничен: technical output-contract pass подтверждён на12случаях, качество
и полная faithful grounding не подтверждены. Reader автоматически не принят,
общая smoke43/17 таблица не смешивается с новой версией. Единственное предложение:
зафиксировать один shared-answer-only-v1 для отдельно согласуемого плана pilot200,
раскрыв обычные retrieval/reader errors, без prompt/cap search по этим ответам.
Новый pilot или дальнейшие модельные запросы этим результатом не разрешены.
