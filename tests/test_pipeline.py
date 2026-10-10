import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from pipeline import fmt_time, parse_transcript, chunk_segments, _srt_time

class PipelineTests(unittest.TestCase):

    def test_fmt_time_minutes(self):
        self.assertEqual(fmt_time(65), "01:05")

    def test_fmt_time_hours(self):
        self.assertEqual(fmt_time(3661), "01:01:01")

    def test_fmt_time_zero(self):
        self.assertEqual(fmt_time(0), "00:00")

    def test_srt_time(self):
        self.assertEqual(_srt_time(0), "00:00:00,000")
        self.assertEqual(_srt_time(3661.5), "01:01:01,500")

    def test_parse_srt(self):
        raw = "1\n00:00:01,000 --> 00:00:03,000\nHello world.\n\n2\n00:00:03,000 --> 00:00:05,000\nNext line."
        x = parse_transcript(raw, "test.srt")
        self.assertEqual(len(x), 2)
        self.assertEqual(x[0]["start"], 1.0)
        self.assertEqual(x[1]["text"], "Next line.")

    def test_parse_vtt(self):
        raw = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello VTT."
        x = parse_transcript(raw, "test.vtt")
        self.assertEqual(len(x), 1)
        self.assertAlmostEqual(x[0]["start"], 1.0)

    def test_parse_txt(self):
        x = parse_transcript("Just plain text.", "test.txt")
        self.assertEqual(len(x), 1)
        self.assertEqual(x[0]["text"], "Just plain text.")

    def test_parse_json_segments(self):
        import json
        data = json.dumps({"segments": [{"start": 0, "end": 5, "text": "Hello"}]})
        x = parse_transcript(data, "test.json")
        self.assertEqual(len(x), 1)
        self.assertEqual(x[0]["text"], "Hello")

    def test_chunk_splits_correctly(self):
        # Two segments whose cumulative end span exceeds 300s → should split into 2 chunks
        segs = [
            {"start": 0,   "end": 310, "text": "a"},
            {"start": 310, "end": 420, "text": "b"},
        ]
        chunks = chunk_segments(segs, 300)
        self.assertEqual(len(chunks), 2)

    def test_chunk_no_split_when_short(self):
        segs = [
            {"start": 0,  "end": 100, "text": "a"},
            {"start": 100,"end": 200, "text": "b"},
        ]
        chunks = chunk_segments(segs, 300)
        self.assertEqual(len(chunks), 1)

    def test_chunk_empty(self):
        self.assertEqual(chunk_segments([], 300), [])

if __name__ == "__main__":
    unittest.main()
