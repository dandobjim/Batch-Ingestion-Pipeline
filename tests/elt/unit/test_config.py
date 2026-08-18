"""Unit tests for the settings layer.

Every test that builds ``EnvVarsConfig`` directly passes ``_env_file=None``:
otherwise pydantic-settings picks up the developer's real ``.env`` and the
suite passes locally while failing in CI.
"""

import logging

import pytest
import structlog
from pydantic import ValidationError

from elt.config.env_vars_config import PROJECT_ROOT, EnvVarsConfig, get_env_vars
from elt.config.logging_configuration import configure_logging


class TestEnvVarsConfig:
    def test_reads_the_api_key_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("GITHUB_API_KEY", "abc")

        assert EnvVarsConfig(_env_file=None).api_key == "abc"

    def test_raises_when_the_api_key_is_missing(self):
        with pytest.raises(ValidationError, match="GITHUB_API_KEY"):
            EnvVarsConfig(_env_file=None)

    def test_field_name_is_not_accepted_as_env_var(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "abc")

        with pytest.raises(ValidationError, match="GITHUB_API_KEY"):
            EnvVarsConfig(_env_file=None)

    def test_ignores_unknown_env_vars(self, monkeypatch):
        monkeypatch.setenv("GITHUB_API_KEY", "abc")
        monkeypatch.setenv("TOTALLY_UNRELATED", "noise")

        assert EnvVarsConfig(_env_file=None).api_key == "abc"


class TestEnvFileLocation:
    def test_env_file_is_an_absolute_project_path(self):
        """Pins the fix: a relative ``.env`` breaks under a foreign CWD."""
        env_file = EnvVarsConfig.model_config["env_file"]

        assert env_file.is_absolute()
        assert env_file == PROJECT_ROOT / ".env"

    def test_env_file_does_not_depend_on_the_cwd(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        assert EnvVarsConfig.model_config["env_file"] == PROJECT_ROOT / ".env"


class TestGetEnvVars:
    def test_caches_the_settings_instance(self, monkeypatch):
        monkeypatch.setenv("GITHUB_API_KEY", "abc")

        assert get_env_vars() is get_env_vars()

    def test_cache_clear_picks_up_a_new_value(self, monkeypatch):
        monkeypatch.setenv("GITHUB_API_KEY", "abc")
        first = get_env_vars()

        get_env_vars.cache_clear()
        monkeypatch.setenv("GITHUB_API_KEY", "xyz")
        second = get_env_vars()

        assert first.api_key == "abc"
        assert second.api_key == "xyz"
        assert first is not second


class TestLoggingConfiguration:
    def test_configure_logging_is_explicit_not_import_time(self):
        """Importing the pipeline must not reconfigure global logging."""
        structlog.reset_defaults()
        assert not structlog.is_configured()

        configure_logging()

        try:
            assert structlog.is_configured()
            config = structlog.get_config()
            assert config["cache_logger_on_first_use"] is False
            assert isinstance(
                config["wrapper_class"](None, None, {}), structlog.typing.BindableLogger
            )
        finally:
            structlog.reset_defaults()

    def test_configure_logging_allows_all_levels(self):
        structlog.reset_defaults()
        configure_logging()

        try:
            with structlog.testing.capture_logs() as logs:
                structlog.get_logger().log(logging.DEBUG, "hello")
            assert logs
        finally:
            structlog.reset_defaults()
