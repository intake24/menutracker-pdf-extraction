import pytest


@pytest.fixture(autouse=True)
def no_model_calls(monkeypatch):
    """Tests are offline: anything that would reach a real backend (`claude -p` or the Anthropic API) fails instead of spending money or quota."""
    from pipeline import llm
    from pipeline.parsers import vision_pairs, vision_products, vision_table

    def refuse(*_, **__):
        raise AssertionError("a test tried to call the real model; patch the parser's RUNNER")
    for module in (vision_table, vision_products, vision_pairs):
        monkeypatch.setattr(module, "RUNNER", refuse)
    monkeypatch.setattr(llm, "claude_runner", refuse)
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", refuse)     # sdk_runner builds its client from this; tests pass a fake client instead
