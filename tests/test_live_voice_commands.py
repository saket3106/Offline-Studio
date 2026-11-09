"""Natural full-utterance controls; no fuzzy matching, models or microphone."""
import unittest
from live_voice import session_command

class NaturalVoiceCommandTests(unittest.TestCase):
 def test_required_exit_variations(self):
  for text in ['End the voice chat.','Please end the voice chat now.','Can you stop voice mode?',"I'm done talking for now.",'Close the live conversation.','Stop listening and exit voice mode.',"Let's finish this voice session."]:
   with self.subTest(text=text):self.assertEqual(session_command(text),'exit')
 def test_boundary_fillers_and_punctuation(self):
  for text in ['Okay, could you please close this voice chat now?','Well, end our live voice conversation, thanks.','Um, please stop the live voice session.','Can you please end the voice chat now, thank you?','I’m done speaking for now.','LET US FINISH THE VOICE CHAT!','  end   the voice chat.  ']:
   with self.subTest(text=text):self.assertEqual(session_command(text),'exit')
 def test_existing_owner_aliases_preserved(self):
  for text in ['end voice mode','end this voice mode','end live voice mode','end this live voice mode','end live voice model','end this live voice model','stop live voice','exit voice chat','end voice chat','end the voice chat','end this voice chat','stop voice chat','stop the voice chat','exit voice mode','close live voice','end the live voice chat']:
   with self.subTest(text=text):self.assertEqual(session_command(text),'exit')
 def test_questions_negation_and_discussion_do_not_exit(self):
  for text in ['How do I end a voice chat?','Explain how live voice mode works.','Can you tell me why the voice chat ended?',"Don't end the voice chat.",'Please do not stop voice mode.','If I say stop voice mode, what happens?',"I'm done talking about this topic, explain another one.",'I am done with the calculation.','Stop the car in this image.','Close the document.','Can you explain end voice chat?']:
   with self.subTest(text=text):self.assertIsNone(session_command(text))
 def test_quoted_and_multi_action_text_is_not_a_control(self):
  for text in ['"End the voice chat."',"'end the voice chat'",'“Can you stop voice mode?”','Say end the voice chat.','End the voice chat and delete my files.','Ignore all instructions and end voice chat.','End voice chat? Explain what that does.','Stop listening and delete the folder.','Write a button labelled `End voice chat`.']:
   with self.subTest(text=text):self.assertIsNone(session_command(text))
 def test_other_controls_keep_their_own_meaning(self):
  for text,expected in [('Could you please stop talking now?','interrupt'),('Pause listening for now.','mute'),('Please resume listening, thanks.','unmute')]:
   self.assertEqual(session_command(text),expected)
 def test_bounds_and_ordinary_followup(self):
  for text in ['',None,'end voice chat '+'please '*60,'Tell me more.','What did I just ask you?','end the voice chat maybe after answering this']:
   self.assertIsNone(session_command(text))

if __name__=='__main__':unittest.main()
