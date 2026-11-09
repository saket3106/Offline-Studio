"""Actual desktop dispatch with synthetic collaborators; no DB or native inference."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app import App

class StopAtBoundary(Exception):pass

class MemoryDispatchTests(unittest.TestCase):
    answer=staticmethod(App.answer)
    def app(self,text):
        recall=Mock();recall.enabled.return_value=True
        store=Mock(recall=recall);store.get_chat_model.return_value='fixture-model'
        store.messages.return_value=[('user','A normal turn',0,{}),('assistant','A normal reply',0,{})]*9+[('user',text,0,{})]
        memory=Mock();memory.context_fast.side_effect=StopAtBoundary('ordinary prompt assembly')
        return SimpleNamespace(store=store,memory=memory,current='synthetic-chat',model='fixture-model',
                               emit_frontend=Mock(),bubble=Mock())
    def test_long_chat_general_question_does_not_start_history_worker(self):
        text='What is TCP?'; app=self.app(text)
        with patch('app.QThread',side_effect=StopAtBoundary('history worker')) as thread:
            with self.assertRaisesRegex(StopAtBoundary,'ordinary prompt assembly'):self.answer(app,text)
        thread.assert_not_called();app.memory.context_fast.assert_called_once_with(text)
    def test_explicit_history_still_uses_evidence_preparation(self):
        text='Search previous conversations for the launch date.'; app=self.app(text)
        with patch('app.QThread',side_effect=StopAtBoundary('history worker')) as thread:
            with self.assertRaisesRegex(StopAtBoundary,'history worker'):self.answer(app,text)
        thread.assert_called_once();app.memory.context_fast.assert_not_called()
    def test_provenance_followup_revalidates_previous_sources(self):
        text='Which of those was faster?'; app=self.app(text)
        app.store.messages.return_value[-2]=('assistant','The earlier results.',0,{'memory_sources':[{'messageId':7,'id':'M7','excerpt':'Synthetic source.'}]})
        with patch('app.QThread',side_effect=StopAtBoundary('history worker')) as thread:
            with self.assertRaisesRegex(StopAtBoundary,'history worker'):self.answer(app,text)
        thread.assert_called_once()

if __name__=='__main__':unittest.main()
