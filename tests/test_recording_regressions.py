"""Regressions for defects seen in the 2026-11-06 owner screen recording.

1. Web/Smart Hybrid research failed outright with "Semantic retrieval needs
   2 GiB available RAM" instead of continuing with lexical FTS5 retrieval.
2. Agent Mode with one attached PDF stopped with "Agent context budget
   exhausted" on the default 4096-token window after a single tool result.
"""
import json,sqlite3,tempfile,threading,unittest
from pathlib import Path
from unittest import mock

from agent_runtime import bound_observation_payload,canonical,tighten_observation_payloads
from workspace_services import LocalWorkspace,migrate_database


class LowMemoryRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.con=sqlite3.connect(self.root/'offline_gpt.sqlite3',check_same_thread=False);self.addCleanup(self.con.close)
        migrate_database(self.con,self.root);self.ws=LocalWorkspace(self.con,threading.RLock(),self.root)
        model=self.root/'encoder.onnx';vocab=self.root/'vocab.txt';model.write_bytes(b'fixture');vocab.write_text('[PAD]\n',encoding='utf-8')
        from intelligence_engine import IntelligenceEngine
        self.engine=IntelligenceEngine(self.ws,{'embedding_model_path':str(model),'embedding_vocab_path':str(vocab)})
        doc=self.root/'note.txt';doc.write_text('Orchid calibration interval is seventeen days.',encoding='utf-8')
        self.engine.knowledge.index([str(doc)],'')

    def test_low_ram_uses_lexical_retrieval_without_loading_encoder(self):
        self.assertTrue(self.engine.health()['embeddingAvailable'])
        with mock.patch('integrated_runtime.physical_memory_status',return_value={'available':1*1024**3}), \
             mock.patch('knowledge_engine.LocalEmbedding',side_effect=AssertionError('encoder must stay unloaded')):
            sources=self.engine.search('orchid calibration')
        self.assertEqual('lexical_low_memory',self.engine.last_retrieval_mode)
        self.assertTrue(any('seventeen' in (s.get('excerpt') or '') for s in sources))


class ObservationTighteningTests(unittest.TestCase):
    def test_large_attachment_observation_is_rebounded_with_coverage(self):
        text='Self learning systems adapt. '*600
        value=bound_observation_payload({'source':'attachment:abc','content':text},max_bytes=5500)
        messages=[{'role':'system','content':'s'},{'role':'user','content':'summarise'},{'role':'assistant','content':'{}'},
                  {'role':'user','content':'UNTRUSTED TOOL OBSERVATION: '+canonical({'tool':'read_attachment','result':value})}]
        tightened=tighten_observation_payloads(messages,1200)
        self.assertIsNot(tightened,messages)
        self.assertLess(len(tightened[3]['content'].encode()),len(messages[3]['content'].encode()))
        result=json.loads(tightened[3]['content'][len('UNTRUSTED TOOL OBSERVATION: '):])['result']
        self.assertTrue(result.get('omitted') or result.get('truncated'))
        self.assertEqual(messages[:3],tightened[:3])

    def test_small_observations_are_unchanged(self):
        messages=[{'role':'system','content':'s'},{'role':'user','content':'q'},{'role':'user','content':'UNTRUSTED TOOL OBSERVATION: '+canonical({'tool':'calculate','result':{'value':4}})}]
        self.assertIs(tighten_observation_payloads(messages,1200),messages)


if __name__=='__main__':
    unittest.main()
