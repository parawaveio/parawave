"""Tests for input/signature validation."""

import json

import pytest

from parawave.errors import ValidationError
from parawave.validation import validate_input_serializability, validate_inputs


class TestValidateInputs:
    def test_valid_inputs(self):
        def process(city: str, model: str = "gpt-4"):
            pass
        data = [{"city": "NYC"}, {"city": "LA"}]
        validated = validate_inputs(process, data, {})
        assert validated == data

    def test_broadcast_merge(self):
        def process(city: str, model: str):
            pass
        data = [{"city": "NYC"}, {"city": "LA"}]
        validated = validate_inputs(process, data, {"model": "gpt-4"})
        assert validated == [
            {"city": "NYC", "model": "gpt-4"},
            {"city": "LA", "model": "gpt-4"},
        ]

    def test_broadcast_item_wins(self):
        def process(city: str, model: str):
            pass
        data = [{"city": "NYC", "model": "gpt-3.5"}]
        validated = validate_inputs(process, data, {"model": "gpt-4"})
        assert validated[0]["model"] == "gpt-3.5"

    def test_missing_required_arg_raises(self):
        def process(city: str, model: str):
            pass
        data = [{"city": "NYC"}]
        with pytest.raises(ValidationError, match="model"):
            validate_inputs(process, data, {})

    def test_extra_key_without_kwargs_raises(self):
        def process(city: str):
            pass
        data = [{"city": "NYC", "extra": "bad"}]
        with pytest.raises(ValidationError, match="extra"):
            validate_inputs(process, data, {})

    def test_extra_key_with_kwargs_passes(self):
        def process(city: str, **kwargs):
            pass
        data = [{"city": "NYC", "extra": "fine"}]
        validated = validate_inputs(process, data, {})
        assert validated == data

    def test_empty_data_raises(self):
        def process(city: str):
            pass
        with pytest.raises(ValidationError, match="empty"):
            validate_inputs(process, [], {})

    def test_non_dict_in_data_raises(self):
        def process(city: str):
            pass
        with pytest.raises(ValidationError, match="dict"):
            validate_inputs(process, ["NYC", "LA"], {})

    def test_function_with_defaults(self):
        def process(city: str, model: str = "gpt-4", temp: float = 0.7):
            pass
        data = [{"city": "NYC"}]
        validated = validate_inputs(process, data, {})
        assert validated == data

    def test_items_with_different_keys(self):
        def process(city: str = "default", model: str = "gpt-4"):
            pass
        data = [{"city": "NYC"}, {"model": "gpt-3.5"}]
        validated = validate_inputs(process, data, {})
        assert len(validated) == 2


class TestValidateInputSerializability:
    def test_valid_inputs_pass(self):
        items = [{"city": "NYC", "count": 5, "active": True, "tags": ["a", "b"]}]
        validate_input_serializability(items)  # should not raise

    def test_bytes_value_raises(self):
        items = [{"data": b"binary content"}]
        with pytest.raises(ValidationError, match="index 0"):
            validate_input_serializability(items)

    def test_custom_object_raises(self):
        class Custom:
            pass
        items = [{"obj": Custom()}]
        with pytest.raises(ValidationError, match="index 0"):
            validate_input_serializability(items)

    def test_error_includes_key_name(self):
        items = [{"name": "ok", "image": b"png bytes"}]
        with pytest.raises(ValidationError, match="image"):
            validate_input_serializability(items)

    def test_error_includes_type_name(self):
        items = [{"data": b"bytes"}]
        with pytest.raises(ValidationError, match="bytes"):
            validate_input_serializability(items)

    def test_nested_non_serializable_raises(self):
        items = [{"nested": {"deep": b"binary"}}]
        with pytest.raises(ValidationError, match="index 0"):
            validate_input_serializability(items)

    def test_fails_on_first_bad_item(self):
        items = [{"ok": "fine"}, {"ok": "fine"}, {"bad": b"bytes"}]
        with pytest.raises(ValidationError, match="index 2"):
            validate_input_serializability(items)

    def test_empty_list_passes(self):
        validate_input_serializability([])  # should not raise

    def test_none_values_pass(self):
        items = [{"value": None}]
        validate_input_serializability(items)  # should not raise

    def test_circular_reference_raises(self):
        d = {}
        d["self"] = d
        with pytest.raises(ValidationError, match="index 0"):
            validate_input_serializability([d])
