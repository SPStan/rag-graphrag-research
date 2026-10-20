# ADR-0020: официальный RAPTOR на 50 passages

## Статус и контекст

Принято для ограниченной проверки Issue #12; результат реального запуска
фиксируется отдельно в `results/summary/raptor-smoke.json`. Это не выбор
лучшего метода и не сравнительный benchmark. #12 не зависит от заблокированного
OpenIE #11: дерево RAPTOR не использует OpenIE.

## Решение и альтернативы

Используем реализацию из трека: `parthsarthi03/raptor`, commit
`7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767`. Проверяем Git revision, набор и
содержимое всех Python файлов перед импортом. Алгоритм UMAP/GMM, soft clustering
и collapsed-tree retrieval остаются upstream. Fork и собственный clustering
не выбраны, чтобы малый smoke проверял именно указанную реализацию.

Адаптер использует поддерживаемые BaseEmbeddingModel/BaseSummarizationModel:
BGE-M3 через локальный Ollama и Qwen через целевой HTTP API. Upstream OpenAI,
SBERT и tenacity callbacks не создаются; weights не скачиваются. Все POST идут
через общий durable Journal и Requests без retry/redirect. Отсутствующий usage,
ошибка формата или лимит останавливают запуск; автоматического resume нет.

50 готовых passages становятся 50 leaf nodes через upstream `create_node`,
затем `construct_tree`. Повторный split объединённого текста потерял бы ID.
Выбор: первые три разрешённых development ID MuSiQue, supporting union и первые
остальные passages до 50. Метки участвуют только в выборе и оценке, не в prompt.
Это support-preserving диагностика, не эффективность retrieval.

Два уровня максимум, reduction dimension 5, threshold 0.1, cluster length 3000
cl100k, summary output cap 512, collapsed top-5 nodes, context cap 3000 cl100k.
Общий Dense reader/template и target parser переиспользованы. Cl100k — только
структурный tokenizer RAPTOR, не tokenizer Qwen. Контекст и revision target
неизвестны. UTF-8 reservation и 100000 combined tokens — ограничение учёта,
не доказательство соответствия backend window. Предел: 100 POST, 20 summaries,
16000 bytes сериализованных generation messages, никаких полных выборок.

## Окружение и отклонения

Отдельная Python 3.12 Windows venv; 60 установленных версий закреплены в
`requirements-raptor-smoke.txt`, основной/check/HippoRAG env не меняется.
Original numpy 1.26.3, OpenAI 1.3.3, SBERT 2.2.2, transformers 4.38.1,
tenacity 8.2.3, UMAP 0.5.5 сохранены. Tiktoken 0.5.1 заменён на 0.7.0
(нет cp312 wheel, build требует Rust); encoding остаётся cl100k.
HTTPX 0.27.2 и huggingface-hub 0.25.2 сохраняют старые import/interfaces;
sklearn 1.5.2 совместим с UMAP 0.5.5. Torch 2.5.1, faiss 1.13.1 и остальные
ранее неприкреплённые зависимости закреплены по фактическому окружению.
Upstream urllib3 1.26.6 заменён на 2.8.0 для используемого Requests 2.34.2.
Алгоритмические исходники не правятся.

## Последствия, проверка и пересмотр

JSON tree сохраняет text, embeddings, children, levels, roots и passage ID.
Reload создаёт только Node/Tree, не Builder и не callbacks: журнал должен быть
неизменен, дерево совпадать. Проверяем cycles, missing children, невалидные
векторы/levels; ancestry объединяется без повторного счёта soft overlaps.
Публикуем provenance coverage и число leaf passages; passage recall@5 для
summary nodes — `not comparable`, ancestry не доказывает сохранение факта.

Offline regression строит настоящий upstream tree на 50 синтетических векторах,
проверяет reload и retrieval без сети. Обычный offline gate не устанавливает
RAPTOR: opt-in SDK test выполняется отдельно. Реальный smoke проверяет три
reader запроса, usage всех summaries и embeddings. Seed 42 и один поток
фиксируются; upstream UMAP без явного random_state не даёт обещания побитовой
повторяемости rebuild. Результат reload проверяется для фактически сохранённого
дерева. Пересмотр нужен перед большим корпусом, comparative benchmark или
изменением backend/dependencies/лимитов.

## Дополнение 20 октября: продолжение после timeout

Принятие unknown historical usage преподавателем передано пользователем в чате.
Один свежий bounded run по [протоколу](../docs/RAPTOR_SMOKE.md): прежние guards,
read timeout300 по успешной диагностике, все старые попытки в aggregate.
Timeout cause и старый server usage не восстановлены; новых автоматических
повторов нет. Согласие не переносится на full corpus или будущие расходы.

Фактическое продолжение 20 октября остановлено на двенадцатом summary:
finish_reason=length при cap512, usage897/512 сохранён. Новый journal полон,
общий расход неполон. Дерево/reader не завершены; перед следующими расходами
пересмотреть отдельную bounded policy truncated summary, без удаления claim.
