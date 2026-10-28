# ADR-0028: offline freeze S500, точный reuse и новый бюджет

Статус: принято для offline-подготовки issue #15 по текущему поручению
пользователя. Это не разрешение на генерацию и не выбор сигнала issue #21.

## Контекст и решение

Пилот содержит 1200 terminal cases: 1199 ответов и один sealed transport
failure. Полный набор — Dense/HippoRAG2/RAPTOR × MuSiQue/HotpotQA × 500
прежних ordered S500 IDs. RAPTOR сохраняется в сравнении независимо от выбора
Hippo для будущего каскада. Перестройка шести индексов не требуется.

`full-experiment.json` фиксирует версии, параметры, входы, каждый case reuse
и missing-set. Команда `scripts.full_experiment` использует существующие
`load_ready_e1`, `result_references`, `lineage_records`, `verify_saved_case`,
`seal_unknown_reader`, payload/parser и terminal journal verifier.
Модельный транспорт и прямые socket connections запрещены на всём аудите.
Обрабатываются только corpus, queries и tuning-pilot artifacts; labels лишь
хэшируются. Значения gold/metrics отложенных частей не открываются.

Совместимость устанавливается по вопросу, corpus/index SHA, reader/filter/
retrieval/model/options/parser/evaluator и точному payload, checkpoint, response,
producer journal/usage. Смена Git HEAD из-за merge не меняет payload. Execution
runtime SHA и исходные плановые code hashes остаются отдельно от проверяющего
кода. Inference/evaluator modules сверяются с последним runtime; для изменённого
только в accounting `e2_pilot` дополнительно сверяется AST функций reuse.
Старые Thought answers не являются кандидатами; исходный Thought retrieval
может использоваться лишь через уже проверенный pilot context provenance.

Отсутствующий/повреждённый **ссылаемый** артефакт — incompatible, не новый
вопрос для незаметного повторного вызова. Любой incompatible блокирует успешный
verify. Public manifest не содержит текстов, ответов или абсолютных путей.
При переносе хранилища старые планы не редактируются: используются явные roots.

Sealed unknown из ADR-0027 переносится в полный набор как terminal failure:
его identity/reservation сохраняются, reader не повторяется, usage остаётся null.
Pipeline EM/F1=0 для этого infrastructure failure не называется неправильным
ответом reader. Это решение фиксирует прямо запрошенное сохранение failure,
не распространяет прежнее разрешение пилота на новые запросы.

Known reader length/empty/parser failures завершают конкретный case без retry;
остальные cases могут продолжаться. Budget/pin/transport/unknown/infra ошибки
останавливают очередь. Hippo malformed filter остаётся fatal; только валидный
пустой filter допускает native DPR. Retry=0, recovery не разрешён.

## Бюджет и вход

Forecast: средний logical **known** usage операции в соответствующей pilot
конфигурации × missing cases; reader input/output, filter и BGE отдельно.
Unknown исключён из знаменателя известных операций, не превращён в ноль.
Это прогноз, а не гарантированный расход. Верх POST: один reader и один BGE
на missing case, дополнительно до одного filter для Hippo. Межметодный reuse
query embeddings не предполагается без нового проверенного механизма.

Reader bound строится существующим `input_size_bounds`: самый длинный из
500 вопросов и пять крупнейших escaped title/text из корпуса или всех RAPTOR
nodes. Это верх serialized messages в **байтах**, не токенах. Без truncation;
выход за прежние 65536 блокирует freeze. Для filter используется консервативный
admission bound 65536; фактический набор candidate facts заранее не вычисляется
без retrieval. Поэтому его data-dependent размер не объявляется измеренным.
Ограничение транспорта действует до POST; будущий execution-plan должен
сохранить этот preflight, а не повышать cap по одному случаю.

Token reservation: reader bound + 1024 envelope + 2048 allowance + 512 output;
filter 65536 + те же allowances; BGE exact serialized question payload + 2048.
Эти байтовые резервы — консервативная политика существующего transport,
не оценка tokenizer window. Backend alias/revision/quantization остаются явно
неизвестными, где сервер их не сообщал.

Физические journals считаются один раз; logical replay не прибавляется.
Development включает source cost, E1 отдельно. E1 reserve61588 и E2 reserve22545
не actual usage; cost_complete=false. Снятие административного90M не отменяет
research caps: E1 indexing68M и старый pilot57189854/2708POST были scoped.
Pilot POST исчерпаны. Новый рассчитанный предел — **предложение**, требующее
отдельного execution-plan/разрешения в следующих issues; manifest не executable.

## Разбиение, альтернативы и проверка

Сохраняются seed42, порядок S500, pilot[0:200], tuning[0:300],
signal-check[300:400], исторический reserve[400:500]. Пилот целиком tuning.
Вся S500 описательная, включает разработку. Сигнал, направление и порог
выбираются в issue21 только на tuning до анализа check gold/metrics.
Предвычисленный ответ не даёт допуска к такому выбору. Прежний просмотр
MuSiQue первых100, позиций200–299 и примера482 не скрывается; отсутствие
истории не доказывает нетронутость. Reserve не становится новым test set.

Отклонены повтор всей S500 (лишние расходы/нарушение sealed failure), reuse по
F1 (утечка выбора), и сравнение только HEAD (merge не меняет семантику).
Проверка: целевые regression tests, реальный immutable artifact audit без HTTP,
затем обязательный offline gate. Пересмотр нужен при смене значимых входов,
payload/model/options/retrieval, несовместимости/недоступности artifact или новом
разрешённом протоколе; старые результаты и execution pins не переписываются.

Источник корпуса закреплён как `osunlp/HippoRAG_2` с revision и SHA
`data/sources.lock.json`; текущие processed corpus/query bytes проверяются отдельно.
Endpoint reader и embedding backend входят в значимый контракт наряду с моделями;
равенство alias не позволяет незаметно перенести reuse на другой backend.

CI history scan выявил восемь false positives в двух новых minified manifests:
три runtime SHA файла `scripts/token_accounting.py` и один hash sealed case в
каждой версии. Каждый SHA сверен с Git blob LF/CRLF соответствующего runtime,
case ID — с SHA256([dataset,method,published tuning ID]). В `.gitleaksignore`
добавлены только два точных commit:path:rule:line fingerprints, как в прежнем
протоколе репозитория. Текущие pins представлены парами file/sha256, sealed ID
назван `case_id_sha256`; значения не менялись. История не переписывается,
новые commits/values продолжают сканироваться, secret checks остаются обязательны.
