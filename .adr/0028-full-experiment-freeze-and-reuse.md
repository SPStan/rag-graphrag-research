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

Forecast: средний usage только **полностью измеренных** logical операций
в соответствующей pilot конфигурации × missing cases. Для input/output reader,
filter и BGE суммы и знаменатель берутся из одной complete-подвыборки.
Отдельный `known_subtotal` сохраняет все известные токены partial operations;
`partial_operations`, `fully_unknown_operations` и `unknown_fields` сохраняют
неполноту. Например100input/10output и50input/unknown дают150known input в
учёте, но forecast100input/10output при знаменателе1. Fully unknown и отсутствие
complete observations дают null forecast и не позволяют вывести operational cap.
Это complete-case прогноз, не утверждение, что missing usage случаен.
Верх POST: один reader и один BGE на missing case, дополнительно до одного
filter для Hippo. Межметодный reuse query embeddings не предполагается.

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
Pilot POST исчерпаны. Static worst-case не является операционным бюджетом.
Выбранный ниже empirical operating cap — **предложение**, требующее отдельного
execution-plan/разрешения; manifest не executable.

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


## Операционный бюджет — предложение, бюджетный критерий ещё открыт

Один вариант: для каждой пары configuration/operation взять максимальный
**полный** расход пилотной операции и умножить на число новых вызовов; сложить
все allocations и добавить один максимальный admission reserve запроса.
Так запас получается из наблюдаемого диапазона расходов и требований admission,
а не из округления до удобного числа. Это отдельный empirical operating cap;
сумма всех статических worst-case reservations114669441 остаётся отдельно.
Операционные allocations — основание одного общего лимита, не новые настройки
методов или раздельные возможности повторного запроса.

Перед каждым POST будущий отдельно approved execution-plan должен требовать:
`new_known + new_unknown_reserves + in_flight_reserves + candidate_reserve <= cap`,
а также остаток total/per-operation POST. Один последовательный worker, reserve
до транспорта; `candidate_reserve` по реальному serialized payload UTF8 bytes
+2048+max_tokens для LLM. Mean и pilot maximum не заменяют admission guard.
Существующий checked_post проверяется offline-тестом на ноль POST при нехватке
лимита; интеграция полного S500 execution-plan всё ещё не выполнена/не разрешена.
Usage сохраняется до проверки ответа, partial/unknown/transport/pin/budget error
останавливает очередь; не освобождать unknown reserve и не продолжать автоматически.
Гарантия pre-admission относится к принятой conservative reservation policy;
она не доказывает фактическое окно/скрытые расходы backend. Нарушение этого
контракта надо сохранить и остановить, а не скрыть потерей known usage.

Этот operating cap **не гарантирует** завершение1800cases: новые запросы могут
оказаться дороже пилотного максимума или следующий reserve уже не поместится.
Тогда stop до следующего POST, отчёт о недовыполненном наборе и новое решение.
Исторические known/E1/development расходы и reserve22545 не входят в новую
allocation и не учитываются повторно; старый unknown остаётся отдельным.
До согласования operating cap критерий бюджета issue15 не выполнен, в PR
используется Refs #15. Согласование бюджета само по себе не запускает модели.


Реальная пересборка: partial0/fully unknown1; forecast5841708.693 не изменился.
Операционное предложение10903320=10834200(sum missing×pilot max complete cost)
+69120(single largest admission reserve), ≤4200POST. Запас над mean forecast
5061611.307. Static worst-case114669441 — отдельная величина. Согласования
операционного cap пока нет; бюджетный критерий issue15 открыт.


## MuSiQue-only разрешение и extension issue16

2026-10-29 пользователь делегировал выбор бюджета с запасом и разрешил его;
точная цитата и границы в `e2-musique-s500-authorization.json`. Для Mu выбрано
5990220новых combined tokens/2100POST=5921100pilot maxima+69120admission.
Это не blanket API authorization и не согласие на HotpotQA/весь cap10903320.
Старый worklist и full freeze не переписываются: новый private execution-plan
отдельно фиксирует согласие,600immutable source cases,500IDs и runtime pins.

