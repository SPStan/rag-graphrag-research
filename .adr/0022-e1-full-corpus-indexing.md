# ADR-0022: измеренная индексация E1 на шести полных корпусах

## 21 октября: подготовка RAPTOR continuation после batch-пробы

Один свежий MuSiQue run использует старые physical responses и удачную batch-пробу
в качестве двух immutable sources. Проверка cache разделяет Dense leaves и
физические summary/embedding ответы. Для leaves проверяются producer journal,
SHA vectors, ordered passage IDs и точный text digest; произвольный producer ID
не заменяет эти проверки. Общая проверка Dense вынесена из существующего
RAPTOR builder и используется также при подготовке/replay.

Failed embedding payload восстанавливается из saved summary до совпадения SHA;
успешная probe должна соответствовать этому же тексту с options4096/4096.
Она не оплачивается второй раз. Существующие успешные embeddings replay по старому
payload SHA, uncached получают новые options. Ветка/модели/корпус/seed/две layers
не меняются; roundtrip tree обязателен. Никакого truncate или повторного Dense.

Оба исходных run входят в history: known1016942+probe2104, unknown reserve10422.
MuSiQue остаток10970532; untouched HotpotQA12M. Диагностика, уже включённая в
history, не добавляется вторично экспортом. Сумма длительностей — attribution,
не новое cold-run измерение. Unknown остаётся unknown после успешного индекса.

Plan создаётся в единственном `<data-root>/indexes/e1/issue13-raptor-batch-plan.json`,
claim рядом с failed manifest исключает второе продолжение между output folders.
Планы/manifest источников закреплены SHA/lineage, новые run ID/output и clean code.
Любая новая ошибка останавливает очередь без retry. До отдельных согласованных
расходов команда только готовит plan; полный rebuild не разрешается успехом probe.
Hippo/QA/E2 не запускаются. Альтернатива повторить501 summaries/500 embeddings
отклонена: сохранённые physical responses пригодны к проверяемому replay.

## Итог ограниченной schema-пробы21октября

После явного разрешения на external dataset transfer первый POST вернул HTTP400:
Grammar error, Unimplemented keys: uniqueItems. Backend не выполняет предложенный
контракт. Второго POST нет, retry нет; usage unknown/reserve8679. Не заменяем
этот результат успешным "JSON Schema supported" и не удаляем uniqueItems скрыто.
Следующий schema-вариант требует отдельного плана/проверки/согласования; локальная
уникальность готового JSON не гарантирует устранение генеративного цикла.
Полный HippoRAG и QA не разрешены результатом этой пробы.

## 21 октября: установлен physical-batch отказ BGE-M3

Точный failed input восстановлен из summary response
`1fdcb7aedc1d9b54d60f2ef99024f8e941664de6ffaf53e3d461d101a9823803`;
его embedding payload SHA совпал с failed journal object_id
`f6deb464ae50c4fb94690686d8e7b734ff8713d65e7dfa96690535ad7b395f1f`.
Это законченный Qwen ответ (stop,2179 input/2135 output), не length.

Родной tokenizer точного GGUF BGE-M3 посчитал2102 без special tokens/2104 с ними.
Три контрольных saved embedding usage совпали с родным подсчётом:524/693/548.
Для подсчёта использован установленный llama-server CPU-only, embedding-only,
no-warmup и только /tokenize; embedding/generation не вызывались. Временный
tokenizer остановлен. GGUF SHA проверен: daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c.

