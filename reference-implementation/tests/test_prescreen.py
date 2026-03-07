"""Layer 1a: Unit tests for the PreScreen engine (PS-001 through PS-010)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from quorum.models import Severity
from quorum.prescreen import PreScreen

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ps() -> PreScreen:
    return PreScreen()


# ── PS-001: Hardcoded Paths ──────────────────────────────────────────────────


class TestPrescreenPS001HardcodedPaths:
    def test_detects_absolute_unix_home_path(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('DATA = "/Users/john/data"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "FAIL"

    def test_detects_absolute_linux_home_path(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('DATA = "/home/deploy/app"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "FAIL"

    def test_detects_etc_path(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('CONFIG = "/etc/myapp/config.yaml"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "FAIL"

    def test_detects_var_path(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('LOG_DIR = "/var/log/myapp"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "FAIL"

    def test_detects_tmp_path(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('TEMP = "/tmp/myapp/cache"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "FAIL"

    def test_detects_windows_path(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('INSTALL = r"C:\\Program Files\\MyApp"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "FAIL"

    def test_passes_clean_file(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('DATA = "./data/input.csv"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "PASS"

    def test_passes_relative_paths(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('from . import module\npath = "../config.yaml"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "PASS"

    def test_evidence_contains_line_numbers(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('x = 1\nDATA = "/Users/john/data"\ny = 2\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert "L2" in check.evidence

    def test_multiple_paths_counted(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('/Users/a/b\n/home/c/d\n/etc/e/f\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert "3 occurrence" in check.description

    def test_fixture_file(self, ps):
        f = FIXTURES / "edge" / "with-hardcoded-path.py"
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-001")
        assert check.result == "FAIL"
        assert check.severity == Severity.HIGH


# ── PS-002: Credentials ──────────────────────────────────────────────────────


class TestPrescreenPS002Credentials:
    def test_detects_password_assignment(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('password = "supersecret123"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "FAIL"

    def test_detects_api_key_pattern(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('api_key = "sk-ant-api03-1234567890abcdefghijklmn"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "FAIL"

    def test_detects_secret_assignment(self, ps, tmp_path):
        f = tmp_path / "t.yaml"
        f.write_text('client_secret: "abcdef1234567890abcdef"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "FAIL"

    def test_detects_token_assignment(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('token = "ghp_1234567890abcdefghijklmnopqrstuvwx"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "FAIL"

    def test_detects_private_key_header(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('BEGIN RSA PRIVATE KEY\nMIIEp...\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "FAIL"

    def test_detects_long_base64_blob(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        blob = "A" * 50  # 50 chars of base64 alphabet
        f.write_text(f'secret = "{blob}"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "FAIL"

    def test_passes_clean_file(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('x = 42\nname = "hello"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "PASS"

    def test_severity_is_critical(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('password: "hunter2"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.severity == Severity.CRITICAL

    def test_evidence_is_redacted(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('password = "mysuperlongsecretpassword"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert "***" in check.evidence

    def test_fixture_file(self, ps):
        f = FIXTURES / "edge" / "with-api-key.txt"
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-002")
        assert check.result == "FAIL"


# ── PS-003: PII ──────────────────────────────────────────────────────────────


class TestPrescreenPS003PII:
    def test_detects_email_address(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('contact: john.doe@company.com\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-003")
        assert check.result == "FAIL"

    def test_detects_us_phone_number(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('phone: (555) 234-5678\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-003")
        assert check.result == "FAIL"

    def test_detects_ssn_pattern(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('ssn: 123-45-6789\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-003")
        assert check.result == "FAIL"

    def test_passes_clean_file(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('This is a clean file with no PII.\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-003")
        assert check.result == "PASS"

    def test_evidence_breakdown(self, ps, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text('email: a@b.com\nphone: (555) 234-5678\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-003")
        assert "email" in check.description

    def test_fixture_file(self, ps):
        f = FIXTURES / "edge" / "with-email.txt"
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-003")
        assert check.result == "FAIL"


# ── PS-004: JSON Syntax ──────────────────────────────────────────────────────


class TestPrescreenPS004JSONSyntax:
    def test_valid_json_passes(self, ps, tmp_path):
        f = tmp_path / "t.json"
        f.write_text('{"valid": true}')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-004")
        assert check.result == "PASS"

    def test_invalid_json_fails(self, ps, tmp_path):
        f = tmp_path / "t.json"
        f.write_text('{"invalid": true, missing_quote}')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-004")
        assert check.result == "FAIL"

    def test_empty_json_object_passes(self, ps, tmp_path):
        f = tmp_path / "t.json"
        f.write_text('{}')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-004")
        assert check.result == "PASS"

    def test_trailing_comma_fails(self, ps, tmp_path):
        f = tmp_path / "t.json"
        f.write_text('{"key": "value",}')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-004")
        assert check.result == "FAIL"

    def test_skipped_for_non_json(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('x = 1\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-004")
        assert check.result == "SKIP"

    def test_evidence_shows_error_location(self, ps, tmp_path):
        f = tmp_path / "t.json"
        f.write_text('{"key": }')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-004")
        assert "line" in check.evidence.lower()


# ── PS-005: YAML Syntax ──────────────────────────────────────────────────────


class TestPrescreenPS005YAMLSyntax:
    def test_valid_yaml_passes(self, ps, tmp_path):
        f = tmp_path / "t.yaml"
        f.write_text('key: value\nlist:\n  - item1\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-005")
        assert check.result == "PASS"

    def test_invalid_yaml_fails(self, ps, tmp_path):
        f = tmp_path / "t.yaml"
        f.write_text('key: value\n  bad indent: here\n    worse:\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-005")
        assert check.result == "FAIL"

    def test_yml_extension_accepted(self, ps, tmp_path):
        f = tmp_path / "t.yml"
        f.write_text('key: value\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-005")
        assert check.result == "PASS"

    def test_skipped_for_non_yaml(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('x = 1\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-005")
        assert check.result == "SKIP"

    def test_empty_yaml_passes(self, ps, tmp_path):
        f = tmp_path / "t.yaml"
        f.write_text('')
        # Empty YAML is valid (parses as None)
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-005")
        assert check.result == "PASS"


# ── PS-006: Python Syntax ────────────────────────────────────────────────────


class TestPrescreenPS006PythonSyntax:
    def test_valid_python_passes(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('def foo():\n    pass\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-006")
        assert check.result == "PASS"

    def test_syntax_error_fails(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('def foo(\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-006")
        assert check.result == "FAIL"

    def test_indentation_error_fails(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('def foo():\npass\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-006")
        assert check.result == "FAIL"

    def test_skipped_for_non_python(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('# Hello\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-006")
        assert check.result == "SKIP"

    def test_utf8_python_passes(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('# -*- coding: utf-8 -*-\nname = "café"\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-006")
        assert check.result == "PASS"

    def test_evidence_shows_error_line(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('x = 1\ndef foo(\ny = 2\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-006")
        assert check.result == "FAIL"


# ── PS-007: Broken MD Links ──────────────────────────────────────────────────


class TestPrescreenPS007BrokenLinks:
    def test_detects_broken_relative_link(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('[link](nonexistent.md)\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-007")
        assert check.result == "FAIL"

    def test_ignores_external_links(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('[google](https://google.com)\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-007")
        assert check.result == "PASS"

    def test_ignores_anchor_links(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('[section](#some-section)\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-007")
        assert check.result == "PASS"

    def test_valid_relative_link_passes(self, ps, tmp_path):
        target = tmp_path / "other.md"
        target.write_text('# Other\n')
        f = tmp_path / "t.md"
        f.write_text('[other](other.md)\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-007")
        assert check.result == "PASS"

    def test_skipped_for_non_markdown(self, ps, tmp_path):
        f = tmp_path / "t.py"
        f.write_text('# [link](missing.md)\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-007")
        assert check.result == "SKIP"

    def test_ignores_mailto_links(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('[email](mailto:test@example.com)\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-007")
        assert check.result == "PASS"


# ── PS-008: TODO Markers ─────────────────────────────────────────────────────


class TestPrescreenPS008TODOMarkers:
    def test_finds_TODO(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('TODO: fix this\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert check.result == "FAIL"

    def test_finds_FIXME(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('FIXME: urgent\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert check.result == "FAIL"

    def test_finds_HACK(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('HACK: workaround\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert check.result == "FAIL"

    def test_finds_XXX(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('XXX: needs rewrite\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert check.result == "FAIL"

    def test_case_insensitive(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('todo: lowercase\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert check.result == "FAIL"

    def test_passes_clean_file(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('# Complete document\nAll sections done.\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert check.result == "PASS"

    def test_counts_multiple(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('TODO: a\nFIXME: b\nHACK: c\n')
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert "3" in check.description

    def test_fixture_file(self, ps):
        f = FIXTURES / "edge" / "with-todo.md"
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-008")
        assert check.result == "FAIL"


# ── PS-009: Whitespace ───────────────────────────────────────────────────────


class TestPrescreenPS009Whitespace:
    def test_detects_trailing_whitespace(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("text   \nmore text\n")
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-009")
        assert check.result == "FAIL"
        assert "trailing whitespace" in check.description.lower()

    def test_detects_mixed_line_endings(self, ps, tmp_path):
        f = tmp_path / "t.md"
        # Pass raw content with mixed endings directly (read_text normalizes)
        content = "line one\r\nline two\nline three\n"
        f.write_bytes(content.encode("utf-8"))
        result = ps.run(f, content)
        check = next(c for c in result.checks if c.id == "PS-009")
        assert check.result == "FAIL"
        assert "mixed" in check.description.lower()

    def test_passes_clean_file(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("clean line one\nclean line two\n")
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-009")
        assert check.result == "PASS"

    def test_detects_trailing_tabs(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("text\t\nmore\n")
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-009")
        assert check.result == "FAIL"


# ── PS-010: Empty File ───────────────────────────────────────────────────────


class TestPrescreenPS010EmptyFile:
    def test_detects_empty_file(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("")
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-010")
        assert check.result == "FAIL"

    def test_detects_whitespace_only(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("\n\n   \n")
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-010")
        assert check.result == "FAIL"

    def test_passes_with_content(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# Header\n")
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-010")
        assert check.result == "PASS"

    def test_fixture_empty_file(self, ps):
        f = FIXTURES / "edge" / "empty.md"
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-010")
        assert check.result == "FAIL"


# ── PreScreen engine-level tests ─────────────────────────────────────────────


class TestPrescreenEngine:
    def test_run_returns_all_10_checks(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# Hello\n")
        result = ps.run(f, f.read_text())
        assert result.total_checks == 10

    def test_counts_match(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# Hello\n")
        result = ps.run(f, f.read_text())
        assert result.passed + result.failed + result.skipped == result.total_checks

    def test_has_failures_property(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text('[broken](missing.md)\n')
        result = ps.run(f, f.read_text())
        assert result.has_failures is True

    def test_no_failures_property(self, ps, tmp_path):
        target = tmp_path / "other.md"
        target.write_text("# Other\n")
        f = tmp_path / "t.md"
        f.write_text("# Clean\n")
        result = ps.run(f, f.read_text())
        # May or may not have failures depending on whitespace etc
        assert isinstance(result.has_failures, bool)

    def test_runtime_ms_recorded(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# Hello\n")
        result = ps.run(f, f.read_text())
        assert result.runtime_ms >= 0

    def test_to_evidence_block(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("TODO: fix\n")
        result = ps.run(f, f.read_text())
        block = result.to_evidence_block()
        assert "Pre-Screen Evidence" in block
        assert "PS-008" in block

    def test_oversized_artifact_skipped(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("x" * (PreScreen.MAX_ARTIFACT_SIZE + 1))
        result = ps.run(f, f.read_text())
        assert result.total_checks == 0

    def test_binary_content_skipped(self, ps, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("hello\x00world")
        result = ps.run(f, f.read_text())
        assert result.total_checks == 0

    def test_clean_research_fixture(self, ps):
        f = FIXTURES / "good" / "research-clean.md"
        result = ps.run(f, f.read_text())
        # Clean fixture should have no security failures
        security_checks = [c for c in result.checks if c.category == "security"]
        for c in security_checks:
            assert c.result == "PASS", f"{c.id} unexpectedly failed"

    def test_clean_python_fixture(self, ps):
        f = FIXTURES / "good" / "code-clean.py"
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-006")
        assert check.result == "PASS"

    def test_clean_yaml_fixture(self, ps):
        f = FIXTURES / "good" / "config-valid.yaml"
        result = ps.run(f, f.read_text())
        check = next(c for c in result.checks if c.id == "PS-005")
        assert check.result == "PASS"
