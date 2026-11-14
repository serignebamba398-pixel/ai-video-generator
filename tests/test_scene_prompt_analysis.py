import unittest
from src.scene_prompt_analysis import analyze_scene_prompt


class PromptAnalysisTests(unittest.TestCase):
    def test_raw_prompt_and_speech_preserved(self):
        raw = 'Marcel se tient le dos.\nMarcel dit :\n« Chef… mon dos ! »\nVictor reste silencieux.'
        result = analyze_scene_prompt(raw)
        self.assertEqual(result.raw_prompt, raw)
        self.assertEqual([(t.speaker, t.dialogue) for t in result.turns], [('Marcel', 'Chef… mon dos !')])

    def test_two_speakers(self):
        result = analyze_scene_prompt('Marcel dit : « Terminé. »\nVictor répond : « Très bien. »')
        self.assertEqual([t.speaker for t in result.turns], ['Marcel', 'Victor'])

    def test_silent_and_ambiguous(self):
        self.assertEqual(analyze_scene_prompt('Il marche en silence.').turns, ())
        result = analyze_scene_prompt('Une affiche indique « Bonjour ».')
        self.assertFalse(result.turns)
        self.assertTrue(result.uncertain)
        self.assertTrue(analyze_scene_prompt('Marcel dit : Bonjour').uncertain)

    def test_label_and_straight_quotes(self):
        result = analyze_scene_prompt('Victor :\n"Très bien."')
        self.assertEqual(result.turns[0].speaker, 'Victor')
        self.assertEqual(result.turns[0].dialogue, 'Très bien.')
