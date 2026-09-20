import json
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.exotel import build_media_message, parse_exotel_event
from app.integrations.sarvam import (
    chat_completion,
    connect_stt_stream,
    parse_stt_message,
    text_to_speech,
)


class ExotelTests(unittest.TestCase):
    def test_start_event_is_parsed(self):
        event = parse_exotel_event(json.dumps({
            "event": "start",
            "streamSid": "stream-1",
            "start": {"callSid": "call-1", "streamSid": "stream-1", "from": "+919876543210"},
        }))
        self.assertEqual(event.start.call_sid, "call-1")
        self.assertEqual(event.start.from_number, "+919876543210")

    def test_media_message_shape(self):
        message = json.loads(build_media_message("YWJj", "stream-1"))
        self.assertEqual(message["media"]["payload"], "YWJj")
        self.assertEqual(message["streamSid"], "stream-1")


class SarvamTests(unittest.IsolatedAsyncioTestCase):
    def test_current_realtime_transcript_shape_is_parsed(self):
        event, text, data = parse_stt_message(json.dumps({
            "event": "transcript.final",
            "text": "Namaste",
            "language": "hi-IN",
        }))

        self.assertEqual(event, "transcript.final")
        self.assertEqual(text, "Namaste")
        self.assertEqual(data["language"], "hi-IN")

    async def test_realtime_stt_preserves_the_spoken_language(self):
        connection = MagicMock()
        with patch(
            "app.integrations.sarvam.websockets.connect",
            new=AsyncMock(return_value=connection),
        ) as connect:
            result = await connect_stt_stream("auto")

        query = parse_qs(urlparse(connect.await_args.args[0]).query)
        self.assertIs(result, connection)
        self.assertEqual(query["language_code"], ["auto"])
        self.assertEqual(query["mode"], ["codemix"])
        self.assertEqual(query["stream_type"], ["balanced"])
        self.assertEqual(query["encoding"], ["linear16"])
        self.assertEqual(query["sample_rate"], ["16000"])

    async def test_chat_uses_sarvam_key_and_conversation_model(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "  Hello from Sarvam  "}}]
        }
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch("app.integrations.sarvam.httpx.AsyncClient", return_value=context):
            content = await chat_completion(
                [{"role": "user", "content": "Hello"}], max_tokens=20
            )

        request = client.post.await_args
        self.assertEqual(content, "Hello from Sarvam")
        self.assertIn("api-subscription-key", request.kwargs["headers"])
        self.assertEqual(request.kwargs["json"]["model"], "sarvam-105b-conversations")

    async def test_tts_uses_current_request_contract(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"audios": ["YWJj"]}
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch("app.integrations.sarvam.httpx.AsyncClient", return_value=context):
            audio = await text_to_speech("Hello", "en-IN")

        payload = client.post.await_args.kwargs["json"]
        self.assertEqual(audio, b"abc")
        self.assertEqual(payload["text"], "Hello")
        self.assertEqual(payload["language_code"], "en-IN")
        self.assertEqual(payload["output_audio_codec"], "mulaw")
        self.assertEqual(payload["speech_sample_rate"], 8000)
        self.assertNotIn("inputs", payload)


if __name__ == "__main__":
    unittest.main()
