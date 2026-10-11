from app import add_label, parse_record


def test_add_label() -> None:
    assert add_label("sample") == "label:sample"


def test_parse_record() -> None:
    assert parse_record("name: sample") == {"name": "name", "value": "sample"}