Минимальная версионная extension существующего shared runner сохраняет legacy
AST полностью; alternative отдельный runner отклонён из-за дублирования
payload/evaluator/claims. До нового POST проверяются scope, parent pins,
per-operation/total POST caps и known+reservation≤cap. Unknown/partial/infra
останавливают очередь, automatic retry/recovery0; бюджет не гарантирует finish.
Offline проверка через реальный CLI с fake transport охватывает reuse, ошибки,
pins и расходы; реальные source/index проверки полностью offline. Пересмотр:
новый reader/index/split либо исчерпанный cap требует отдельного решения;
этот протокол не подбирается по F1 и не разрешает новые исследования.


## Применение unknown-stop на MuSiQue

Run7936654d остановился на remote reader ConnectionError/RemoteDisconnected:
ответ не получен, usage null, reserve15732 не actual. Новые700completed+1failed,
199not_attempted;600parent cases сохранены. Соблюдён stop без retry/recovery,
не снят общий failed guard. Техническое ночное разрешение пользователя не
переопределяет unknown policy. Кодовый дефект не установлен; исправление кода
не подменяет неизвестный outcome. Для следующего решения сохранены residual
3721696tokens/398POST после reserve и immutable partial artifacts; сами residual
лимиты не разрешают новый запуск. Автоматизация прекращает polling после
уведомления. Полное сравнение1500cases пока не подтверждено.


## Принятое решение после уведомления об unknown

Прямой ответ пользователя «Делай то что нужно» на запрос решения о199unattempted
разрешает один missing-only child исходногоS500run. Текст/контекст/границы записаны
в e2-musique-s500-unattempted-authorization.json. Альтернатива повторить unknown
отклонена; остановленный parent сохраняется failed с исходнымnull usage.
Existing seal_unknown_reader проверяет embedding, exact reader payload/objectID,
started checkpoint, отсутствие response и ровно один attributed unknown.
Его infrastructure outcome учитываетсяpipeline0 с marker, не как неверный reader
answer. Это расширение существующего S500 plan/guard, не снятие failed-run запрета.

Parent plan строго pinned к99d5e846/runtime e144ad9 и повторно строится с теми же
contract/data/index/source настройками; только child code pins новые. Parent claims
и все artifact SHA остаются immutable; child использует новый plan/output и durable
claim родительского snapshot. Вторая такая sealed-unknown child запрещена.
Root cap5990220/2100 не растёт: child≤3721696tokens/398POST после known2252792 и
reserve15732. Unknown usagenull сохраняется и не получает вымышленного0.
Целевые offline tests должны пройти через existing runner и проверить ровноmissing,
неизменные parent bytes, budget conservation, sealed case no POST, запрет tamper/
active lock/claim/second child и отсутствие двойного учёта. Per-POST admission и
остановка на новой transport/unknown сохраняются; окончание не гарантируется.


## Проверенный результат и postprocessor boundary

Unattempted childba393849/runtimea0 завершил199/199 с398POST/802989known,
0newunknown. Итог1500expected:1499completed+1sealed historicalfailure.
S500newphysical3055781known/2100POST,Mu unknownreserve15732; parente144/failed
иsource claims/results/journals immutable. Полный common evaluator, ID/SHA/
lineage audit,3localMLflow/Langfuse500caseviews/fulltext иartifactroundtrip
проверены. РасходE1иoldHotunknown сохраняетсяотдельно, cost_complete=false.

Послеterminal обнаружен posthoc pagination defect: nativeAPI отдаёт meta.cursor,
reader ждал next_cursor и видел1000из2001obs. Минимальное решение поддерживает
оба поля сguard repeatedcursor. Альтернатива переэкспортироватьdata отклонена:
существующийDense trace дочитан,успешныеexports не повторяются.3targeted tests
cover обаcursor schema/2001items/repeatedcursor; realnativefulltext/usage proof
подтвердил3views. Дляofflinefreeze введён AST guard: разрешено менять толькоbody
get_all_langfuse_observations, остальныеexport/inference AST nodes неизменны.
Blanket exception дляtracking отвергнуто. Executioncodea0 зафиксировандоfix;
postprocessor имеетотдельныйHEAD/sha,старыеplans/runtimeSHA не переписываются.
Пересмотрнужен приновом API schema илиизменениидругихexport/generationfunctions;
это не разрешение повторять inference. Source/audit/receipt links вsafeJSON.


