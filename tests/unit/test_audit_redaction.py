"""Tests for audit event sensitive field redaction."""

from __future__ import annotations

from agentManager.observability.audit import AuditEvent, AuditEventType, redact_audit_event


def test_redacts_default_sensitive_detail_fields():
    event = AuditEvent(
        event_type=AuditEventType.CUSTOM,
        detail={
            "api_key": "sk-secret",
            "password": "cleartext",
            "nested": {"token": "jwt", "safe": "visible"},
        },
    )

    redacted = redact_audit_event(event)

    assert redacted.detail["api_key"] == "***REDACTED***"
    assert redacted.detail["password"] == "***REDACTED***"
    assert redacted.detail["nested"]["token"] == "***REDACTED***"
    assert redacted.detail["nested"]["safe"] == "visible"


def test_redact_fields_are_configurable(monkeypatch):
    monkeypatch.setenv("AUDIT_REDACT_FIELDS", "secret,private")
    event = AuditEvent(
        event_type=AuditEventType.CUSTOM,
        detail={"secret": "hidden", "token": "visible", "items": [{"private": "hidden"}]},
    )

    redacted = redact_audit_event(event)

    assert redacted.detail["secret"] == "***REDACTED***"
    assert redacted.detail["token"] == "visible"
    assert redacted.detail["items"][0]["private"] == "***REDACTED***"