Модель metadata: context8192. Исторический runner: n_ctx_slot4096; точная ошибка:
input2104 exceeds physical batch2048. Значит исходная HTTP413 неверно сводилась
к превышению контекста. Установленный Ollama0.40.4 по умолчанию выделяет embedding
batch2048; num_batch задаёт physical и logical batch в [коде закреплённой версии](https://github.com/ollama/ollama/blob/v0.40.4/llm/llama_server.go).

Минимальная предлагаемая политика: только RAPTOR новые embeddings получают явные
num_ctx=4096/num_batch=4096, truncate=false; сохраняется полный summary и прежняя
модель. Успешный старый payload/cache проверяется первым и переиспользуется с
исходным SHA; новые options не заставляют повторять старые embeddings. Не меняем
Qwen summary cap, не делим и не обрезаем тексты. Отказ/unknown/реальный input сверх
этого окна останавливает обработку; повышение до8192 требует отдельного решения
и проверки памяти. Этот параметр не объявляется проверенным полным E1.

Сначала synthetic tests payload/cache/запрета изменения Dense/Hippo. Затем
отдельно согласованная проба: один localhost embedding POST на сохранённом
summary2104, никакого полного RAPTOR rebuild. Исторический failed usage остаётся
unknown, даже если новая попытка успешна. При продолжении вычитать все known и
unknown reservations из прежних12M, включая диагностику; физический и standalone
расход не смешивать.

Проверка21октября на clean eb6b271: один отдельно разрешённый localhost POST,
num_ctx4096/num_batch4096/truncate=false. Тот же2104-token input обработан,
вектор1024 сохранён и загружен без новых calls; usage2104,100% известен.
В runner подтверждены n_batch4096/n_ubatch4096/n_ctx_slot4096.
Probe manifest SHA:1997f8e6ddb5c044d64882b2fb8c9ea1a1fda097f2c8110b36e795b8bfac0385.
Статус: исправление подтверждено на конкретном failed input, не на полном индексе.
Предыдущий unknown10422 не снят. Для будущего RAPTOR MuSiQue остаётся10970532
из12M после known1016942, reserve10422 и diagnostic2104. Probe не разрешает
новый полный run автоматически; сначала подготовка continuation с immutable
lineage, verified old payload reuse и canonical claim. Старые500 successful
embedding payload не должны повторяться из-за добавления новых options.

## Уточнение21октября: повторный цикл, независимые индексы

Коррекция инструкции не устранила цикл на втором passage: исходный и revised
ответы length3072, соответственно163/191 tuples при4 уникальных. Usage известен,
обе попытки сохранены. Это отказ генерации, а не доказанный дефект графового алгоритма.
Повтор той же инструкции либо повышение cap отвергнуты: оба уже наблюдавшихся
варианта расходуют токены на повторы. Для HippoRAG нужен отдельный проверяемый
протокол устранения цикла; третьей попытки на этом passage сейчас нет.

Вместо удержания независимых RAPTOR строк до завершения HippoRAG выбран отдельный
канонический plan. Меняются только code_commit двух не начатых RAPTOR строк;
предыдущие планы и все run immutable, budgets/данные/модели прежние. Claim при prior,
проверка terminal journals/artifacts и запрет иных методов до HTTP предотвращают
параллельный запуск и неявный повтор failed run. E1 сохраняет всю историю расходов.
Альтернатива — остановить все независимые работы — не добавляет проверки HippoRAG.
Условие пересмотра: failed RAPTOR либо новый offline-проверенный протокол HippoRAG.
Offline-регрессии: lock, изменённый artifact, начатый output, failed Dense,
повторный claim, запрет Hippo до HTTP, сохранение unknown и физических сумм.

## Уточнение20октября: цикл при известном usage

Network child повторил3 tuples56раз и достиг3072 output на93словном passage.
Cap не увеличиваем: частичный результат непригоден, больший cap не лечит цикл.
Выбрана одна проба с явной инструкцией уникальности и закрытия JSON; source NER
берётся из verified cache, triple SHA проверяется до HTTP. При успехе тот же
ограниченный fallback доступен обоим Hippo датасетам: один на request,≤20/dataset,
только length с явным циклом. Transport retry0. Полный JSON без дубликатов обязателен,
иначе остановка. Обе попытки/все предки входят в стоимость и время E1; кэш не
дублирует физический расход. Unknown сохраняется. Политика/команды — E1_INDEXING.

Статус: протокол принят к реализации20октября2026; фактические статусы запуска
публикуются в E1. Успешный smoke не объявляется готовым полным индексом.

## Контекст

#10/#11/#12 слиты. Issue#13 требует три метода × два корпуса5500, стоимость,
покрытие и загрузку. Исторический Dense кэш имеет неизвестную стоимость;
перенос smoke результатов в E1 её не восстанавливает. Административный предел90M
снят ADR-0016, но каждый эксперимент должен иметь заданные пределы.

## Решение и альтернативы

Строим новые Dense индексы с полным учётом; их точные leaf vectors переиспользуем
в RAPTOR этого же пакета. Альтернатива — исторический Dense с явной неполнотой;
новое построение недорого и даёт измеренный producer для совместимых leaves.
HippoRAG сохраняет свою обработку newline→space в embedding callback, поэтому
совместимость его векторов с Dense не предполагается и стоимость измеряется отдельно.

Общая связка в run_e1, только index-only вызовы библиотек в e1_indexers;
алгоритмы графа/кластеризации не переписываются. Сохраняем проверенные pinned SDK,
NER1024/triples3072/summary4096, последовательные запросы и strict JSON parser.
Не включаем reader: это E1, оценка качества относится к следующей задаче.
Disjoint бюджеты2M/20M/12M на метод/датасет, всего68M новых комбинированных
токенов. Смета, ограничения прогноза и команды — [E1_INDEXING](../docs/E1_INDEXING.md).

Один канонический plan привязан к checkout/commit. Все outputs новые, lock до
запросов, started до HTTP, ответ до validation, неизвестный usage останавливает.
Кэш требует SHA и подтверждённую физическую попытку; failed не повторяется
автоматически. Данные/ответы/индексы приватны, публикуются метаданные/суммы/SHA.

## Проверка и последствия

Offline-тесты запрещают HTTP при бюджете/неполноте, проверяют неизменность
checkpoint и отсутствие повторной оплаты. В изолированных реальных SDK
synthetic документы проходят index/save/reload без HTTP. Они проверяют связку,
но не заменяют реальных шести индексов. Фактические E1 результаты проверяются
по каждому manifest и хэшам; failed/pending явно блокируют E2.

Пересмотр требуется при length/parse/unknown, превышении бюджета, несовместимости
SDK/модели или неприемлемом машинном времени. Не уменьшаем корпус и не удаляем
неудачные попытки ради формального завершения. Полнота новой стоимости E1 не
означает полноту всех исторических затрат исследования.

## Продолжение20октября после сетевого отказа

HippoRAG MuSiQue остановлен на triple запроса1561; usage неизвестен, успешные
3293 ответа и весь журнал сохранены. Вместо полного нового построения выбран
проверяемый replay отдельных физических success/complete ответов в новом run.
Альтернатива повторить все запросы дала бы повторную оплату без новой информации.
Полнота producer run остаётся false, несмотря на проверенные usage отдельных
ответов. Unknown reservation7922 вычитается вместе с known2841297 из20M;
остаток17150781, общий потолок68M не меняется.

Одна canonical claim рядом с failed prior; старые manifest/response/journal/plan
неизменны. Immutable lineage связывает модели и старые Dense producer. Новое
соединение на каждый remote POST, без transport retry; причина RemoteDisconnected
не установлена. Следующий отказ останавливает пакет. Offline-регрессии проверяют
нулевой HTTP на replay/изменённом кэше/повторном claim и сохранение unknown в E1.


## Аудит 21 октября: стоимость, reload и следующий диагностический шаг

Физический расход пакета не включает повторно Dense embeddings, переиспользованные
RAPTOR. Для самостоятельной стоимости RAPTOR атрибутируем всю измеренную историю
производителя, включая failed attempts; unknown остаётся unknown. Это стоимость
фактической подготовки, а не оценка идеального запуска без ошибок. Разделяем
physical_usage_complete и standalone_cost_complete. Сумма длительностей историй
обозначается attributed_construction_seconds, не измерением нового запуска с нуля.

Restore уже валидирует структуру/векторы. Дополнительно проверяется точное равенство
serialize(restore(payload)) и исходного payload, включая тексты и embeddings.

Следующая гипотеза для HippoRAG — structured output со схемой triples вместо
одного json_object. Статус: предложение, вызовов нет. Проверяем поддерживаемый
контракт целевого сервера: массив троек из трёх непустых строк; uniqueItems только
если backend действительно поддерживает это ограничение. Поддержка JSON Schema
на уровне API не доказывает поддержку каждого keyword и не гарантирует качество.
Схема без подтверждённого enforcement уникальности не объявляется исправлением цикла.

Подготовка21октября: исходные SHA обоих payload совпали; NER только из verified
cache. Схема и строгий локальный валидатор подготовлены, HTTP запрещён при проверке.
Предложение включает uniqueItems=true; неизвестная поддержка означает возможный
отказ API, после которого диагностика останавливается. Резерв8679+8990=17669
из остатка16065954, cap3072 прежний. Ни один новый POST не выполнен;
отдельное согласие на2 POST получено21октября, полный rebuild запрещён.
Сначала завершение очереди и интеграция. Исполнитель требует live checkout,
clean commit, отсутствие running index workers и точный SHA private plan;
повторно восстанавливает payload перед claim. Claim рядом с каноническим prior,
максимум2 POST,0 NER/retry; первый отказ останавливает цикл. Все попытки входят
в E1 cost history, unknown reserve не выдаётся за измеренный расход.
Безопасные SHA и команда — docs/E1_INDEXING.md, private payload не публикуются.

До вызова: восстановить два сохранённых проблемных payload из pinned prompts,
passage и проверенного NER; сверить их исходные SHA. Offline проверить схему,
валидатор, бюджет, отсутствие повторной оплаты NER и число физических запросов.
Предлагаемый диагностический предел: по одной новой попытке на каждый из двух
случаев, максимум два POST, cap 3072 прежний, точный input reserve вычислить по
восстановленным payload до согласования. Это не разрешение запуска.

Успех пробы: stop, строгий полный JSON, валидные уникальные triples, известный usage;
семантическая поддержанность проверяется отдельно по исходному passage без QA gold.
Новый отказ останавливает диагностику. Даже 2/2 не разрешают автоматически полный
rebuild. Для принятия политики нужны версия конфигурации, одинаковое правило обоим
датасетам и явная маркировка смешанного base/fallback extraction при reuse.
Сохранённые частичные ответы не очищать дедупликацией для помещения в индекс.
Альтернативы повышения cap и третьего идентичного prompt отклонены из-за повторов.


## RAPTOR: малые рекурсивные группы,21октября

После исправления physical batch продолжение68b112fc прошло1540 физических
POST (770summary/770embedding), все с известным usage1477962. При Layer1
pinned cluster_utils.py рекурсивно получает группу2–4nodes; формула
floor(sqrt(n-1)) задаёт n_neighbors=1, UMAP требует>1. Дерево отсутствует.
Сетевая причина и неизвестный usage этого нового запуска не установлены:
новых сетевых ошибок нет, старый unknown10422 сохранён отдельно.

Выбрана локальная политика `pinned_gmm_umap_singletons_n_le_4_v1`:
для<=4узлов возвращать singleton clusters без UMAP/GMM. Все node/text/vector
сохраняются, нет обрезки, дедупликации и добавления gold. Обычный путь группировки,
перекрывающиеся memberships и recursive defaults10/0.1 повторяют pinned код;
SDK blobs остаются неизменны. Правило применяется обоим датасетам. Единственный
узел, превышающий3000cl100k, остаётся целиком, как в upstream singleton base case;
общий context/budget guard остаётся обязательным передHTTP.

Альтернатива clamp n_neighbors>=2 не решает остальные ограничения UMAP для
n=2..4 (размерность/спектральная инициализация). Уменьшение корпуса, смена
модели и повтор всей индексации отклонены. Сведение маленькой группы в один
кластер может снова превысить max_length_in_cluster и вернуть рекурсию.
Singleton terminals гарантируют завершение именно этого малого случая,
но не доказывают завершение любого следующего слоя и не оценивают качество.

Это явно отмеченная версия адаптера, отклонение от исходной реализации,
подтверждённое пока offline. Тесты воспроизводят исходную ошибку на pinned SDK,
проверяют отсутствие reduction/HTTP для2–4nodes, сохранение всех узлов,
перекрывающиеся группы и index/save/reload с fake models. Полный corpus cache
проверяется безHTTP до первого нового запроса; реальный индекс ещё не готов.

Продолжение: один canonical child в musique-cluster1 с immutable lineage/SHA,
claim рядом с failed musique-batch1. Все три истории включаются единожды;
новый known1477962 вычитается из остатка10970532:9492570 для MuSiQue,
HotpotQA12000000 без изменений. Старые unknown/reserves не сбрасываются.
До новых вызовов — offline-проверки и конкретное решение о продолжении;
stop first error/retry0, без Hippo/E2/QA/merge. Пересмотр при следующем
непрогрессе рекурсии или ошибке, без бесконечных одинаковых попыток.


## RAPTOR HotpotQA: ограниченная summary-проба (предложение,21октября)

Новая остановка не связана с n_neighbors: Layer1 дошёл до генерации summary,
ответ3011in/4096out исчерпал cap. Содержимое — чрезмерно подробный каталог;
оснований объявлять его тем же циклом HippoRAG нет. Не повышаем cap4096:
это может увеличить расход и несовместимость с embedding, не исправив сжатие.
Не принимаем partial/deduplicated/truncated текст как завершённый узел.

Предлагается1диагностический POST с исходным context без изменения и отдельным
system требованием≤300слов, compact prose, без каталогов/повторов/новых фактов.
Cap снижен до1536, жёсткие проверки stop/word count/4000UTF8bytes/known usage.
Byte guard не выдаётся за native token count; embeddings в этой пробе нет.
Альтернатива смены модели/корпуса отклонена; повтор идентичного prompt не
проверяет конкретное исправление. Сжатие до300слов может потерять важные детали:
семантическая поддержанность и пригодность к индексу остаются отдельной проверкой.
Это предложение версии prompt, а не подтверждённый выбор benchmark.

Точный original SHA восстанавливается из verified cache; old response и known7107
не меняются. Claim доHTTP,1POST/0retry/0embedding/0NER. Расход и unknown входят
в агрегат E1; вычитаются из остатка9306190 HotpotQA. Даже успех не разрешает
автоматически full continuation. Дальнейшее применение правила должно быть
одинаково определено для обоих датасетов и явно версионировано; готовый MuSiQue
не повторяется без отдельного основания. После второго отказа не запускать
цепочку однотипных проб, а описать воспроизведение/варианты для решения.


### Результат summary-пробы и граница следующего решения

Единственный согласованный POST дал stop/535output tokens/1979bytes,
но315whitespace words>300. Это улучшение завершённости относительно length,
но не успех по заранее заданному диагностическому критерию. Manifest failed
сохранён, расход3593known добавлен в E1, индекс не продолжен. Нового unknown нет.
Не расширять критерий задним числом и не обрезать сохранённый ответ.

Следующий выбор вынесен на решение: отдельная проба с запасом в целевом числе
слов (250при hard≤300) либо явно согласованный куратором новый допуск и принятие
уже полного315-word response по SHA с отдельной записью принятого отклонения.
При втором варианте исходный failed остаётся failed; меняется будущий критерий,
а не прошлый результат. Semantic support и native BGE count ещё не подтверждены.
Ни один вариант, второйPOST и full continuation этим результатом не разрешены.

### 22 октября: native-capacity fallback и offline-принятие

Техническое решение: желаемые300слов в corrective prompt отделены от
обязательных stop/nonempty/known usage/native embedding fit. Произвольный
порог350и новый POST ради круглого числа отклонены. Native BGE count550
(контроль2104) помещается4096/4096; 16групп утверждений проверены по context.
Полный сохранённый ответ принят отдельной записью с SHA/происхождением;
старый failed manifest по300словам не меняется. Это выбор пригодности для
продолжения, не подтверждение качества метода или внешней истинности context.

Единое правило обоих датасетов: fallback только после baseline length,
cap1536, максимум1corrective-попытка/датасет, retry0. Hotpot её уже потратил:
новый continuation только replay принятого ответа и оставшиеся baseline
requests; любой новый length окончательно останавливает этот план. Успешные
summaries не перегенерировать, отличие prompts раскрыть в provenance.
Бюджет9302597combined tokens,≤4000physical POST; все failed/probe/unknown
сохраняются. Новый run и canonical claim, original→fallback association,
nativeпроверка новых embedding inputs доHTTP; no truncation.

Прежнее предложение о новом допуске только через куратора заменено текущей
offline-политикой в рамках явного поручения. Действующий протокол требует
раздельно: пользовательское разрешение реальных расходов, научное согласование
O/N/R/H и техническую готовность PR. Ни один новый HTTP сейчас не разрешён.
Пересмотр: неподдержанная claim, native overflow, новый length/unknown,
нарушение replay/бюджета или установленный эффект разных prompts на сравнение.

Hippo: удаление uniqueItems — кандидат совместимости schema, не подтверждённое
исправление цикла. Полный JSON/форма/уникальность проверяются локально;
предлагается≤2POST на прежних двух случаях, не full корпус. ИсторическийHTTP400
unknown reserve8679сохраняется, cap3072не повышен. Реальной проверки пока нет.
Подробности и воспроизведение: docs/E1_INDEXING.md, безопасное принятие —
results/summary/e1-raptor-summary-adoption.json.

### 22 октября: отдельное TLS-восстановление HotpotQA

Новый отказ — TLS handshake timeout5секунд, не отсутствие model response после300.
В run17fdc09a1005новых POST,1935267known и8432unknown reserve; старые записи
не меняются. Альтернатива слепого повторения или повышения generation cap отклонена.
Один ограниченный fresh run меняет connect timeout5→30, read300/retry0/prompt/cap
прежние. После1005POST остаётся2995; после known+reserve7358898combined tokens
в прежнем12M. Новый claim/output/run; все успешные responses replay поSHA.
Первый uncached key обязан быть исходным failed summary key. Любая новая ошибка
останавливает этот план, третья continuation автоматически не разрешена.
Причина timeout на стороне сети/сервера дальше handshake не установлена;
новый параметр — защитная политика, не экспериментально доказанное исправление.
Успешный TLS-only preflight0HTTP не доказывает исправность generation.
Проверка: offline регрессии claim, ограничения, provenance, cache, второго timeout,
zeroHTTP при подмене audit/key/attempts. Условия пересмотра: новый отказ или
невоспроизводимый payload, расход выше reserve либо несовпадение источников.
Научное O/N/R/H и merge отдельно; Hippo и E2 этим решением не разрешены.

### 22 октября: оба RAPTOR завершены; ограниченный compatible-schema executor

Hotpotbb177a66 completed:5500leaves/7595nodes,слои5500/1411/684,
347новыхPOST/697411known,0ошибок; отдельный fresh-process exactreload/0HTTP.
Готово4/6. TLS continuation в данном запуске позволила закончить этап;
это не доказывает устранение всех сетевых причин. Старый unknown8432сохранён.

Совместимый schema-вариант встроен в существующий execute_schema_probe, а не
одноразовый скрипт. Своя claim/output, exact approved SHA и code pin, max2POST,
cap3072,connect30/read300/retry0/stopfirst. Одно правило полного JSON/формы/
локальных дубликатов. Old uniqueItems manifest/unknown8679сохраняется; exporter
суммирует обе диагностики без двойного учёта. Предложенный резерв17625из16057275,
passage и cached NER прежние, NER/embedding/full rebuild не разрешаются.
После старогоHTTP400 требуется отдельное согласие на новый schema-вариант;
согласие на RAPTOR TLS этот scope не покрывает. Успех2случаев не является
доказательством исправления цикла или достаточности full indexing.
Проверка: offline HTTP callback показывает claim доPOST и≤2попытки, unknown
второго ответа сохраняет первый usage, invalid JSON/дубликаты/length отвергаются,
E1 known/reserves агрегируются ровно один раз. Условие пересмотра: server400,
неполный output, дубликаты, unknown или неподдержанные facts при semantic audit.

### 22 октября: два schema-ответа и граница применения штатного parser

Согласованная проба09ec0b4/6d0d0dc3 выполнила2POST. Valencia stop16/16unique,
Kobe stop62/14unique,48повторных вхождений; общий1774in/1460out=3234known,
новогоunknown0. Строгая проба failed по duplicate triples во втором ответе;
остановка соблюдена, full indexing не запущен. Failed/raw/history неизменны.

Оба JSON полные, schema принята API на этих случаях. Kobe повторяет факты по
кратности наград источника; это конечный output, не доказательство исправления
любых прежних генеративных циклов. Cap/модель/prompt повторно не менялись.
Pinned SDK filter_invalid_triples/flatten_facts уже сворачивают буквальные
дубликаты; наш обычный parser использует этот код. Offline:16→16,62→14,
recover_partial=False,HTTP0,61файл установки проверен. Partial не принят.

Следующее предложение — отдельное принятие полных сохранённых responses для
штатной graph-set семантики с раскрытием raw/unique/provenance, без новогоPOST.
Это не пересмотр результата строгой пробы и не автоматическое разрешение
full индекса. Принятие ещё не активировано, replay/новый bounded plan потребуют
проверки. Единая политика обоих датасетов, неизменные raw, unknown и stopping
условия обязательны. Литературная или фактическая истинность всех triples этим
не доказана; output теряет временные/количественные qualifiers и часть modality.
Новый запрос ради удаления дубликатов сейчас не требуется. При отказе от этой
семантики нужен другой заранее заданный протокол извлечения counts/years.


### 22 октября: native graph-set adoption и offline-интеграция continuation

Принято техническое решение `native_graph_set_schema_v1`: использовать полные
сохранённые responses штатным parser SDK1438aba3 (exact literal dedup), сохраняя
raw и failed строгой пробы. Отдельный публичный adoption содержит исходный/schema
request, response/manifest SHA, producer и raw/unique counts16/16и62/14. Прямой
вызов закреплённого SDK воспроизвёл counts offline, requests запрещены.
Альтернативы: ещё одна генерация ради уникальности — лишняя оплата без необходимости;
частичный JSON — отвергнут; извлечение count/year qualifiers — другой протокол,
не реализуется молча в этом блоке. Семантическая истинность не доказана.

Для обоих datasets новые triples используют ту же совместимую shape schema;
старые успешные json_object кэшируются с прежним ключом. Adoption replay в runner
записывает фактический schema key/producer; проверяет полный JSON, usage и SHA до
использования. Никакого возобновления старых manifests. Общий canonical claim,
новые outputs/run IDs, history обоих probes включена один раз. Пределы исходных
20M/dataset не расширены: Mu16054041, Hotpot20M, вместе36054041 новых combined
токенов. POST≤40000/dataset включая embeddings, LLM≤11000 до вычета кэша,
corrective0/retry0/redirect0, connect30/read300. На первой ошибке остановка,
known/unknown сохраняются. Политика не обещает, что length больше не возникнет.

Проверка: целевые offline-тесты corruption/length/partial/unknown/duplicate fields,
parser mismatch, provenance replay без двойной стоимости, общий повторный claim,
запрет следующего POST после ошибки. Команды и остановки в E1_INDEXING.
Это offline-разрешение принятия и подготовка плана, не разрешение новых HTTP;
новый full-corpus этап требует отдельного scoped согласия пользователя. Научные
O/N/R/H и готовность6/6 остаются отдельными проверками; куратор автоматически
не назначается согласующим техническую нормализацию. Условия пересмотра: смена
SDK/schema/модели, необходимость новых corrective attempts, потеря provenance или
изменение исследовательской семантики facts. Старые failed и unknown не меняются.


### 22 октября: локальный preflight failed с нулём физических попыток

Согласие на оба Hippo datasets получено дляcaf265ad/7f0c6ed. Runner остановился
на первом старом triples cache hit: strict schema-проверка ошибочно применялась
к прежнему json_object с extra fields. HTTP0, новые tokens0, Hotpot не запускался.
Контракты разделены: verified старые ответы используют прежний pinned parser,
actual schema payload — строгую проверку. Полный offline-аудит4836cache entries:
2332NER/2332triples,1919legacy extra-fields, recover_partial=False, без запросов.

Решение: один preflight child в существующей подготовке плана, только при
failed journal с attempts0/known0/unknown0 и проверенных SHA. Failed и исходный
approved plan не меняются. Новый claim рядом с нулевым failed, новые run IDs/outputs,
эта история включена с расходом0; бюджет, model/data/caps/stop/retry0 прежние.
Применимое согласие на оба прогона сохраняется: ни одной оплаченной попытки ещё
не использовано, исправляется локальный replay. Происхождение согласия содержит
исходный approved SHA и отдельный execution revision, не подменяет слова пользователя.
Альтернатива reset failed/claim отвергнута; бесконечные revisions запрещены.
Путь не применим после любого physical request, в том числе успешного с известным
usage; новой генеративной политики/повтора после model failure он не разрешает.
Проверки: regression legacy extra fields, positive/negative zero-attempt guard,
immutable ancestors/unchanged budget/new outputs/once-only claim;60targeted passed.


### 22 октября: shape schema не остановила генеративный цикл

Run3eab6c1d остановился после1357passages/1544POST/1015121known. Последний
response length3072 при input891:168complete tuple fragments/26unique,
142одинаковых подряд; источник не содержит такого числа событий, поздние
сведения passage отсутствуют. Полный JSON отсутствует; partial не принимается.
Known3963 этой попытки уже включён, transport errors0 не равны extraction success.
Manifest/raw SHA и точный payload из source+cachedNER восстановлены offline.

Решение: не повторять POST с теми же условиями, не повышать cap, не дописывать
JSON и не выбирать число facts по наблюдаемым26unique. Форма schema не является
устранением цикла, SDK dedup применим только к полным accepted responses.
После двух безрезультатных мер (prompt uniqueness/shape schema) нужен короткий
разбор и внешний ответ о Qwen/backend перед следующим расходом, а не ещё одна
цепочка одноразовых проб. Причина на уровне модели/decoder не установлена.

Совместимый reuse проверен для всех5500source requests:3102полныхNER+triples,
2NER-only/2396безNER;6379response entries. Никакого готового Hippo графа это
не доказывает. Старый failed/unknown не сбрасывается. E1known16707393,
upper16762447,cost_complete=false; Mu остаток15038920/Hotpot20M.
В этом разборе generation/embedding0; один GET /models без данных корпуса
подтвердил наличие gpt-oss-120b, но не deployment limits. Альтернативная модель
не принята: SPEC фиксирует общую Qwen, изменение требует явного пересмотра
условий и актуальных научных формулировок. До контрактов/payload/ограниченной
проверки новый полный запуск не готов. Параметры следующей пробы не выдумываются.
Следующий возможный gate после подтверждённого исправления Qwen — один тот же
full passage+cachedNER, cap3072, без retry/NER/embedding; exact reserve/plan до
разрешения, stop на ошибке. Raw/coverage/SHA и ограничения в E1_INDEXING.


### 22 октября: отдельный child после ошибки physical POST counter

Разрешённый mixed runb2dc4e51 остановлен локальным guard на2410/5500:
2752LLM cache events ошибочно вошли в cap4814 вместе с2069physicalPOST.
Исправлениеb5ab964 исключает replay. Known1375138/current unknown0 сохранены;
это не новый generative failure. Старый zero-attempt preflight exception не
применяется: расходы уже были. Failed/план/response SHA не переопределяются.

Один согласуемый child в existing runner: canonical plan/once claim, новый output,
прежний общий fallback claim root,10history Mu. Строгая проверка local-counter
причины, terminal known journal, всех artifacts и завершённых fallback claims.
Любой unknown/unresolved model failure/активный worker запрещает подготовку.
Пределы уменьшаются на все использованные physical POST/tokens: Mu13650487tokens,
2745внешнихLLMPOST/37931всехPOST, один из20fallback slots занят. Hotpot прежний.
Сохранённый full fallback replay сохраняет реальную модель/response identity.
Второй такой child запрещён. Partial primary не принимается и не отправляется снова.
После offline gates/clean HEAD требуется отдельный допуск exact child SHA/расходов;
старое согласие на original plan не подменяется. Mu source audit предшествует Hotpot,
QA/E2/merge не запускаются. Это восстановление исполнения, не изменение benchmark.


### 23 октября: один local embedding socket child после полного extraction

Mu06ee684/acdf13d5 завершил5500extractions и failed на /api/embed HTTP400:
внутренний /tokenize bind WSAENOBUFS (buffer space/queue full). Причина ресурса
не доказана, после паузы socket counts малы. Server restart/probe не делались.
Unknown3967reserved, known2283204сохранены; E1cost_complete=false/4из6.

Решение для отдельного допуска: existing runner создаёт один canonical socket
child, новый output/run и11history Mu, прежний fallback root/2claims. Mu новый
LLMPOST cap0, extraction только verified cache; новый остаток11363316tokens/
33494всехPOST. Hotpot20M/11020LLM/40000всехPOST остаётся за Mu source audit.
Параметры extraction/reader/model/digest/vector dimension/truncate не меняются.
Пауза после response≥2s/0.25s per text, новые physical embedding batches≤8;
canonical sorting с восстановлением caller order и private per-request inputs.
Это mitigation без утверждения доказанного исправления сервера. Первая ошибка
останавливает child, повторного socket child/скрытого retry нет.

Полные совместимые32-text stages reuse:45857entity vectors сопоставлены с
verified normalized responses; частичные8864fact vectors сохранены, но без input
mapping после set order shift их reuse не установлен. Альтернатива угадать mapping
отвергнута. Facts66082могут потребовать нового local encode; расходы прежних
8864иunknown не возвращаются. Новая physical grouping отражается в export,
численные результаты свежих batches не объявляются битово равными старым.
Отдельное согласие exact SHA требуется до HTTP; это не новый benchmark и не
автоматическое требование нового научного согласования. QA/E2/merge запрещены.

## Консолидация сдачи — 26 октября

Одна issue13 сдаётся итоговым Draft PR33. Исправления PR34 уже перенесены
(1d41ad4,bc2de84) и развиты без потери исходных тестов; карта в
[протоколе E1](../docs/E1_INDEXING.md#консолидация-issue-13-в-итоговый-pr-33--26-октября).
Старые команды/статусы34 не восстанавливаются. Закрытие заменённого PR без merge
не закрывает issue, не меняет runtime pins и не означает новый эксперимент.

## Разрешение интеграции итоговых PR

Научные O/N/R/H подтверждены куратором по текущему сообщению пользователя,
без выдуманной ссылки/даты решения и без заявления о GitHub/bot approval.
Сохранённые отдельные допуски mixed extractor/continuations/unknown действуют
в своей прежней области; новые расходы и экспериментальные вызовы не разрешены.
При выполненных критериях и актуальных CI разрешены Ready и обычный merge33,
затем36 с проверкой новой базы. Защита/checks/reviews не обходятся. Ограничения
semantic_verified=false/cost_complete=false не снимаются. После E1/E2 очередь —
issue15 (протокол и reuse), сам этап15 в этой задаче не запускается.
