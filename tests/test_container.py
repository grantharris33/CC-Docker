"""Container management tests for CC-Docker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateway"))

from app.models.container import ContainerStatus
from app.services.container import ContainerManager


class TestContainerManager:
    """Tests for ContainerManager."""

    @pytest.fixture
    def container_manager(self):
        """Create a ContainerManager instance."""
        return ContainerManager()

    def test_parse_memory_gigabytes(self, container_manager):
        """Test memory parsing for gigabytes."""
        assert container_manager._parse_memory("4g") == 4 * 1024**3
        assert container_manager._parse_memory("2G") == 2 * 1024**3

    def test_parse_memory_megabytes(self, container_manager):
        """Test memory parsing for megabytes."""
        assert container_manager._parse_memory("512m") == 512 * 1024**2
        assert container_manager._parse_memory("1024M") == 1024 * 1024**2

    def test_parse_memory_kilobytes(self, container_manager):
        """Test memory parsing for kilobytes."""
        assert container_manager._parse_memory("1024k") == 1024 * 1024

    def test_parse_memory_bytes(self, container_manager):
        """Test memory parsing for plain bytes."""
        assert container_manager._parse_memory("1048576") == 1048576


class TestStreamParser:
    """Tests for stream parser."""

    @pytest.fixture
    def parser(self):
        """Create a StreamParser instance."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "wrapper"))
        from stream_parser import StreamParser
        return StreamParser()

    def test_parse_single_json(self, parser):
        """Test parsing a single JSON object."""
        data = '{"type": "assistant", "message": "hello"}'
        results = parser.feed(data)
        assert len(results) == 1
        assert results[0]["type"] == "assistant"

    def test_parse_multiple_json(self, parser):
        """Test parsing multiple JSON objects."""
        data = '{"type": "a"}{"type": "b"}{"type": "c"}'
        results = parser.feed(data)
        assert len(results) == 3
        assert [r["type"] for r in results] == ["a", "b", "c"]

    def test_parse_partial_json(self, parser):
        """Test parsing partial JSON across multiple feeds."""
        results1 = parser.feed('{"type": "test"')
        assert len(results1) == 0

        results2 = parser.feed(', "value": 123}')
        assert len(results2) == 1
        assert results2[0]["type"] == "test"
        assert results2[0]["value"] == 123

    def test_parse_nested_json(self, parser):
        """Test parsing nested JSON."""
        data = '{"outer": {"inner": {"deep": true}}}'
        results = parser.feed(data)
        assert len(results) == 1
        assert results[0]["outer"]["inner"]["deep"] is True

    def test_parse_with_noise(self, parser):
        """Test parsing with noise before JSON."""
        data = 'some noise {"type": "valid"} more noise'
        results = parser.feed(data)
        assert len(results) == 1
        assert results[0]["type"] == "valid"

    def test_reset(self, parser):
        """Test parser reset."""
        parser.feed('{"incomplete":')
        parser.reset()
        assert parser.buffer == ""
        assert parser.brace_count == 0


class TestFormatForClient:
    """Tests for message formatting."""

    @pytest.fixture
    def format_fn(self):
        """Get format_for_client function."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "wrapper"))
        from stream_parser import format_for_client
        return format_for_client

    def test_format_assistant_message(self, format_fn):
        """Test formatting assistant message."""
        msg = {"type": "assistant", "message": {"text": "Hello"}}
        result = format_fn(msg)
        assert result["type"] == "assistant"
        assert result["message"]["text"] == "Hello"

    def test_format_tool_use(self, format_fn):
        """Test formatting tool use message."""
        msg = {"type": "tool_use", "tool": "Read", "input": {"path": "/test"}}
        result = format_fn(msg)
        assert result["type"] == "tool_use"
        assert result["tool"] == "Read"

    def test_format_result(self, format_fn):
        """Test formatting result message."""
        msg = {
            "type": "result",
            "subtype": "success",
            "result": "Done",
            "total_cost_usd": 0.01,
        }
        result = format_fn(msg)
        assert result["type"] == "result"
        assert result["subtype"] == "success"
        assert result["total_cost_usd"] == 0.01
