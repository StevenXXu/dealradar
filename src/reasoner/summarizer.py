# src/reasoner/summarizer.py
"""Semantic compression: summarize company text to <100 word one-liner."""
from bs4 import BeautifulSoup


def truncate_to_p_tags(html: str, max_p_tags: int = 20) -> str:
    """
    Truncate HTML to the first max_p_tags <p> tags.
    Token control strategy — deterministic, simple.
    """
    soup = BeautifulSoup(html, "lxml")
    p_tags = soup.find_all("p")[:max_p_tags]
    texts = []
    for p in p_tags:
        text = p.get_text(strip=True)
        if text:
            texts.append(text)
    return "\n\n".join(texts)


class Summarizer:
    """Build prompts for semantic compression of company text."""

    SYSTEM_PROMPT = """You are a senior venture analyst. Summarize the company below in exactly ONE sentence (under 100 words).
Focus on: What do they do? Who are their customers? How do they make money?
Return ONLY the summary sentence — no labels, no bullet points."""

    def __init__(self, model_chain=None):
        self.model_chain = model_chain

    def build_prompt(self, text: str) -> str:
        truncated = truncate_to_p_tags(text, max_p_tags=20)
        return f"Summarize this company in one sentence (under 100 words):\n\n{truncated}"

    def summarize(self, text: str, model_chain) -> tuple[str, str]:
        """Call AI to produce a <100 word one-liner. Returns (text, model_name)."""
        prompt = self.build_prompt(text)
        response = model_chain.complete(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            max_tokens=200,
        )
        return response.text.strip(), response.model_name
