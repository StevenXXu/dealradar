# tests/test_summarizer.py
from src.reasoner.summarizer import Summarizer, truncate_to_p_tags

def test_truncate_to_p_tags():
    html = "<p>First</p><p>Second</p><p>Third</p><p>Fourth</p><p>Fifth</p>"
    result = truncate_to_p_tags(html, max_p_tags=3)
    # Function returns plain text (no <p> tags) - 3 paragraphs
    assert "First" in result
    assert "Second" in result
    assert "Third" in result
    assert "Fourth" not in result  # Only first 3

def test_truncate_to_p_tags_preserves_content():
    html = "<p>First para</p><p>Second para</p>"
    result = truncate_to_p_tags(html, max_p_tags=10)
    assert "First para" in result
    assert "Second para" in result

def test_summarizer_prompt_includes_requirements():
    summarizer = Summarizer()
    prompt = summarizer.build_prompt("Some long text about a company")
    assert "under 100 words" in prompt
    assert "one sentence" in prompt

def test_summarizer_returns_tuple():
    """summarize() should return (text, model_name) tuple."""
    from unittest.mock import MagicMock
    from src.reasoner.models import ModelResponse, ModelProvider
    summarizer = Summarizer()
    mock_response = ModelResponse(text="A design tool.", provider=ModelProvider.GEMINI, model_name="gemini-2.0-flash")
    mock_chain = MagicMock()
    mock_chain.complete.return_value = mock_response
    result = summarizer.summarize("Some text", mock_chain)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] == "A design tool."
    assert result[1] == "gemini-2.0-flash"
