import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app


class StudioOptionsTests(unittest.TestCase):
    def test_valid_seed_and_negative_become_flux_overrides(self):
        self.assertEqual(app.studio_overrides({'seed': 1234, 'negative': '  blurry,   text  '}),
                         {'flux_seed': 1234, 'flux_negative_prompt': 'blurry, text'})

    def test_bad_or_missing_values_are_dropped(self):
        for options in ({}, {'seed': None}, {'seed': ''}, {'seed': 'abc'}, {'seed': -5}, {'seed': 2**31}, None, 'x'):
            self.assertNotIn('flux_seed', app.studio_overrides(options))
        self.assertEqual(app.studio_overrides({'seed': '0'}), {'flux_seed': 0})
        self.assertEqual(len(app.studio_overrides({'negative': 'x' * 900})['flux_negative_prompt']), 600)

    def test_negative_prompt_only_reaches_the_cli_with_real_cfg(self):
        src = open(app.__file__, encoding='utf-8').read()
        self.assertIn("if negative and scale>1 and self.action!='edit_image':command.extend(['-n',negative])", src)
        # Studio overrides are one-shot: every send consumes and clears them.
        self.assertIn("self.variation_overrides=dict(getattr(self,'studio_overrides',None) or {});self.studio_overrides=None", src)


if __name__ == '__main__':
    unittest.main()
