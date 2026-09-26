"""ADR-0012: diagnostic QA on a COPY of an existing graph; never indexes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
import uuid

import numpy as np
import requests

from scripts import run_hipporag as h
from scripts import run_dense as d
from scripts.answer_parser import extract_reader_answer
from scripts.evaluate_dense import read_jsonl, validate_manifest_file, evaluate

ROOT = h.ROOT
DENSE_ID = '98d8b412-cec6-45e4-9c14-0e4ad85855bb'
INDEX_ID = 'e78eff08-532a-40b3-a359-49a6b08b32a7'


def tree_hashes(path):
    return {p.relative_to(path).as_posix(): h.sha256_file(p)
            for p in sorted(path.rglob('*')) if p.is_file()}


def validate_pair_inputs(dense, rows, source):
    if [r['question_id'] for r in rows] != source['expected_question_ids']:
        raise ValueError('Ordered question IDs differ')
    if dense['inputs']['corpus_sha256'] != source['inputs']['corpus_sha256']:
        raise ValueError('Corpus differs')
    for key in ('generation', 'embedding'):
        if dense[key]['model']['digest'] != source[key]['model']['digest']:
            raise ValueError(f'{key} digest differs')
    if dense['generation']['reader_template_sha256'] != h.reader_template_metadata()[1]:
        raise ValueError('Reader template differs')
    if dense['generation']['options'] != d.GENERATION_OPTIONS:
        raise ValueError('Reader options differ')
    if dense['retrieval']['top_k'] != 5:
        raise ValueError('Expected top-5')
    for row in rows:
        if (row['generation_options'] != dense['generation']['options']
                or row['reader_prompt_version'] != dense['generation']['reader_prompt_version']
                or row['top_k'] != 5
                or row['generation_model']['digest'] != dense['generation']['model']['digest']
                or row['embedding_model']['digest'] != dense['embedding']['model']['digest']):
            raise ValueError('Dense row config differs')


class NativeChat:
    """One request per call, checkpoint before dispatch; no hidden retries."""
    def __init__(self, session, output, model, options):
        self.session, self.output, self.model = session, output, model
        self.options = options
        self.events = []
        self.question_id = None
        self.stage = 'fact_filter'
        self.error = None

    def infer(self, messages, **kwargs):
        if len(self.events) >= 200:
            raise RuntimeError('200 chat request budget exhausted')
        record = {'question_id': self.question_id, 'stage': self.stage,
                  'messages': messages, 'status': 'in_flight'}
        path = self.output / f'{len(self.events):04d}.json'
        h.write_json_atomic(path, record)
        self.events.append(record)
        started = time.perf_counter()
        try:
            options = dict(self.options)
            options['num_predict'] = kwargs.get('max_new_tokens', 512)
            payload = {'model': self.model, 'messages': messages,
                       'stream': False, 'options': options}
            # Both the DSPy marker prompt and common reader require text.
            response = self.session.post(d.OLLAMA_URL + '/api/chat', json=payload, timeout=300)
            response.raise_for_status()
            result = response.json()
            d.require_completed_generation(result, self.question_id)
            record.update(status='completed', response=result,
                          seconds=time.perf_counter() - started, options=options)
            h.write_json_atomic(path, record)
            return result['message']['content'], {
                'finish_reason': result['done_reason'],
                'prompt_tokens': result.get('prompt_eval_count'),
                'completion_tokens': result.get('eval_count')}, False
        except BaseException as exc:
            self.error = exc
            record.update(status='unknown_or_failed', error_type=type(exc).__name__)
            h.write_json_atomic(path, record)
            raise


def paired_summary(left, right, seed=42):
    a, b = left['per_question'], right['per_question']
    if [r['question_id'] for r in a] != [r['question_id'] for r in b]:
        raise ValueError('Unpaired results')
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(a), size=(10000, len(a)))
    result = {}
    for key in ('em', 'f1', 'recall_at_k'):
        delta = np.array([y[key] - x[key] for x, y in zip(a, b)])
        result[key] = {'hipporag_minus_dense': float(delta.mean()),
                       'paired_bootstrap_95_percent': np.quantile(
                           delta[samples].mean(axis=1), [.025, .975]).tolist(),
                       'better': int((delta > 0).sum()), 'equal': int((delta == 0).sum()),
                       'worse': int((delta < 0).sum())}
    return result


def run(execute=False):
    dense_path = ROOT / f'results/raw/dense-musique-{DENSE_ID}.jsonl'
    source_path = ROOT / f'results/raw/hipporag2-musique-{INDEX_ID}.manifest.json'
    dense = h.read_json(dense_path.with_suffix('.manifest.json'))
    source = h.read_json(source_path)
    dense_rows = read_jsonl(dense_path)
    validate_manifest_file(dense_path, dense_rows, dense)
    validate_pair_inputs(dense, dense_rows, source)
    for key in ('corpus', 'queries', 'labels'):
        if h.sha256_file(Path(source['inputs'][key + '_path'])) != source['inputs'][key + '_sha256']:
            raise ValueError(f'{key} hash mismatch')
    corpus = h.read_json(Path(source['inputs']['corpus_path']))
    query_map = {q['id']: q for q in h.read_json(Path(source['inputs']['queries_path']))}
    queries = [query_map[qid] for qid in dense['expected_question_ids']]
    if len(queries) != 100:
        raise ValueError('Expected exactly the frozen 100 questions')
    source_storage = Path(source['storage_dir'])
    hashes = tree_hashes(source_storage)
    if not any(p.endswith('graph.pickle') for p in hashes):
        raise ValueError('Existing graph required')
    if not execute:
        print(json.dumps({'status': 'dry_run_verified', 'questions': len(queries),
                          'index_files': len(hashes), 'independent_benchmark_eligible': False}))
        return
    session = requests.Session()
    session.trust_env = False
    for kind in ('generation', 'embedding'):
        actual = d.model_info(session, dense[kind]['model']['name'])
        if actual['digest'] != dense[kind]['model']['digest']:
            raise ValueError(f'Installed {kind} digest changed')
    run_id = str(uuid.uuid4())
    output = ROOT / f'results/raw/hipporag2-musique-{run_id}.jsonl'
    manifest_path = output.with_suffix('.manifest.json')
    work = ROOT / 'storage' / f'comparison-asbuilt-{run_id}'
    copy = work / 'index'
    shutil.copytree(source_storage, copy)
    if tree_hashes(copy) != hashes:
        raise ValueError('Index copy checksum mismatch')
    os.environ.setdefault('HF_HOME', str(work / 'hf-cache'))
    manifest = {'schema_version': 2, 'run_id': run_id, 'dataset': 'musique',
                'status': 'running', 'mode': 'diagnostic-as-built',
                'independent_benchmark_eligible': False,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'source': h.git_snapshot(), 'source_index_run_id': INDEX_ID,
                'source_manifest_sha256': h.sha256_file(source_path),
                'source_index_sha256': hashes,
                'source_openie_acceptance_gate': source['index']['openie_acceptance_gate'],
                'expected_question_ids': dense['expected_question_ids'],
                'inputs': source['inputs'], 'generation': dense['generation'],
                'embedding': dense['embedding'], 'retrieval': {'top_k': 5},
                'results_file': output.name, 'paired_dense_run_id': DENSE_ID,
                'paired_dense_results_sha256': h.sha256_file(dense_path)}
    h.write_json_atomic(manifest_path, manifest)
    native = NativeChat(session, work / 'requests', dense['generation']['model']['name'],
                        dense['generation']['options'])
    HippoRAG, CacheOpenAI, Embedding, Config = h.load_hipporag_classes()
    config = Config(llm_name='qwen2.5_3b', embedding_model_name='bge-m3_latest',
                    llm_base_url=h.OLLAMA_BASE_URL, embedding_base_url=h.OLLAMA_BASE_URL,
                    embedding_provider='openai', embedding_batch_size=1,
                    save_dir=str(copy), dataset='musique', qa_top_k=5,
                    retrieval_top_k=200, temperature=0, seed=42, max_new_tokens=512,
                    response_format={'type': 'json_object'}, max_retry_attempts=1)
    native.global_config = config
    llm = CacheOpenAI.from_experiment_config(config)
    llm.cache_file_name = str(work / 'unused-query-cache.sqlite')
    llm.infer = native.infer
    index_manifest = h.read_json(copy / 'qwen2.5_3b_bge-m3_latest/index_manifest.json')
    embedding = Embedding(global_config=config)
    h.install_no_truncate_embedding_api(embedding, h.OLLAMA_BASE_URL, 'bge-m3:latest')
    rag = None
    rows = []
    start = time.perf_counter()
    try:
        rag = HippoRAG(global_config=config, extraction_llm=llm, qa_llm=llm,
                       embedding_model=embedding,
                       index_identity=index_manifest['components']['explicit_identity'])
        if not rag._graph_state_available:
            raise ValueError('Graph missing; rebuild prohibited')
        def forbidden(*args, **kwargs):
            raise RuntimeError('Index/OpenIE prohibited in diagnostic QA')
        rag.index = forbidden
        rag.openie.ner = forbidden
        rag.openie.triple_extraction = forbidden
        texts = {p['title'] + '\n' + p['text']: p for p in corpus}
        stored = rag.chunk_embedding_store.get_all_id_to_rows()
        if {r['content'] for r in stored.values()} != set(texts):
            raise ValueError('Index does not exactly cover the fixed corpus')
        rag.prepare_retrieval_objects()
        embedding_events = []
        original_encode = embedding.batch_encode
        def measured_encode(*args, **kwargs):
            t = time.perf_counter()
            value = original_encode(*args, **kwargs)
            embedding_events.append({'seconds': time.perf_counter() - t,
                                     'usage': dict(embedding.last_usage)})
            return value
        embedding.batch_encode = measured_encode
        filter_logs = []
        original_filter = rag.rerank_facts
        def measured_filter(*args, **kwargs):
            value = original_filter(*args, **kwargs)
            filter_logs.append({'selected_facts': len(value[1]), 'log': value[2]})
            return value
        rag.rerank_facts = measured_filter
        with output.open('x', encoding='utf-8') as stream:
            for i, query in enumerate(queries):
                if time.perf_counter() - start > 7200:
                    raise TimeoutError('Two-hour question-start deadline exceeded')
                native.question_id, native.stage = query['id'], 'fact_filter'
                eb_start, calls_start = len(embedding_events), len(native.events)
                t = time.perf_counter()
                solution = rag.retrieve([query['question']], num_to_retrieve=5)[0]
                if native.error:
                    raise RuntimeError('Retrieval swallowed transport failure') from native.error
                retrieval_seconds = time.perf_counter() - t
                passages = [texts[text] for text in solution.docs[:5]]
                messages = d.build_reader_messages(query['question'], passages)
                native.stage = 'reader'
                generation_start = time.perf_counter()
                raw, meta, _ = native.infer(messages)
                generation_seconds = time.perf_counter() - generation_start
                answer, status = extract_reader_answer(raw)
                row = {'run_id': run_id, 'dataset': 'musique', 'mode': 'diagnostic-as-built',
                       'question_id': query['id'], 'planned_question_ids': dense['expected_question_ids'],
                       'question': query['question'], 'answer': answer, 'raw_answer': raw,
                       'answer_extraction_status': status, 'done': True,
                       'done_reason': meta['finish_reason'], 'top_k': 5,
                       'generation_model': dense['generation']['model'],
                       'embedding_model': dense['embedding']['model'],
                       'generation_options': dense['generation']['options'],
                       'reader_prompt_version': dense['generation']['reader_prompt_version'],
                       'retrieved': [{'id': p['id'], 'score': float(score)}
                                     for p, score in zip(passages, solution.doc_scores)],
                       'prompt_tokens': meta['prompt_tokens'], 'completion_tokens': meta['completion_tokens'],
                       'query_embedding_client_seconds': sum(e['seconds'] for e in embedding_events[eb_start:]),
                       'query_embedding_prompt_tokens': sum(e['usage']['prompt_tokens'] for e in embedding_events[eb_start:]),
                       'retrieval_seconds': retrieval_seconds, 'generation_wall_seconds': generation_seconds,
                       'question_end_to_end_seconds': time.perf_counter() - t,
                       'dense_fallback': filter_logs[-1]['selected_facts'] == 0,
                       'fact_filter_diagnostic': filter_logs[-1],
                       'chat_calls': len(native.events) - calls_start}
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                stream.flush()
                print(f'[{i+1}/100] saved; graph_facts={filter_logs[-1]["selected_facts"]}; reader={meta["finish_reason"]}', flush=True)
        manifest.update(status='completed', results_sha256=h.sha256_file(output))
        labels = h.read_json(Path(source['inputs']['labels_path']))
        metrics = evaluate(rows, labels, manifest=manifest)
        h.write_json_atomic(output.with_suffix('.metrics.json'), metrics)
        dense_metrics = evaluate(dense_rows, labels, manifest=dense)
        safe_metrics = lambda m: {k: m[k] for k in ('run_id', 'em', 'token_f1', 'recall_at_k', 'generation_stopped_normally', 'usage')}
        summary = {'kind': 'diagnostic-as-built-paired-comparison',
                   'independent_benchmark_eligible': False, 'questions': len(rows),
                   'corpus_passages': len(corpus), 'dense': safe_metrics(dense_metrics),
                   'hipporag2': safe_metrics(metrics), 'paired': paired_summary(dense_metrics, metrics),
                   'source_index_run_id': INDEX_ID, 'unresolved_openie_outcomes': 160,
                   'dense_fallback_questions': sum(r['dense_fallback'] for r in rows),
                   'reader_model': dense['generation']['model'], 'embedding_model': dense['embedding']['model'],
                   'reader_options': dense['generation']['options'],
                   'reader_template_sha256': dense['generation']['reader_template_sha256'],
                   'corpus_sha256': source['inputs']['corpus_sha256'],
                   'ordered_ids_sha256': source['inputs']['evaluation_view']['ordered_question_ids_sha256'],
                   'dense_results_sha256': h.sha256_file(dense_path),
                   'hipporag_results_sha256': h.sha256_file(output),
                   'chat_usage_by_stage': {stage: {
                       'calls': sum(e['stage'] == stage for e in native.events),
                       'prompt_tokens': sum(e['response']['prompt_eval_count'] for e in native.events if e['stage'] == stage),
                       'completion_tokens': sum(e['response']['eval_count'] for e in native.events if e['stage'] == stage)}
                       for stage in ('fact_filter', 'reader')},
                   'limitations': ['Diagnostic as-built graph; strict index gate remains failed.',
                                   'Historical total indexing cost unknown; query costs do not include it.',
                                   'Small fixed local candidate, not target API benchmark.',
                                   'Dense timing was measured in an earlier session; no controlled speed comparison.',
                                   'Embedding preprocessing differs between package and Dense; same model, not identical pipeline.']}
        manifest['comparison_summary'] = summary
        if tree_hashes(source_storage) != hashes:
            raise RuntimeError('Source index changed')
        manifest['source_index_unchanged'] = True
        h.write_json_atomic(ROOT / 'results/summary/dense-vs-hipporag-asbuilt100.json', summary)
        print(json.dumps({'status': 'completed', 'run_id': run_id, 'paired': summary['paired']}), flush=True)
    except BaseException as exc:
        manifest.update(status='failed', error_type=type(exc).__name__, error=str(exc),
                        completed_questions=len(rows))
        raise
    finally:
        if rag is not None:
            rag.close()
        llm.close()
        manifest['source_index_unchanged'] = tree_hashes(source_storage) == hashes
        h.write_json_atomic(manifest_path, manifest)
        session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    run(parser.parse_args().execute)
