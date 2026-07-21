"""Tests for API key masking utility."""

import os
import sys

import pytest

# Ensure backend directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.masking import mask_api_key


class TestMaskApiKey:
    """Unit tests for the mask_api_key function."""

    def test_empty_string_returns_empty(self):
        """Empty string input returns empty string."""
        assert mask_api_key("") == ""

    def test_single_char_returns_asterisk(self):
        """Single character is fully masked."""
        assert mask_api_key("a") == "*"

    def test_two_chars_masks_first(self):
        """Two character key masks first, shows last."""
        assert mask_api_key("ab") == "*b"

    def test_three_chars_masks_first_two(self):
        """Three character key masks first two, shows last."""
        assert mask_api_key("abc") == "**c"

    def test_four_chars_masks_first_three(self):
        """Four character key masks first three, shows last."""
        assert mask_api_key("abcd") == "***d"

    def test_five_chars_shows_last_four(self):
        """Five character key masks first, shows last four."""
        assert mask_api_key("abcde") == "*bcde"

    def test_standard_api_key(self):
        """Standard length API key shows only last 4 chars."""
        key = "sk-1234567890abcdef"
        result = mask_api_key(key)
        assert result.endswith("cdef")
        assert result == "*" * (len(key) - 4) + "cdef"

    def test_long_key_preserves_length(self):
        """Masked result has the same length as the original key."""
        key = "sk-very-long-api-key-that-is-realistic-abc123"
        result = mask_api_key(key)
        assert len(result) == len(key)
        assert result[-4:] == key[-4:]
        assert all(c == "*" for c in result[:-4])
