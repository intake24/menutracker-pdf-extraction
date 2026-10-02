import pytest


@pytest.fixture(autouse=True)
def no_model_calls(monkeypatch):
    """Tests are offline: anything that would reach the real `claude` fails instead of spending quota."""
    from pipeline.parsers import vision_table

    def refuse(*_):
        raise AssertionError("a test tried to call the real model; patch vision_table.RUNNER")
    monkeypatch.setattr(vision_table, "RUNNER", refuse)
