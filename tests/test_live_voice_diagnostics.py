"""Bounded diagnostic retention and serialized snapshots, without audio."""
import threading
import unittest
from live_voice import LiveVoiceSession


class VoiceDiagnosticTests(unittest.TestCase):
    def test_long_session_retains_recent_bounded_evidence(self):
        session = LiveVoiceSession(lambda _: None, history_limit=32)
        session.start('authored')
        for i in range(10000): session.publish('thinking' if i % 2 else 'listening')
        self.assertEqual(len(session.timeline), 32)
        self.assertEqual(len(session.snapshot()['timeline']), 24)
        self.assertEqual(session.timeline[-1]['stage'], 'thinking')

    def test_turn_markers_are_also_bounded_and_snapshot_is_detached(self):
        session = LiveVoiceSession(lambda _: None, history_limit=8)
        session.start('authored'); session.tick(chat='authored', busy=False)
        turn = session.begin_capture(session.session_id, session.generation, 'authored', False, False)
        for i in range(1000): session.mark('authored-marker-' + str(i))
        self.assertEqual(len(session.turn_timelines[turn]), 8)
        self.assertEqual(session.snapshot()['turnTimeline'][-1]['stage'], 'authored-marker-999')
        snapshot = session.snapshot(); snapshot['timeline'][0]['stage'] = 'external mutation'
        self.assertNotEqual(session.timeline[0]['stage'], 'external mutation')

    def test_new_session_releases_old_turn_diagnostics(self):
        session = LiveVoiceSession(lambda _: None)
        session.start('old'); session.tick(chat='old', busy=False)
        session.begin_capture(session.session_id, session.generation, 'old', False, False)
        self.assertTrue(session.turn_timelines)
        session.close(); session.start('new')
        self.assertFalse(session.turn_timelines)
        self.assertEqual(len(session.timeline), 1)

    def test_concurrent_publish_and_snapshot_have_ordered_revisions(self):
        revisions = []; session = LiveVoiceSession(lambda event: revisions.append(event['revision']), history_limit=48)
        session.start('authored'); errors = []; gate = threading.Barrier(5)
        def run(worker):
            try:
                gate.wait()
                for i in range(400):
                    session.publish(f'worker-{worker}-state-{i % 2}')
                    self.assertLessEqual(len(session.snapshot()['timeline']), 24)
            except Exception as exc: errors.append(exc)
        workers = [threading.Thread(target=run, args=(i,)) for i in range(4)]
        for worker in workers: worker.start()
        gate.wait()
        for worker in workers: worker.join(4); self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(revisions, sorted(set(revisions)))
        self.assertEqual(len(session.timeline), 48)

    def test_emitter_can_reenter_snapshot(self):
        session = LiveVoiceSession(lambda _: session.snapshot())
        session.start('authored'); session.interrupt(); session.close()
        self.assertFalse(session.active)

    def test_invalid_configuration_fails_without_starting_session(self):
        for limit in [0, -1, 4097, True, 1.5, '32']:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                LiveVoiceSession(lambda _: None, history_limit=limit)


if __name__ == '__main__': unittest.main()
