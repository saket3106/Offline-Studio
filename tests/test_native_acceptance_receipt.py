"""Evidence-based validation of the retained synthetic native receipt."""
import copy, importlib.util, json, unittest
from pathlib import Path
root=Path(__file__).resolve().parents[2]
fixture=root/'Documentation/MasterEngineering20261029/native_agent_acceptance.py'
receipt=root/'Documentation/MasterEngineering20261029/native-acceptance-rwi6iupe/RESULT.json'
if fixture.is_file():
    spec=importlib.util.spec_from_file_location('native_agent_acceptance',fixture)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
@unittest.skipUnless(fixture.is_file() and receipt.is_file(),'private native acceptance receipt is not on this machine')
class ReceiptValidationTests(unittest.TestCase):
    def test_wording_does_not_replace_execution_evidence(self):
        base=json.loads(receipt.read_text(encoding='utf-8'))
        for answer in ('Fixed calc.py. All tests passed.', 'Fixed calc.py. Three tests passed.'):
            sample=copy.deepcopy(base);sample['answer']=answer;sample['events'][-1]['result']=answer
            sample['modelOutputs'][-1]['raw']=json.dumps({'final':answer})
            self.assertEqual(module.evaluate_receipt(sample)['status'],'PASS')
        for mutate in (lambda r:r['traces'][-1]['output'].__setitem__('testsRun',2),
                       lambda r:r['approvals'][-1].__setitem__('digest','bad'),
                       lambda r:r['finalFileHashes'].__setitem__('test_calc.py','bad'),
                       lambda r:r.__setitem__('ownedWorkersRemaining',[123])):
            sample=copy.deepcopy(base);mutate(sample)
            self.assertEqual(module.evaluate_receipt(sample)['status'],'FAILED')
if __name__=='__main__':unittest.main()
