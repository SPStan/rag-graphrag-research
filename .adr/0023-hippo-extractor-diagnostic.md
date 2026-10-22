# ADR-0023: диагностика другого extractor отдельно от benchmark

Дата:22 октября2026. Статус: **предложение**; ни смена benchmark, ни расходы
не приняты этим ADR. Связь: ADR-0022, issue#13, Draft PR#33/Refs #13.

## Контекст

Hippo Qwen повторил cycle/length после uniqueness prompt и shape schema.
Причина неизвестна, новой клиентской ошибки при offline-аудите не найдено.
Готовы Dense×2/RAPTOR×2;3102полных Qwen NER+triples сохранены и не являются
готовым Hippo graph. Ожидание оператора не требуется для offline-подготовки.

## Предлагаемое решение

Один ограниченный source-only diagnostic iairlab/gpt-oss-120b:3известных failed
passages и2фиксированных successful controls, максимум5POST/44124 reserve,
cap3072, temperature0/seed42, reasoning_effort=low, shape schema без uniqueItems,
без Qwen chat_template_kwargs, без retry/нового NER/embedding. Точные identities,
бюджет и stop/semantic gates зафиксированы в E1_INDEXING и private prepared plan.
Заявленные куратором context131k/JSONSchema/reasoning — не измерение deployment.
Параметр low соответствует [vLLM GPT-OSS recipe](https://github.com/vllm-project/recipes/blob/main/OpenAI/GPT-OSS.md);
это источник выбора параметра, не доказательство поддержки на нашем endpoint.
Не создавать Harmony/template вручную: endpoint получает messages.

Перед POST нужны отдельное согласие пользователя, clean pinned HEAD и plan SHA.
Machine success → awaiting_source_review всех5 по исходному тексту; JSON-only
success не принимается. Любой отказ/unknown/length/недостоверное содержание
останавливает план. Скрытого перехода к full corpus/следующей модели нет.

## После разрешённой диагностики: источник и область утверждений

Пять GPT-OSS ответов дали полный JSON/stop/known usage6105, но source review
не прошёл. Это не доказывает качество модели или исправление Qwen cycle.
Диагностика разрешена пользователем отдельно и исполнена; смена benchmark остаётся
предложением. Старые ответы/manifests immutable, GPT cache не принят в Qwen.

Одна offline policy source_faithfulness_v1 добавляет system rules: attribution,
uncertainty/negation/quantifiers, disjoint dates, correct modifier attachment,
no outside repairs. Она не содержит исправленных triples/QA gold или особых правил
для конкретных имён. Применимость к пяти замечаниям проверена source-only;
действие инструкции на генерацию не измерено. Один общий вариант обоим датасетам.

run_e1 prepare-extractor-policy проверяет происхождение отрицательного review и
готовит exact payload candidate; новая request identity сохраняет изменение prompt.
Candidate намеренно не исполняется существующим transport. Следующий вариант
потребует отдельного executable plan/claim, допуска расходов и решения о cache;
подготовка не расходует предложенный reserve48929 и не разрешает новый POST.
После повторного semantic failure — разбор протокола вместо новых prompt retries.

## Техническая готовность одного source-policy follow-up

Отдельный executable proposal hippo_extractor_policy_probe_v1 готовит те же payload,
что проверенный candidate10e82514, и использует existing execute_schema_probe.
Новый output/run, canonical exclusive claim у предыдущего GPT producer и проверка
negative review/parent budget запрещают повторные дочерние попытки между output
folders. Aggregate export включает обе GPT-пробы/старый history ровно один раз;
unknown сохраняется. Transport retry0/timeout30/300/cap3072,5POST/48929reserve.

Это только механизм исполнения после отдельного разрешения точного plan SHA/HEAD.
Old offline candidate не разблокирован. Пока POST0, policy generation не проверена.
После успеха всё ещё необходим source review всех5, решение benchmark/cache и
отдельный continuation plan/расходы. После semantic failure не вводить следующий
prompt retry без разбора причины и принятого изменения протокола.

## Итог разрешённого follow-up: смена benchmark не принята

Plan614b9318/runtime73ab428, run81df270e:5POST/7190known tokens, все stop/full JSON,
новый unknown0. Поправлены fiction attribution и disjoint dates на двух случаях;
неподтверждённый modifier attachment и параллельные qualified/unqualified edges
остались. Strict source review не пройден; private review948ac856, details E1_INDEXING.
Производящие manifests не изменены, GPT ответы не приняты в Qwen cache.

Два содержательных отказа завершают этот prompt-fix путь. Нового sampling/cap/
prompt перебора не предлагаем. Следующий выбор — сохранить строгий gate и4/6
либо отдельно предложить приёмку явно шумного extractor с source audit. Последнее
меняет критерий и конфигурацию SPEC; необходимо upfront решение о допустимых
ошибках, единых правилах обоим датасетам и cache, актуальное O/N/R/H и отдельный
continuation budget/допуск. Текущее отрицательное заключение не заменяется успехом.
Это протокольный выбор, не обязательное ожидание оператора. Ни один вариант
benchmark ниже этим результатом автоматически не принят.

## Решение о benchmark после пробы — ещё не принято

A. Сохранить исходный единый Qwen extractor:3102пары reuse при точных request/SHA,
но подтверждённого исправления Qwen пока нет. Нельзя возобновить его вслепую.

B. Явная конфигурация Qwen NER + GPT-OSS triples (одинаково обоим датасетам).
Это hybrid extractor, а не прежний Qwen benchmark. Нельзя просто подмешать
GPT triples в Qwen identity. Для однородной такой конфигурации потребуется заново
извлечь triples всех passages, включая3102старых; совместимый Qwen NER reuse.

C. Qwen primary + GPT-OSS fallback только после определённого length/cycle.
Это **смешанная** конфигурация. Старые3102Qwen пары можно сохранить лишь при явном
принятии mixed cache и одинаковой fallback policy обоим датасетам. В каждом cache
entry — реальная producer model/request/response SHA и provenance. Диагностика
сама не выбирает C и не доказывает прежнюю сопоставимость с Dense/RAPTOR.

D. Полностью GPT-OSS OpenIE (NER+triples): новые NER и triples всех5500на датасет,
до11000LLMPOST/dataset до любых ошибок. NER этим diagnostic вообще не проверен.
Нужен отдельный проверенный контракт/бюджет. Старый Qwen cache не переименовывать.

После выбора B/C/D граф строится заново из принятых полных extraction; embeddings
изменившихся entities/facts пересчитываются. Exact unchanged chunk/vector inputs
можно reuse только при SHA/model/dimension совместимости; newline→space Hippo
не даёт права автоматически подставить Dense vectors. Готовые Dense/RAPTOR не
пересчитывать без конкретного изменения их собственных входов/параметров.
Failed/probe/unknown сохранять в physical cost, исторический unknown не становится0.

## Альтернативы, последствия и проверка

Поднимать cap/дописывать partial/дедуплицировать незавершённый JSON отвергнуто:
это не исправляет цикл и пропуски. Перебирать sampling параметры без основания
или новую holdout выборку не планируем. Архив оператора уже есть; его отправка
требует адресата/отдельного разрешения и не заменяет source review.

Offline gates проверяют noHTTP, claim once, exact reconstruction/SHA,5POST cap,
first-error stop, actual model journal, unknown reserve, no double physical cost,
read-only load4готовых индексов и synthetic retrieval→common reader→evaluator.
После успешной диагностики сначала отдельное решение конфигурации/согласование
O/N/R/H по BOT_REVIEW_WORKFLOW, затем bounded continuation plan/разрешение.
Полный E2 требует6готовых проверенных индексов и отдельного допуска.
Пересмотр: фактическая несовместимость GPT payload, неполный/неподдержанный source
extraction или принятый другой исследовательский протокол; автоматического перебора нет.
