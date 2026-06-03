"""Tests for runtime hooks subsystem."""

import os
import subprocess
from unittest.mock import patch

import pytest

from agentManager.runtime.hooks import (
    VALID_HOOK_EVENTS,
    HookConfig,
    HookRunner,
    load_hooks_from_list,
)


class TestHookConfig:
    """Tests for HookConfig dataclass."""

    def test_valid_hook_config(self):
        hook = HookConfig(
            name="test-hook",
            event="before_workflow_run",
            command="echo hello",
        )
        assert hook.name == "test-hook"
        assert hook.event == "before_workflow_run"
        assert hook.command == "echo hello"
        assert hook.enabled is False
        assert hook.timeout_seconds == 30
        assert hook.allow_failure is False

    def test_defaults(self):
        hook = HookConfig(name="h", event="after_workflow_run", command="true")
        assert hook.enabled is False
        assert hook.timeout_seconds == 30

    def test_rejects_empty_name(self):
        with pytest.raises(ValueError, match="name must not be empty"):
            HookConfig(name="", event="before_workflow_run", command="true")

    def test_rejects_invalid_event(self):
        with pytest.raises(ValueError, match="Invalid hook event"):
            HookConfig(name="h", event="invalid_event", command="true")

    def test_rejects_empty_command(self):
        with pytest.raises(ValueError, match="command must not be empty"):
            HookConfig(name="h", event="before_workflow_run", command="")

    def test_rejects_zero_timeout(self):
        with pytest.raises(ValueError, match="timeout_seconds must be >= 1"):
            HookConfig(name="h", event="before_workflow_run", command="true", timeout_seconds=0)

    def test_all_valid_events_accepted(self):
        for event in VALID_HOOK_EVENTS:
            hook = HookConfig(name="h", event=event, command="true")
            assert hook.event == event


class TestHookRunner:
    """Tests for HookRunner class."""

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_runs_enabled_hook(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["echo", "success"], returncode=0, stdout="success", stderr=""
        )
        hook = HookConfig(
            name="echo-test",
            event="before_workflow_run",
            command="echo success",
            enabled=True,
        )
        runner = HookRunner([hook])
        results = runner.run_hooks("before_workflow_run")
        assert "echo-test" in results
        assert results["echo-test"]["status"] == "ok"
        assert results["echo-test"]["stdout"] == "success"
        # Security: verify shell=False is used
        mock_run.assert_called_once()
        call_shell = mock_run.call_args.kwargs.get("shell")
        assert call_shell is False

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    def test_skips_disabled_hook(self):
        hook = HookConfig(
            name="disabled-hook",
            event="before_workflow_run",
            command="echo nope",
            enabled=False,
        )
        runner = HookRunner([hook])
        results = runner.run_hooks("before_workflow_run")
        assert "disabled-hook" not in results

    @patch.dict(os.environ, {"HOOKS_ENABLED": "false"})
    def test_skips_when_hooks_disabled(self):
        hook = HookConfig(
            name="no-run",
            event="before_workflow_run",
            command="echo nope",
            enabled=True,
        )
        runner = HookRunner([hook])
        results = runner.run_hooks("before_workflow_run")
        assert "no-run" not in results

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_only_runs_matching_event(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["echo"], returncode=0, stdout="ok", stderr=""
        )
        before = HookConfig(
            name="before", event="before_workflow_run", command="echo before", enabled=True
        )
        after = HookConfig(
            name="after", event="after_workflow_run", command="echo after", enabled=True
        )
        runner = HookRunner([before, after])
        results = runner.run_hooks("before_workflow_run")
        assert "before" in results
        assert "after" not in results

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_failed_hook_raises(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["exit"], returncode=1, stdout="", stderr=""
        )
        hook = HookConfig(
            name="fail",
            event="before_workflow_run",
            command="exit 1",
            enabled=True,
        )
        runner = HookRunner([hook])
        with pytest.raises(RuntimeError, match="failed with exit code"):
            runner.run_hooks("before_workflow_run")

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_allow_failure_suppresses_error(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["exit"], returncode=1, stdout="", stderr=""
        )
        hook = HookConfig(
            name="fail-ok",
            event="before_workflow_run",
            command="exit 1",
            enabled=True,
            allow_failure=True,
        )
        runner = HookRunner([hook])
        results = runner.run_hooks("before_workflow_run")
        assert "fail-ok" in results
        assert results["fail-ok"]["status"] == "failed"

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_timeout_raises(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
        hook = HookConfig(
            name="timeout",
            event="before_workflow_run",
            command="sleep 60",
            enabled=True,
            timeout_seconds=1,
        )
        runner = HookRunner([hook])
        with pytest.raises(RuntimeError, match="timed out"):
            runner.run_hooks("before_workflow_run")

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_timeout_allow_failure(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=1)
        hook = HookConfig(
            name="timeout-ok",
            event="before_workflow_run",
            command="sleep 60",
            enabled=True,
            timeout_seconds=1,
            allow_failure=True,
        )
        runner = HookRunner([hook])
        results = runner.run_hooks("before_workflow_run")
        assert results["timeout-ok"]["status"] == "timeout"

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_context_passed_to_hook(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["python", "-c", "..."], returncode=0, stdout="wf-42", stderr=""
        )
        hook = HookConfig(
            name="ctx-test",
            event="before_workflow_run",
            command="python -c \"import os; print(os.environ.get('WORKFLOW_ID', ''))\"",
            enabled=True,
        )
        runner = HookRunner([hook])
        results = runner.run_hooks("before_workflow_run", {"WORKFLOW_ID": "wf-42"})
        assert results["ctx-test"]["stdout"] == "wf-42"

    @patch.dict(os.environ, {"HOOKS_ENABLED": "true"})
    @patch("subprocess.run")
    def test_task_plan_hook_events(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["echo"], returncode=0, stdout="ok", stderr=""
        )
        before = HookConfig(
            name="pre-confirm",
            event="before_task_plan_confirm",
            command="echo pre",
            enabled=True,
        )
        after = HookConfig(
            name="post-confirm",
            event="after_task_plan_confirm",
            command="echo post",
            enabled=True,
        )
        runner = HookRunner([before, after])
        results = runner.run_hooks("before_task_plan_confirm")
        assert "pre-confirm" in results
        assert "post-confirm" not in results
        results2 = runner.run_hooks("after_task_plan_confirm")
        assert "post-confirm" in results2

    def test_add_hook(self):
        runner = HookRunner()
        runner.add_hook(HookConfig(name="added", event="before_workflow_run", command="echo ok"))
        assert len(runner.hooks) == 1

    def test_load_hooks_from_list(self):
        configs = [
            {"name": "h1", "event": "before_workflow_run", "command": "echo 1"},
            {"name": "h2", "event": "after_workflow_run", "command": "echo 2", "enabled": True},
        ]
        hooks = load_hooks_from_list(configs)
        assert len(hooks) == 2
        assert hooks[0].name == "h1"
        assert hooks[1].enabled is True
