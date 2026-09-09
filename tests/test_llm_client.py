from unittest.mock import patch

from llm_client import answer_question


def test_answer_question_passes_context_and_model_to_gemini() -> None:
    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("llm_client.genai") as genai:
            client_class = genai.Client
            client_class.return_value.models.generate_content.return_value.text = "answer"

            result = answer_question("What?", ["context"], model="test-model")

    assert result == "answer"
    call = client_class.return_value.models.generate_content.call_args
    assert call.kwargs["model"] == "test-model"
    assert "context" in call.kwargs["contents"]


def test_answer_question_requires_api_key() -> None:
    with patch.dict("os.environ", {}, clear=True):
        try:
            answer_question("What?", [])
        except RuntimeError as exc:
            assert "GOOGLE_API_KEY" in str(exc)
        else:
            raise AssertionError("Expected a missing API key error")