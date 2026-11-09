"""A wrong-family vision projector is replaced by the matching mmproj beside the model (measured 2026-11-09)."""
import tempfile, unittest
from pathlib import Path
import integrated_runtime as ir


def engine(conflicts):
    cls = next(v for v in vars(ir).values() if isinstance(v, type) and hasattr(v, '_matching_projector'))
    obj = cls.__new__(cls); obj.cfg = {}
    obj._vision_pair_review = lambda model, projector: {'conflict': 'wrong family' if projector.name in conflicts else '', 'error': ''}
    return obj


class ProjectorMatchTests(unittest.TestCase):
    def test_conflicting_projector_is_swapped_for_the_matching_one(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); model = d / 'Qwen3VL-8B-Instruct-Q4_K_M.gguf'
            for name in (model.name, 'mmproj-F16.gguf', 'mmproj-Qwen3VL-8B-Instruct-F16.gguf'): (d / name).write_bytes(b'gguf')
            e = engine({'mmproj-F16.gguf'})
            self.assertEqual(e._matching_projector(model, d / 'mmproj-F16.gguf').name, 'mmproj-Qwen3VL-8B-Instruct-F16.gguf')
            self.assertEqual(Path(e.cfg['vision_projector']).name, 'mmproj-Qwen3VL-8B-Instruct-F16.gguf')

    def test_matching_or_unresolvable_projector_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); model = d / 'm.gguf'; model.write_bytes(b'g'); good = d / 'mmproj-a.gguf'; good.write_bytes(b'g')
            self.assertEqual(engine(set())._matching_projector(model, good), good)
            e = engine({'mmproj-a.gguf'})
            self.assertEqual(e._matching_projector(model, good), good); self.assertEqual(e.cfg, {})


if __name__ == '__main__':
    unittest.main()
