"""Tests for the primary-flow email allowlist in auth.service_decorator.

This is defense-in-depth for when the OAuth consent screen is published
"In production": Google then lets any Google account reach the
authorisation flow, not just the small set of test users allowed while
"Testing". These tests confirm that only configured emails can pass the
allowlist used by the OAuth 2.1 authentication path.
"""

import pytest

from auth.service_decorator import (
    GoogleAuthenticationError,
    _enforce_primary_email_allowlist,
    _get_allowed_primary_emails,
)


def test_default_allowlist_permits_owner_email():
    assert "paul.crouch1@gmail.com" in _get_allowed_primary_emails()


def test_owner_email_passes_case_insensitively():
    # Should not raise, including with different casing.
    _enforce_primary_email_allowlist("paul.crouch1@gmail.com", "test_tool")
    _enforce_primary_email_allowlist("Paul.Crouch1@Gmail.com", "test_tool")


def test_unknown_email_is_rejected():
    with pytest.raises(GoogleAuthenticationError):
        _enforce_primary_email_allowlist("stranger@example.com", "test_tool")


def test_joint_account_email_is_not_implicitly_allowed_on_primary_flow():
    # The joint account is only ever loaded via _authenticate_joint_service,
    # which bypasses this allowlist entirely - it should NOT be a member of
    # the primary-flow allowlist by default.
    with pytest.raises(GoogleAuthenticationError):
        _enforce_primary_email_allowlist("lizzieandpaul2019@gmail.com", "test_tool")


def test_allowlist_override_via_env(monkeypatch):
    monkeypatch.setenv(
        "WORKSPACE_MCP_ALLOWED_USERS", "someone@example.com, other@example.com"
    )
    allowed = _get_allowed_primary_emails()
    assert allowed == {"someone@example.com", "other@example.com"}
    _enforce_primary_email_allowlist("someone@example.com", "test_tool")
    with pytest.raises(GoogleAuthenticationError):
        _enforce_primary_email_allowlist("paul.crouch1@gmail.com", "test_tool")