## Исторические checksum fingerprints итогового отчёта

CI061b306 нашёл2generic-api-key совпадения вpublic e2-musique-s500.json:
обаcase_key — один и тотжеSHA256([musique,raptor,3hop1__90327_83076_319330]),
не credential. Значения проверены вimmutableGitblob ивычислением existingdigest.
В.gitleaksignore только2точныхcommit/path/rule/linefingerprints(2162,2205),
историяне переписывается, blanketrule/path исключений нет. Public keyname теперь
case_id_sha256, значениеидентичноprivatecase_key. Sourceplans/raw/journals не
меняются. Полный historyscan219commits дал0findings; syntheticstdin canary обнаружен;
новыеvalues/commits продолжаютсканироваться. Это не опубликованное одобрениебота.


## Воспроизводимость опубликованных дополнительных свидетельств

Ранее write_report строил базовые метрики и затирал posthoc audit/tracking/cost
разделы. Выбрано одно reviewed приложение с run/plan/manifest и локальными SHA,
а не слепое сохранение старого JSON и не повторный tracking-export. Основные
метрики/physical accounting строятся прежним runner; appendix не может подменять
core fields. Audit сверяется с исходным snapshot, views с сохранённым receipt,
cumulative known/POST вычисляются из исходных subtotal один раз. Неизменные raw
и execution plans не переписываются, существующий evaluation требует равенства.
Повторная сборка в независимые outputs и негативные tamper-тесты проверяют путь.
Это postprocessor change, не изменение reader/retrieval/evaluator/эксперимента.
При изменении lineage необходимы новые проверяемые свидетельства; старое
приложение для иного run/manifest отклоняется.


## Текущее бюджетное решение issue15

Прямое согласие пользователя от2026-10-29: «Я согласен с этими лимитами»
в ответ на предложение4 982 220новых combined tokens/2100POST только HotpotQA.
Это согласование операционного бюджета как протокольного решения в PR37,
**не команда запуска**. Научные O/N/R/H уже согласованы по сообщению пользователя;
публикация bot/GitHub review не утверждается.

| Scope | Утверждённые новые tokens | POST caps | Статус |
|---|---:|---|---|
| MuSiQue | 5990220 | reader900/filter300/localBGE900 =2100 | Ранее разрешён и выполнен в PR38; отдельный continuation199 не расширял caps |
| HotpotQA | 4982220 | reader900/filter300/localBGE900 =2100 | Бюджет согласован; execution не запущен/не разрешён этим решением |

Hot allocation4913100 = сумма300missing calls × maximum fully measured pilot
operation для каждого метода/стадии; плюс69120 для допуска очередного запроса.
Источник — неизменный `budget_proposal.operational_budget_proposal.allocations`
в frozen `results/summary/full-experiment.json`, строки HotpotQA. Scope — только
900ранее не запущенных method/question cases,600исходов пилота переиспользуются,
включая один sealed transport failure. Это не600успешных ответов.

Исходный общий proposal10903320 и static worst-case114669441 остаются историческими
расчётами, не переписываются и не называются actual usage. Сумма отдельно принятых
allocation caps10972440 выше старого proposal на69120: admission headroom теперь
отдельный у двух последовательных этапов. Это не перенос неиспользованного Mu
остатка; исходный Mu cap не расширяется. Исторические costs и unknown reserves
(Hot22545/Mu15732/E1отдельно) сохраняются, не считаются новыми расходами или нулём.

