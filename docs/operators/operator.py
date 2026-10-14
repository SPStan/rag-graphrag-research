"""One user-authorized diagnostic POST; retain unknown prior usage, no retry."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
import requests
from scripts.check_target_api import settings
from scripts import run_dense as dense
from scripts.run_dense_target import save_private_json
from scripts.token_accounting import Journal, recorded_call, read_records, summarize, verified_reference

baseline = dense.read_json(ROOT / 'results/summary/raptor-smoke.json')
prior_dir = ROOT / 'results/raw/raptor-smoke' / baseline['run_id']
prior_path = prior_dir / 'manifest.json'
prior = dense.read_json(prior_path)
verified = verified_reference(prior, prior_path)
if verified['status'] != 'verified' or verified['summary']['journal_corrupt_tail']:
    raise ValueError('Prior journal not intact')
request_path = prior_dir / 'index-summary-50.request.json'
if dense.sha256_file(prior_path) != baseline['artifacts']['manifest_sha256'] or dense.sha256_file(request_path) != baseline['artifacts']['first_summary_request_sha256']:
    raise ValueError('Prior manifest/request SHA mismatch')
payload = dense.read_json(request_path)
config = settings(dotenv_values(Path(os.environ['TARGET_API_ENV_FILE'])))
if config['model'] != payload['model'] or config['base_url'] != prior['generation']['base_url']:
    raise ValueError('Endpoint/model differs from prior')
reservation = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048 + payload['max_tokens']
if payload['max_tokens'] != 512 or reservation > 5000:
    raise ValueError('Diagnostic budget mismatch')
run_id = str(uuid.uuid4())
# Same canonical prior owns the claim regardless of diagnostic output location.
claim = prior_dir / 'summary-diagnostic-once.claim.json'
with claim.open('x', encoding='utf-8') as f:
    json.dump({'run_id': run_id, 'prior_run_id': prior['run_id'], 'maximum_new_posts': 1}, f)
    f.flush()
    os.fsync(f.fileno())
directory = ROOT / 'results/raw/raptor-summary-diagnostic' / run_id
directory.mkdir(parents=True, exist_ok=False)
journal = Journal(directory / 'tokens.jsonl', run_id=run_id, method='raptor', dataset='musique')
manifest = {
    'schema_version': 1, 'run_id': run_id, 'status': 'starting',
    'authorization': 'User explicitly requested one resend despite unknown prior usage, 2026-10-14; curator approval not claimed',
    'prior_run_id': prior['run_id'], 'prior_manifest_sha256': dense.sha256_file(prior_path),
    'prior_accounting': prior['token_accounting'], 'request_sha256': dense.sha256_file(request_path),
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'code': dense.git_snapshot(), 'model': config['model'], 'base_url': config['base_url'],
    'new_token_budget': 5000, 'request_reservation': reservation,
    'maximum_new_posts': 1, 'automatic_retries': 0, 'timeout_seconds': {'connect': 5, 'read': 300},
    'started_at': datetime.now(timezone.utc).isoformat(),
    'ready_for_indexing': False, 'tree_or_reader_started': False,
}
dense.write_json_atomic(directory / 'manifest.json', manifest)
headers = {'Authorization': 'Bearer ' + config['key'], 'X-Client-Request-Id': run_id}
save_private_json(directory / 'request.json', payload, headers)
try:
    with requests.Session() as session:
        if session.get_adapter(config['base_url']).max_retries.total != 0:
            raise ValueError('Transport retries must be zero')

        def send():
            response = session.post(config['base_url'] + '/chat/completions', json=payload, headers=headers, timeout=(5, 300), allow_redirects=False)
            try:
                body = response.json()
            except ValueError:
                body = {'unparsed_response_text': response.text}
            save_private_json(directory / 'response.json', body, headers)
            if 300 <= response.status_code < 400:
                raise ValueError('Redirect refused')
            response.raise_for_status()
            return body

        body = recorded_call(journal, send, phase='index', operation='summary_diagnostic', provider='target_api', model=config['model'], kind='llm', object_id='50')
    if not journal.summary()['complete']:
        raise ValueError('Missing usage; stop')
    if sum(journal.summary()['known_subtotal'].values()) > 5000:
        raise ValueError('Budget exceeded; stop')
    choice = body['choices'][0]
    content = choice['message']['content']
    manifest['finish_reason'] = choice.get('finish_reason')
    manifest['usage'] = body.get('usage')
    manifest['response_id'] = body.get('id')
    manifest['server_input_matches_native_350'] = body['usage']['prompt_tokens'] == 350
    if not isinstance(content, str) or not content.strip() or choice.get('finish_reason') != 'stop':
        raise ValueError('Summary invalid or incomplete')
    manifest['content_characters'] = len(content)
    manifest['status'] = 'completed'
except Exception as exc:
    manifest['status'] = 'failed'
    manifest['error_type'] = type(exc).__name__
finally:
    manifest['token_accounting'] = journal.reference()
    previous = read_records(verified['path'])
    current = read_records(journal.path)
    manifest['aggregate_accounting'] = summarize([*previous, *current])
    manifest['aggregate_total'] = None
    if manifest['aggregate_accounting']['complete']:
        raise ValueError('Unexpected complete aggregate; prior usage must stay unknown')
    response_path = directory / 'response.json'
    if response_path.exists():
        manifest['response_sha256'] = dense.sha256_file(response_path)
    manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
    dense.write_json_atomic(directory / 'manifest.json', manifest)
print(json.dumps({'run_id': run_id, 'status': manifest['status'], 'usage': manifest.get('usage'), 'finish_reason': manifest.get('finish_reason'), 'error_type': manifest.get('error_type'), 'aggregate_complete': manifest['aggregate_accounting']['complete']}))
if manifest['status'] != 'completed':
    raise SystemExit(1)
