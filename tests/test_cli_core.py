"""Tests for CLI credential loading and argument parsing.

Tests load_credentials() logic: CLI args > .ini file > env vars,
and build_parser() subcommand structure.
"""

import os
import pytest
import tempfile
from franklinwh_cloud.cli import load_credentials, build_parser


# ── load_credentials ────────────────────────────────────────────────

class TestLoadCredentials:
    """Test credential loading priority: CLI args > .ini > env vars."""

    def test_cli_args_take_priority(self):
        """When all three CLI args provided, they should be used directly."""
        email, password, gateway = load_credentials(
            email="cli@test.com", password="clipass", gateway="CLIGW"
        )
        assert email == "cli@test.com"
        assert password == "clipass"
        assert gateway == "CLIGW"

    def test_ini_file_loading(self):
        """Credentials loaded from .ini file when CLI args absent."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write("[energy.franklinwh.com]\n")
            f.write("email = ini@test.com\n")
            f.write("password = inipass\n")
            f.write("[gateways.enabled]\n")
            f.write("serialno = INIGW\n")
            ini_path = f.name

        try:
            email, password, gateway = load_credentials(config_path=ini_path)
            assert email == "ini@test.com"
            assert password == "inipass"
            assert gateway == "INIGW"
        finally:
            os.unlink(ini_path)

    def test_env_vars_fallback(self, monkeypatch):
        """Environment variables used when no .ini and no CLI args."""
        monkeypatch.setenv("FRANKLIN_USERNAME", "env@test.com")
        monkeypatch.setenv("FRANKLIN_PASSWORD", "envpass")
        monkeypatch.setenv("FRANKLIN_GATEWAY", "ENVGW")
        # Point to a nonexistent config to skip .ini
        email, password, gateway = load_credentials(config_path="/nonexistent.ini")
        assert email == "env@test.com"
        assert password == "envpass"
        assert gateway == "ENVGW"

    def test_missing_everything_returns_empty(self, monkeypatch):
        """No args, no .ini, no env → empty strings."""
        monkeypatch.delenv("FRANKLIN_USERNAME", raising=False)
        monkeypatch.delenv("FRANKLIN_PASSWORD", raising=False)
        monkeypatch.delenv("FRANKLIN_GATEWAY", raising=False)
        email, password, gateway = load_credentials(config_path="/nonexistent.ini")
        assert email == ""
        assert password == ""
        assert gateway == ""


# ── build_parser ────────────────────────────────────────────────────

class TestBuildParser:
    """Test CLI argument parser structure."""

    def test_has_subcommands(self):
        parser = build_parser()
        # Parse a known command — should not raise
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_tou_command(self):
        parser = build_parser()
        args = parser.parse_args(["tou"])
        assert args.command == "tou"

    def test_tou_set_option(self):
        parser = build_parser()
        args = parser.parse_args(["tou", "--set", "SELF"])
        assert args.command == "tou"
        assert args.set_mode == "SELF"

    def test_tou_next_option(self):
        parser = build_parser()
        args = parser.parse_args(["tou", "--next"])
        assert args.command == "tou"
        assert args.show_next is True

    def test_tou_rates_file_option(self):
        parser = build_parser()
        args = parser.parse_args(["tou", "--set", "SELF", "--rates-file", "rates.json"])
        assert args.set_mode == "SELF"
        assert args.rates_file == "rates.json"

    def test_tou_season_and_months(self):
        parser = build_parser()
        args = parser.parse_args(["tou", "--set", "SELF", "--season", "Summer", "--months", "10,11,12,1,2,3"])
        assert args.season == "Summer"
        assert args.months == "10,11,12,1,2,3"

    def test_tou_day_type(self):
        parser = build_parser()
        args = parser.parse_args(["tou", "--set", "SELF", "--day-type", "weekday"])
        assert args.day_type == "weekday"

    def test_tou_day_type_choices(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["tou", "--set", "SELF", "--day-type", "invalid"])

    def test_tou_wait_flag(self):
        parser = build_parser()
        args = parser.parse_args(["tou", "--set", "SELF", "--wait"])
        assert args.wait_confirm is True

    def test_tou_wait_default_false(self):
        parser = build_parser()
        args = parser.parse_args(["tou", "--set", "SELF"])
        assert args.wait_confirm is False

    def test_mode_command(self):
        parser = build_parser()
        args = parser.parse_args(["mode"])
        assert args.command == "mode"

    def test_json_flag(self):
        parser = build_parser()
        # --json is a top-level flag, not on subcommands
        args = parser.parse_args(["--json", "status"])
        assert args.json is True

    def test_monitor_interval(self):
        parser = build_parser()
        args = parser.parse_args(["monitor", "-i", "10"])
        assert args.interval == 10

    def test_installer_flag_true(self):
        parser = build_parser()
        args = parser.parse_args(["--installer", "status"])
        assert args.installer is True

    def test_installer_flag_default_false(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert getattr(args, "installer", False) is False

    def test_version_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    def test_all_commands_accepted(self):
        """All registered subcommands should parse without error."""
        parser = build_parser()
        # Commands that need no extra args
        for cmd in ["status", "mode", "tou", "monitor", "diag",
                     "discover", "metrics", "bms", "accessories"]:
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_accessories_alias(self):
        """accessories command should accept 'acc' alias."""
        parser = build_parser()
        args = parser.parse_args(["acc"])
        assert args.command == "acc"

    def test_accessories_power_flag(self):
        """accessories --power flag should be parsed correctly."""
        parser = build_parser()
        args = parser.parse_args(["accessories", "--power"])
        assert args.power is True

    def test_accessories_default_no_power(self):
        """accessories without --power should have power=False."""
        parser = build_parser()
        args = parser.parse_args(["accessories"])
        assert args.power is False

    def test_fetch_requires_args(self):
        """fetch requires http_method and path — should fail without them."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["fetch"])

    def test_fetch_with_args(self):
        """fetch with required args should parse."""
        parser = build_parser()
        args = parser.parse_args(["fetch", "GET", "/api/test"])
        assert args.command == "fetch"