Перед любым будущим Hot POST необходимы отдельный проверенный missing-only
execution-plan, актуальная сверка ID/data/index/model/reader/evaluator/source/
claims/остатков caps и отдельная команда запуска. Один serial worker, retry0.
До запроса: known+unknown reservations+in-flight+exact candidate reservation
не выше4982220, totalPOST не выше2100 и отдельные operation caps не превышены.
При нехватке — stop без POST. Новые partial/unknown/transport/infra/pin/budget
ошибки останавливают очередь без retry/автопродолжения; sealed unknown не повторять.
Прежняя политика известных reader case failures сохраняется. Reader cap512,
prompt/model/top5/index/split/SDK и строгий Hippo filter не меняются.
Завершение900cases не гарантируется; новый расход/отступление потребует нового
решения. Никаких моделей/embeddings/индексации/tracking-export этим согласованием
не запускать. Анализ signal-check для выбора сигнала issue21 не разрешён.

Все четыре критерия issue15 выполнены: шесть configurations/ID закреплены;
каждый reused result проверен/исключён; missing-set, оценки, scoped caps и stop
условия зафиксированы;300/100/100 и development-ограничения сохранены.
PR37: Closes #15, Draft. Исходный frozen manifest/runtime SHA/raw неизменны.
Записи Mu-согласий остаются в существующем PR38:
[budget](https://github.com/SPStan/rag-graphrag-research/blob/codex/musique-s500-comparison/results/summary/e2-musique-s500-authorization.json),
[continuation](https://github.com/SPStan/rag-graphrag-research/blob/codex/musique-s500-comparison/results/summary/e2-musique-s500-unattempted-authorization.json).


## Full-history secrets CI: разрешённые точные checksum fingerprints

CI сканирует fetched refs, включая исторический PR38 commit061b306.
Обе находки в его public JSON (строки2162/2205) независимо сверены с existing
case digest([musique,raptor,публичный tuning question ID]) и immutable Git blob.
Пользователь явно разрешил перенести две уже существующие в PR38 точечные
записи в PR37 после отдельного уведомления об отказе automatic approval.
В .gitleaksignore только commit/path/rule/line; blanket rule/path исключений нет.
История и raw не меняются; новые значения продолжают сканироваться.

## Hot: продолжение только незапущенных после known filter failure,30октября

Исходный Hot run `91f59cf6-e61c-499d-9d29-d55bff1824c2` terminal failed
на `E2_filter_shape_invalid`, без нового unknown. Его usage/response/checkpoint,
claims, failed manifest и plan `ce5a2b70…` неизменны. Из1500ожидаемых
учтено1071:1068completed,3failed,429not_attempted. Новая fatal ошибка имеет
известный usage: это не transport unknown и не неверный ответ reader.

После уведомления о конкретной причине/429missing/запрете automatic retry
пользователь ответил «Делай то что нужно». Решение: выполнить только ранее
незапущенные429cases (Hippo129,RAPTOR300), не повторять failed/paid/unknown.
Оригинальная filter-fatal политика сохраняется: исходный run остаётся failed;
её не переносим в продолжение очереди внутри этого failed run. Новый child
допускается только существующим missing-only механизмом с проверенным immutable
parent lineage и отдельной hash-bound записью решения. Научные модели, prompt,
reader cap512, top5, индексы, split, evaluator не меняются; O/N/R/H pending
перед merge. Новый filter failure снова fatal, второго такого child не будет.

Из прежнего Hot cap4982220/2100POST потрачено1203911known/1112POST,
новыхunknown0. Childcap3778309tokens/987POST =429reader+129filter+429BGE;
один оставшийся reader slot исходного failed-case не используется.
Расширения бюджета нет. Исторические unknown/reserves/E1 остаются отдельно.
Общий durablecounter становится2/2; дальнейшие auto restarts запрещены.

Неудачные outcomes учитываются pipelineEM/F1=0 с исходными error markers,
не называются неправильными reader answers; not_attempted не получает0.
До полноты1500outcomes E3 не публикуется. Terminal audit и cumulative expense
суммируют parent+child один раз, сохраняя logical reuse отдельно.

Альтернативы: повторить filter или ослабить schema — отклонены; остановиться
навсегда — безопасно, но не завершает429явно разрешённых missing cases.
Проверка: actual shared CLI с synthetic HTTP, immutable parent/pins/claims,
remainingcaps, known-failure reuse, запрет secondchild/unknown и0повторной оплаты;
затем реальный offline source/index/artifact gate безHTTP и mandatory hook.
