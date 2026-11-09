import unittest
from validators import enforce_exact_word_count, finalize_response_text, WordCountValidator
from intelligence import resolve_deterministic_task


class F01F03RegressionTests(unittest.TestCase):
    """Regression suite verifying corrections for Astra findings F01, F02, and F03."""

    def test_f01_no_fabricated_dates_in_word_count(self):
        """F01: Under-count responses must NEVER be padded with fabricated dates like 'today'."""
        text = "The deployment failed."
        result = enforce_exact_word_count(text, 4)
        self.assertNotIn("today", result.lower())
        self.assertNotIn("every day", result.lower())
        self.assertEqual(result, "The deployment failed.")

    def test_f01_preserve_boolean_truth(self):
        """F01: Over-count responses must NEVER delete boolean literals or predicates."""
        text = "The function returns False."
        result = enforce_exact_word_count(text, 3)
        self.assertIn("False", result)
        self.assertEqual(result, "The function returns False.")

    def test_f01_preserve_frequency_qualification(self):
        """F01: Over-count responses must NEVER strip frequency/modality qualifiers."""
        text = "This often fails."
        result = enforce_exact_word_count(text, 2)
        self.assertIn("often", result)
        self.assertEqual(result, "This often fails.")

    def test_f01_preserve_negation_and_predicates(self):
        """F01: Over-count responses must NEVER strip negation or predicate adjectives."""
        text = "The system is not safe."
        result = enforce_exact_word_count(text, 3)
        self.assertIn("safe", result)
        self.assertTrue("not" in result or "n't" in result)

    def test_f01_internal_dispensable_modifier_pruning(self):
        """F01: Non-essential dispensable modifiers can be trimmed while preserving sentence-final words."""
        cand = "Software testing finds bugs early, improves reliability, reduces overall development costs, and prevents failures."
        result = enforce_exact_word_count(cand, 12, required_words=["bugs"], forbidden_words=["perfect"])
        self.assertEqual(len(WordCountValidator.count_words(result)), 12)
        self.assertIn("bugs", result.lower())
        self.assertNotIn("perfect", result.lower())
        self.assertTrue(result.endswith("prevents failures."))

    def test_f02_no_unmeasured_word_count_label(self):
        """F02: finalize_response_text must NOT append a WORD COUNT label unless actual content matches."""
        # 2 words text with required_output_fields: ['WORD COUNT: 8']
        text = "Result unknown."
        result = finalize_response_text(
            text,
            {"constraints": {"word_count_exact": 8, "required_output_fields": ["WORD COUNT: 8"]}},
        )
        self.assertNotIn("WORD COUNT", result)
        self.assertEqual(result, "Result unknown.")

    def test_f02_truthful_word_count_label_accepted(self):
        """F02: When measured word count matches required field, the label is appended truthfully."""
        text = "One two three four five six seven eight."
        result = finalize_response_text(
            text,
            {"constraints": {"word_count_exact": 8, "required_output_fields": ["WORD COUNT: 8"]}},
        )
        self.assertIn("WORD COUNT: 8", result)

    def test_f03_explanation_prompts_not_hijacked_by_status_shortcut(self):
        """F03: Conceptual/explanatory questions must return None from resolve_deterministic_task."""
        prompts = [
            "Explain what output mode means.",
            "What do the status fields mean?",
            "Explain why the last PDF created was empty.",
            "Explain how bridges support weight.",
        ]
        for prompt in prompts:
            out = resolve_deterministic_task({"text": prompt, "route_target": "CHAT"})
            self.assertIsNone(out, f"Prompt '{prompt}' should not be intercepted by deterministic shortcut")

    def test_f03_status_command_still_resolved_deterministically(self):
        """F03: Deterministic task requests for status fields continue to succeed."""
        task_def = {
            "id": 10,
            "text": "10. Output mode and file creation status: verify that no PDF or artifact was created and output mode is chat.",
            "route_target": "CHAT",
        }
        resolved = resolve_deterministic_task(task_def)
        self.assertIsNotNone(resolved)
        self.assertIn("OUTPUT MODE: CHAT", resolved["answer"])
        self.assertIn("PDF CREATED: NO", resolved["answer"])
        self.assertIn("ARTIFACT CREATED: NO", resolved["answer"])


if __name__ == "__main__":
    unittest.main()
