# tests/test_models.py
from src.reasoner.models import ModelChain, ModelProvider

def test_model_chain_initialization():
    import os
    os.environ["GEMINI_API_KEY"] = "test"
    chain = ModelChain()
    assert len(chain.providers) >= 1
    assert chain.providers[0].name == "GEMINI"  # Enum member name is uppercase

def test_model_provider_enum():
    assert ModelProvider.GEMINI.value == "gemini"
    assert ModelProvider.KIMI.value == "kimi"
    assert ModelProvider.OPENAI.value == "openai"
