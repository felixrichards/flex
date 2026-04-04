from champs.common.json_payload import extract_json_payload


def test_extract_json_payload_from_fenced_block() -> None:
    content = """```json
{"a": 1, "b": "x"}
```"""
    parsed = extract_json_payload(content)
    assert parsed == {"a": 1, "b": "x"}


def test_extract_json_payload_invalid_returns_none() -> None:
    assert extract_json_payload("hello world") is None
    assert extract_json_payload("```json\n{bad}\n```") is None
