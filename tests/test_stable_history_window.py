"""The history sent with a message keeps its first message for several turns so the local server's prompt cache
is reused (turn_trace 2026-11-11: 18 of 128 turns reused it; first token median 1.4 s)."""
import unittest
from pathlib import Path

from memory_manager import stable_history_window, token_stable_history_window

SOURCE = Path(__file__).resolve().parents[1]


def chat(n):
    return [('user' if i % 2 == 0 else 'assistant', f'm{i}') for i in range(n)]


class StableHistoryWindowTests(unittest.TestCase):
    def test_short_chats_send_everything(self):
        for n in range(0, 14):
            self.assertEqual(stable_history_window(chat(n)), chat(n))

    def test_long_chats_keep_between_8_and_13_recent_messages(self):
        for n in range(14, 200):
            window = stable_history_window(chat(n))
            self.assertTrue(8 <= len(window) <= 13, (n, len(window)))
            self.assertEqual(window, chat(n)[-len(window):])  # always the newest messages, none skipped
            self.assertEqual(window[0][0], 'user')  # starts on the same role as the full chat

    def test_start_stays_put_for_three_turns_in_a_row(self):
        starts = [stable_history_window(chat(n))[0] for n in range(14, 200, 2)]  # one turn = user + assistant
        runs, run = [], 1
        for a, b in zip(starts, starts[1:]):
            if a == b:
                run += 1
            else:
                runs.append(run); run = 1
        self.assertEqual(set(runs), {3})
        # The old "last 10 messages" window changed its first message on every turn.
        old = [chat(n)[-10:][0] for n in range(14, 200, 2)]
        self.assertEqual(len(set(old)), len(old))

    def test_chat_prompt_uses_the_token_window(self):
        text = (SOURCE / 'app.py').read_text(encoding='utf-8')
        self.assertIn("selected_rows=[] if compact else token_stable_history_window(rows[:-1],context_limit//2,", text)


def sized_chat(sizes):
    return [('user' if i % 2 == 0 else 'assistant', 'x' * size) for i, size in enumerate(sizes)]


class TokenHistoryWindowTests(unittest.TestCase):
    count = staticmethod(lambda row: len(row[1]))

    def windows(self, rows, budget=1000):
        return [token_stable_history_window(rows[:n], budget, self.count) for n in range(2, len(rows) + 1, 2)]

    def test_short_chats_send_everything(self):
        rows = sized_chat([50] * 12)
        self.assertEqual(token_stable_history_window(rows, 1000, self.count), rows)

    def test_trims_rarely_in_large_jumps_and_stays_within_budget(self):
        rows = sized_chat([40, 160] * 60)  # 60 turns of 200 "tokens"
        windows = self.windows(rows)
        starts = [len(rows[:2 * (k + 1)]) - len(w) for k, w in enumerate(windows)]
        moves = sum(a != b for a, b in zip(starts, starts[1:]))
        self.assertLessEqual(moves, 60 // 3)  # the count window moved every 3 turns
        for w in windows:
            self.assertLessEqual(sum(map(self.count, w)), 1000)
            self.assertEqual(w[0][0], 'user')

    def test_same_history_gives_the_same_start_every_turn(self):
        rows = sized_chat([30, 300, 20, 500, 10, 90] * 10)
        for n in range(2, len(rows), 2):
            w1 = token_stable_history_window(rows[:n], 900, self.count)
            w2 = token_stable_history_window(rows[:n + 2], 900, self.count)
            if len(w2) == len(w1) + 2:
                self.assertEqual(w1, w2[:len(w1)])

    def test_one_huge_message_keeps_only_the_newest(self):
        rows = sized_chat([10, 10, 10, 5000])
        self.assertEqual(token_stable_history_window(rows, 1000, self.count), rows[-1:])


if __name__ == '__main__':
    unittest.main()
