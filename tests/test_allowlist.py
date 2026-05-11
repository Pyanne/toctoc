"""Tests for allowlist manager."""

from anpr_gate.allowlist.manager import AllowlistManager


class TestAllowlistManager:
    def test_empty_allowlist(self):
        al = AllowlistManager()
        assert al.is_empty()
        assert al.is_allowed("AB-123-CD") is False

    def test_add_and_check(self):
        al = AllowlistManager()
        al.add("AB-123-CD")
        assert al.is_allowed("AB-123-CD") is True
        assert al.is_allowed("ab-123-cd") is True  # normalized
        assert len(al) == 1

    def test_normalization(self):
        al = AllowlistManager(["ab 123 cd"])
        assert al.is_allowed("AB-123-CD") is True

    def test_remove(self):
        al = AllowlistManager(["AB-123-CD"])
        assert al.remove("AB-123-CD") is True
        assert al.is_allowed("AB-123-CD") is False

    def test_update_replaces_all(self):
        al = AllowlistManager(["OLD"])
        al.update(["NEW1", "NEW2"])
        assert al.is_allowed("OLD") is False
        assert al.is_allowed("NEW1") is True
        assert len(al) == 2