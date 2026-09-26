import tempfile
import unittest
from pathlib import Path
from scripts.compare_asbuilt import NativeChat, paired_summary, tree_hashes, validate_pair_inputs


class CompareAsbuiltTests(unittest.TestCase):
    def test_reuse_rejects_corpus_or_model_change_before_requests(self):
        dense = {'inputs': {'corpus_sha256': 'one'},
                 'generation': {'model': {'digest': 'a'}}}
        source = {'expected_question_ids': ['a'], 'inputs': {'corpus_sha256': 'two'},
                  'generation': {'model': {'digest': 'b'}}}
        with self.assertRaisesRegex(ValueError, 'Corpus'):
            validate_pair_inputs(dense, [{'question_id': 'a'}], source)
        source['inputs']['corpus_sha256'] = 'one'
        with self.assertRaisesRegex(ValueError, 'digest'):
            validate_pair_inputs(dense, [{'question_id': 'a'}], source)

    def test_pairing_rejects_reordered_ids(self):
        left = {'per_question': [{'question_id': 'a'}, {'question_id': 'b'}]}
        right = {'per_question': list(reversed(left['per_question']))}
        with self.assertRaises(ValueError):
            paired_summary(left, right)

    def test_paired_bootstrap_constant_difference(self):
        left = {'per_question': [{'question_id': str(i), 'em': 0, 'f1': 0, 'recall_at_k': 0} for i in range(3)]}
        right = {'per_question': [{'question_id': str(i), 'em': 1, 'f1': 1, 'recall_at_k': 1} for i in range(3)]}
        result = paired_summary(left, right)
        self.assertEqual(result['f1']['paired_bootstrap_95_percent'], [1, 1])
        self.assertEqual(result['f1']['better'], 3)

    def test_transport_persists_before_request_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            class Session:
                calls = 0
                def post(self, *args, **kwargs):
                    self.calls += 1
                    assert (folder / '0000.json').exists()
                    assert kwargs['json']['options']['num_ctx'] == 4096
                    assert 'format' not in kwargs['json']
                    raise TimeoutError('synthetic')
            session = Session()
            chat = NativeChat(session, folder, 'fake', {'num_ctx': 4096})
            with self.assertRaises(TimeoutError):
                chat.infer([{'role': 'user', 'content': 'synthetic'}])
            self.assertEqual(session.calls, 1)
            self.assertEqual(chat.events[0]['status'], 'unknown_or_failed')

    def test_tree_hash_detects_changed_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'graph').write_text('a')
            before = tree_hashes(root)
            (root / 'graph').write_text('b')
            self.assertNotEqual(before, tree_hashes(root))


if __name__ == '__main__':
    unittest.main()
