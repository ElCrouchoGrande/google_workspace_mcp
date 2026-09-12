"""Tests that the account="joint" override is gated by the primary allowlist.

Regression coverage for a gap found in review: `require_google_service`'s
wrapper special-cases account="joint" and calls `_authenticate_joint_service`
directly, bypassing `_authenticate_service` (and therefore the allowlist
enforced inside `get_authenticated_google_service_oauth21`) entirely. Without
an explicit gate on this branch too, any authenticated Google account -
which is anyone, once the OAuth consent screen is published "In production"
- could reach the joint mailbox simply by passing account="joint".
"""

import pytest

import auth.service_decorator as service_decorator


class _FakeService:
    """Minimal stand-in with the .close() the wrapper calls on cleanup."""

    def close(self) -> None:
        pass


def _patch_common_decorator_state(monkeypatch, authenticated_user):
    async def fake_get_auth_context(tool_name):
        return (authenticated_user, "bearer_token", "session-123")

    monkeypatch.setattr(service_decorator, "is_oauth21_enabled", lambda: True)
    monkeypatch.setattr(service_decorator, "_get_auth_context", fake_get_auth_context)
    monkeypatch.setattr(
        service_decorator, "_detect_oauth_version", lambda *args, **kwargs: True
    )


@pytest.mark.asyncio
async def test_joint_override_rejects_unauthorised_authenticated_user(monkeypatch):
    """An authenticated stranger must not reach the joint account."""
    _patch_common_decorator_state(monkeypatch, authenticated_user="stranger@example.com")

    async def fake_authenticate_joint_service(*args, **kwargs):
        raise AssertionError(
            "_authenticate_joint_service must not run for a disallowed user"
        )

    monkeypatch.setattr(
        service_decorator,
        "_authenticate_joint_service",
        fake_authenticate_joint_service,
    )

    @service_decorator.require_google_service("gmail", "gmail_read")
    async def sample_tool(service, account: str = "primary"):
        raise AssertionError("tool body should not run when auth fails")

    with pytest.raises(service_decorator.GoogleAuthenticationError):
        await sample_tool(account="joint")


@pytest.mark.asyncio
async def test_joint_override_allows_authorised_owner(monkeypatch):
    """The app owner's own authenticated session can still use account="joint"."""
    _patch_common_decorator_state(monkeypatch, authenticated_user="paul.crouch1@gmail.com")

    calls = []
    fake_service = _FakeService()

    async def fake_authenticate_joint_service(
        service_name, service_version, tool_name, resolved_scopes
    ):
        calls.append((service_name, service_version))
        return fake_service, "lizzieandpaul2019@gmail.com"

    monkeypatch.setattr(
        service_decorator,
        "_authenticate_joint_service",
        fake_authenticate_joint_service,
    )

    @service_decorator.require_google_service("gmail", "gmail_read")
    async def sample_tool(service, user_google_email: str, account: str = "primary"):
        return service

    result = await sample_tool(account="joint")

    assert result is fake_service
    assert calls == [("gmail", "v1")]


@pytest.mark.asyncio
async def test_joint_override_rejects_missing_authenticated_user(monkeypatch):
    """No verified identity at all must fail closed, not crash or fall through.

    In OAuth 2.1 mode a missing authenticated_user is already rejected
    earlier in the wrapper (_extract_oauth21_user_email), before the
    account="joint" branch is even reached - so the assertion here is just
    that _authenticate_joint_service never runs, not a specific exception
    type.
    """
    _patch_common_decorator_state(monkeypatch, authenticated_user=None)

    async def fake_authenticate_joint_service(*args, **kwargs):
        raise AssertionError(
            "_authenticate_joint_service must not run without a verified identity"
        )

    monkeypatch.setattr(
        service_decorator,
        "_authenticate_joint_service",
        fake_authenticate_joint_service,
    )

    @service_decorator.require_google_service("gmail", "gmail_read")
    async def sample_tool(service, account: str = "primary"):
        raise AssertionError("tool body should not run when auth fails")

    with pytest.raises(Exception):
        await sample_tool(account="joint")
