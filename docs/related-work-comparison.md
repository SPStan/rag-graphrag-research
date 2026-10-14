# Сравнение опубликованных RAG-методов

Обзор для [issue #25](https://github.com/SPStan/rag-graphrag-research/issues/25), проверен агентом 14 октября 2026. Это сопоставление устройства методов, без новых экспериментов и численного рейтинга. [Слайдовый вариант](#slide-version) готов к переносу в презентацию; файла презентации в актуальном master нет. Исходная библиография и неподтверждённый журнал чтения студента сохранены в [READING](READING.md). Оценка задачи — 2 часа работы студента; фактическое время его работы здесь не измерялось.

Выбраны конкретные конфигурации: RAG-Sequence для Natural Questions у Lewis et al.; основная конфигурация HippoRAG 2 из таблицы 2 его статьи; RAPTOR + SBERT + GPT-4 для QASPER из таблицы 3 оригинальной статьи. Это разные экспериментальные условия, поэтому их опубликованные оценки не объединяются в рейтинг.

<a id="full-comparison"></a>

## Полная таблица особенностей

Стоимость ниже означает источники работы и вызовов, а не измеренный расход нашего проекта. PPR — Personalized PageRank; OpenIE — извлечение открытых отношений; passage — исходный текстовый фрагмент.

| Метод / опубликованный вариант | Представление индекса | Индексация и вызовы моделей | Поиск и контекст | Многошаговые вопросы | Генератор / эмбеддер | Затраты индексации | Затраты ответа | Ограничение и источник |
|---|---|---|---|---|---|---|---|---|
| **Dense RAG: RAG-Sequence, NQ** [D] | Векторы Wikipedia-passages, FAISS/MIPS | DPR кодирует passages; генеративные summaries/OpenIE для индекса не нужны (§2.2, §3) | top-k MIPS; BART обрабатывает вопрос с каждым passage, вероятности ответов маргинализуются (§2.1, §2.5) | Явного обхода связей в описанном поиске нет; это вывод из алгоритма, а не доказательство неспособности dense RAG к multi-hop | BART-large; DPR, BERT-base bi-encoder (§2.2–2.4) | Passage embeddings и FAISS; отдельно обучение query encoder/BART, document encoder закреплён (§2.4, §3) | Query embedding, MIPS, генерация/оценка кандидатов по passages (§2.5) | NQ-конфигурация не воспроизводит наш baseline. Точное test-time k выбранного checkpoint здесь не установлено. [D §2–3.1][d] |
| **HippoRAG 2: основная конфигурация** [H] | Phrase- и passage-узлы; relation, synonym, contains-рёбра (§3.1–3.2) | LLM OpenIE; embeddings passages/phrases/triples; построение графа ([H-code]) | Query-to-triple → LLM-фильтр → PPR → top-5 исходных passages; при пустом наборе triples dense fallback (§3.3–3.5, §4.4) | PPR распространяет активацию по связям; MuSiQue/HotpotQA входят в проверку (§4.2) | Llama-3.3-70B-Instruct: extraction/filter/reader; NV-Embed-v2 (§4.4, табл. 2) | Extraction tokens, embeddings, связи и хранение графа | Query embeddings, triple filter, PPR и reader | Ошибки фильтра/PPR разобраны в App. E; расход зависит от конфигурации (App. F, табл. 12). Это версия 2, с passage-узлами и recognition memory. [H][h] |
| **RAPTOR: SBERT + GPT-4, QASPER** [R] | Листья — исходные chunks; верхние узлы — summaries (§3) | Embedding → UMAP/GMM soft clustering → LLM summary → embedding рекурсивно (§3) | Collapsed tree: cosine-поиск по всем уровням, выбранные тексты в контекст; в статье бюджет 2000 tokens. Есть tree traversal (§3, Fig. 3) | Объединяет сведения в summaries; multi-hop иллюстрируется качественным примером, основной фокус — длинные документы (§3–4) | GPT-4 reader; gpt-3.5-turbo summaries; SBERT multi-qa-mpnet-base-cos-v1 (§3, табл. 3) | Embeddings листьев/summaries, clustering и summary tokens | Query embedding, поиск узлов и reader | Summaries могут терять детали/ошибаться (App. E). Бюджет статьи не равен нашему top-5; top-5 узлов не равен passage recall@5. [R][r] |

[D], [H], [R] обозначают версии статей в библиографии ниже; локаторы в ячейках относятся именно к этим версиям. Затраты, выведенные из операций алгоритма, не задают число HTTP-запросов: batching, cache и retry зависят от реализации. Денежные цены, точные serving revisions и полный сопоставимый расход всех трёх выбранных конфигураций здесь **не установлены**. Отсутствие сведений в README не трактуется как отсутствие возможности метода.

## Связь с нашим исследованием

RAG-Sequence выбран как конкретный опубликованный представитель dense retrieval + generation, а не как описание всех современных dense RAG. Наш [baseline в SPEC](SPEC.md#замороженный-план-сравнения-для-issue-7) использует BGE-M3, cosine top-5 и единый prompt-reader с объединённым контекстом; совместное обучение и маргинализация RAG-Sequence в нём не выполняются. Поэтому проект сравнивает свои адаптеры в единых условиях, а не воспроизводит оценки Lewis et al.

| Уровень сведений | Что означает в этой работе |
|---|---|
| Опубликованные конфигурации | Только таблица выше; разные модели, корпуса и протоколы. Числа качества не переносим в проект |
| Наш локальный результат | Отдельное [диагностическое сравнение сентября](COMPARISON_2026-09-26.md); не основной benchmark и не оценка RAPTOR |
| Целевой протокол проекта | [SPEC](SPEC.md), [DATA](DATA.md), [ADR-0015](../.adr/0015-pinned-comparison-and-signal-split.md): общие ID/корпуса, Qwen/BGE-M3, reader/оценщик, учёт фаз. Малые проверки не доказывают сравнительное преимущество; текущая очередь в [TASKS](TASKS.md) |

Для RAPTOR сохраняем тип/уровень полученного узла и reader input tokens. Если контекст включает summaries, passage recall@5 обозначается `not comparable`; объединение исходных passage IDs можно оценить отдельно как provenance coverage, указав их число. Оно не доказывает, что нужный факт сохранился в summary. Эти правила уже закреплены в SPEC; реализация RAPTOR в этом PR не меняется.

<a id="slide-version"></a>

## Таблица для одного слайда

**Аналоги: что индексируют и что получает reader**

| Метод | Индекс | Поиск → контекст | Дополнительная работа | Главная оговорка |
|---|---|---|---|---|
| Dense / RAG-Sequence [D] | Векторы passages | MIPS → passage-кандидаты | Кодирование корпуса | Наш prompt-reader отличается |
| HippoRAG 2 [H] | Граф + passage-векторы | Triple filter + PPR → passages | OpenIE + фильтр triples | Ошибки извлечения/поиска |
| RAPTOR [R] | Chunks + summaries | Все уровни → тексты узлов | Рекурсивные summaries | Узел ≠ исходный passage |

Dense ищет исходные фрагменты, HippoRAG 2 связывает их через граф, RAPTOR добавляет уровни суммаризации. Открытый вопрос проекта: когда дополнительная индексация окупается по качеству и полной стоимости при одинаковых данных и моделях? Проверяем это на MuSiQue/HotpotQA с общим reader и учётом фаз; предполагаемый вклад — сопоставимый анализ условий, а научная новизна и преимущество ещё не доказаны.

Источники для подписи слайда: [D — Lewis et al.][d], [H — Gutiérrez et al., HippoRAG 2][h], [R — Sarthi et al.][r]; условия и оговорки — [полная таблица](#full-comparison).

## Что подготовить к объяснению на ревью

Перед обсуждением студенту нужно своими словами ответить на три вопроса:

1. Чем наш dense baseline отличается от RAG-Sequence в строке [D]? Объяснить роль общего prompt-reader и маргинализации, опираясь на раздел «Связь с нашим исследованием».
2. Зачем HippoRAG 2 нужны passage-узлы, фильтр triples и PPR, и когда срабатывает dense fallback? Проверить §3.2–3.5 источника [H].
3. Почему пять RAPTOR-узлов нельзя оценивать как пять исходных passages? Различить качество ответа, passage recall@5 и provenance coverage по SPEC и строке [R].

Агент повторно сверил таблицу с указанными версиями статей и официального кода 15 октября 2026. Это подготовительные вопросы, а не подтверждение самостоятельного чтения или готовности студента к защите. Согласие куратора по O1/N1/R1/H1 проверяется отдельно от технического ревью.

## Первоисточники и версии

- **[D]** Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, NeurIPS 2020; проверена [arXiv v4, 12.04.2021][d], §2.1–2.5, §3–3.1. Официальный опубликованный checkpoint [facebook/rag-sequence-nq](https://huggingface.co/facebook/rag-sequence-nq); точная ревизия весов не закрепляется, веса не скачивались. [Официальные examples/rag в Transformers v3.5.1](https://github.com/huggingface/transformers/tree/v3.5.1/examples/rag) — версия связанного кода для справки, не доказательство commit исходного эксперимента.
- **[H]** Jiménez Gutiérrez et al., *From RAG to Memory: Non-Parametric Continual Learning for Large Language Models*, 2025; проверена [arXiv v2, 19.06.2025][h], §3, §4.4, табл. 2, App. E/F. **[H-code]** [официальный HippoRAG.py, commit 1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff](https://github.com/OSU-NLP-Group/HippoRAG/blob/1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff/src/hipporag/HippoRAG.py): `index`, `retrieve`, `rerank_facts`, `qa`; [OpenIE](https://github.com/OSU-NLP-Group/HippoRAG/blob/1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff/src/hipporag/information_extraction/openie_openai.py): `ner`, `triple_extraction`. Эта позднейшая ревизия уже закреплена проектом; она не объявляется кодом экспериментов статьи 2025 года.
- **[R]** Sarthi et al., *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval*, 2024; проверена [arXiv v1, 31.01.2024][r], §3–4, Fig. 3, табл. 3, App. E. [Официальный код, commit 7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767](https://github.com/parthsarthi03/raptor/tree/7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767): [tree_retriever.py](https://github.com/parthsarthi03/raptor/blob/7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767/raptor/tree_retriever.py), `retrieve_information_collapse_tree`/`retrieve`; [SummarizationModels.py](https://github.com/parthsarthi03/raptor/blob/7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767/raptor/SummarizationModels.py), `GPT3TurboSummarizationModel`. Код имеет свои defaults; он не подтверждает, что все defaults совпадали с экспериментом статьи.
- **Дополнительно:** Guo et al., [LightRAG: Simple and Fast Retrieval-Augmented Generation](https://arxiv.org/abs/2410.05779), 2024, [официальный репозиторий](https://github.com/HKUDS/LightRAG). Библиографический кандидат из READING; в сравнение трёх методов и новые эксперименты здесь не включён.

[d]: https://arxiv.org/html/2005.11401v4
[h]: https://arxiv.org/html/2502.14802v2
[r]: https://arxiv.org/html/2401.18059v1
