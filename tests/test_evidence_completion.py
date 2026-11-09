import unittest
from research_evidence import check_support,preceding_claim,source_conflicts
class EvidenceTests(unittest.TestCase):
 def test_unsupported_numbers_are_not_verified_by_membership(self):
  source={'id':'K0123456789abcdef','excerpt':'The engine displacement is 349 cc and the power is 20 bhp.'}
  self.assertTrue(check_support('The displacement is 900 cc.',source)['requiresReview'])
  self.assertFalse(check_support('The engine displacement is 349 cc.',source)['requiresReview'])
 def test_exact_quote_and_false_quote(self):
  s={'id':'K1','excerpt':'The calibration interval is seventeen days.'}
  self.assertEqual('DIRECT_QUOTE_MATCH',check_support('It states "calibration interval is seventeen days".',s)['supportStatus'])
  self.assertTrue(check_support('It states "calibration interval is one year".',s)['requiresReview'])
 def test_near_claim_and_negation(self):
  self.assertEqual('The engine is 349 cc.',preceding_claim('Unrelated sentence. The engine is 349 cc. ',99))
  self.assertTrue(check_support('The engine is not fuel injected.',{'id':'K1','excerpt':'The engine is fuel injected.'})['requiresReview'])
 def test_conflicts_are_flagged_without_resolving_truth(self):
  c=source_conflicts([{'id':'K1','excerpt':'Engine 349 cc.'},{'id':'K2','excerpt':'Engine 346 cc.'}]);self.assertEqual(1,len(c));self.assertIn('POTENTIAL',c[0]['status'])
 def test_discovery_query_keeps_literal_product_identity(self):
  from intelligence_engine import compact_query
  self.assertEqual('Royal Enfield Hunter 350',compact_query('Research Royal Enfield Hunter 350 and cite the source in one sentence.'))
