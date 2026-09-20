import unittest
from unittest.mock import AsyncMock, patch

from app.models.schemas import CallSession
from app.voice.browser_pipeline import _get_llm_response
from app.voice.prompts import MALAYALAM_TURN_INSTRUCTION


class VoiceLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_malayalam_call_adds_a_language_instruction(self):
        session = CallSession(
            detected_language="ml-IN",
            conversation_history=[
                {"role": "system", "content": "Sales agent"},
                {"role": "user", "content": "എനിക്കൊരു website വേണം"},
            ],
        )

        with patch(
            "app.voice.browser_pipeline.chat_completion",
            new=AsyncMock(return_value="തീർച്ചയായും."),
        ) as completion:
            response = await _get_llm_response(session)

        messages = completion.await_args.args[0]
        self.assertEqual(response, "തീർച്ചയായും.")
        self.assertEqual(messages[1]["role"], "system")
        self.assertEqual(messages[1]["content"], MALAYALAM_TURN_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
