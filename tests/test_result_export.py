"""Tests for Result and ResultItem export methods."""

import csv
import io
import json
import pytest
from parawave.result import Result, ResultItem


@pytest.fixture
def sample_result():
    items = [
        ResultItem(index=0, input={"x": 1}, output={"y": 2}, status="completed", error=None, attempts=1, elapsed=0.5),
        ResultItem(index=1, input={"x": 2}, output=None, status="failed", error="timeout", attempts=3, elapsed=1.2),
        ResultItem(index=2, input={"x": 3}, output="hello", status="completed", error=None, attempts=1, elapsed=0.3),
    ]
    return Result(items=items, run_id="test-run-123", elapsed=2.0, tags={"env": "test"})


class TestResultItemToJson:
    def test_returns_valid_json(self, sample_result):
        item = sample_result[0]
        j = item.to_json()
        parsed = json.loads(j)
        assert parsed["index"] == 0
        assert parsed["ok"] is True

    def test_indent_parameter(self, sample_result):
        item = sample_result[0]
        j = item.to_json(indent=2)
        assert "\n" in j


class TestResultToJson:
    def test_returns_valid_json(self, sample_result):
        j = sample_result.to_json()
        parsed = json.loads(j)
        assert parsed["run_id"] == "test-run-123"
        assert len(parsed["items"]) == 3

    def test_indent_parameter(self, sample_result):
        j = sample_result.to_json(indent=2)
        assert "\n" in j


class TestResultToCsv:
    def test_returns_csv_string(self, sample_result):
        csv_str = sample_result.to_csv()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0]["index"] == "0"
        assert rows[0]["status"] == "completed"
        assert rows[0]["ok"] == "True"

    def test_writes_to_file(self, sample_result, tmp_path):
        path = tmp_path / "results.csv"
        returned = sample_result.to_csv(path=str(path))
        assert returned == str(path)
        assert path.exists()
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3

    def test_columns_present(self, sample_result):
        csv_str = sample_result.to_csv()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        expected_cols = {"index", "status", "input", "output", "error", "attempts", "elapsed", "ok"}
        assert set(rows[0].keys()) == expected_cols

    def test_non_serializable_output_uses_str(self, sample_result):
        csv_str = sample_result.to_csv()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert "y" in rows[0]["output"]

    def test_empty_result(self):
        result = Result(items=[], run_id="empty", elapsed=0.0)
        csv_str = result.to_csv()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 0
