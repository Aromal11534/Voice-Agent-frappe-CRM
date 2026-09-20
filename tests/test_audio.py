import audioop
import unittest

from app.voice.audio import StreamingResampler, chunk_audio


class AudioTests(unittest.TestCase):
    def test_mulaw_chunks_are_silence_padded(self):
        chunks = chunk_audio(b"\x11" * 330, chunk_size=320)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[1]), 320)
        self.assertEqual(chunks[1][10:], b"\xff" * 310)

    def test_streaming_resampler_preserves_state(self):
        first = b"\x01\x00" * 80
        second = b"\x02\x00" * 80
        expected, _ = audioop.ratecv(first + second, 2, 1, 8000, 16000, None)
        resampler = StreamingResampler()
        actual = resampler.process(first) + resampler.process(second)
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
