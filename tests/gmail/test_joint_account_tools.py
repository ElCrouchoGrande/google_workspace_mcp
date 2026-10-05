"""account="joint" behaviour in the Gmail tools (sender identity, tool surface)."""

import base64
import inspect
from unittest.mock import AsyncMock, Mock, patch

import pytest

import gmail.gmail_tools as gmail_tools
from gmail.gmail_tools import (
    JOINT_GMAIL_ACCOUNT,
    draft_gmail_message,
    send_gmail_message,
)


def _unwrap(tool):
    fn = tool.fn if hasattr(tool, "fn") else tool
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _raw_from_header(call_kwargs) -> str:
    raw = call_kwargs["body"]["raw"] if "body" in call_kwargs else None
    if raw is None:
        raw = call_kwargs["body"]["message"]["raw"]
    text = base64.urlsafe_b64decode(raw).decode("utf-8", errors="ignore")
    return next(line for line in text.splitlines() if line.lower().startswith("from:"))


GMAIL_TOOLS_WITH_ACCOUNT = [
    "search_gmail_messages",
    "get_gmail_message_content",
    "get_gmail_messages_content_batch",
    "get_gmail_attachment_content",
    "send_gmail_message",
    "draft_gmail_message",
    "get_gmail_thread_content",
    "get_gmail_threads_content_batch",
    "list_gmail_labels",
    "manage_gmail_label",
    "list_gmail_filters",
    "manage_gmail_filter",
    "modify_gmail_message_labels",
    "batch_modify_gmail_message_labels",
]


@pytest.mark.parametrize("name", GMAIL_TOOLS_WITH_ACCOUNT)
def test_tool_exposes_account_parameter_defaulting_to_primary(name):
    params = inspect.signature(_unwrap(getattr(gmail_tools, name))).parameters
    assert "account" in params
    assert params["account"].default == "primary"


@pytest.mark.asyncio
async def test_send_as_joint_uses_joint_address_as_sender():
    service = Mock()
    service.users().messages().send().execute.return_value = {"id": "m1"}

    result = await _unwrap(send_gmail_message)(
        service=service,
        user_google_email="paul.crouch1@gmail.com",
        to="recipient@example.com",
        subject="Hello",
        body="Hi",
        include_signature=False,
        account="joint",
    )

    assert "Email sent! Message ID: m1" in result
    kwargs = service.users.return_value.messages.return_value.send.call_args.kwargs
    assert JOINT_GMAIL_ACCOUNT in _raw_from_header(kwargs)


@pytest.mark.asyncio
async def test_send_as_primary_keeps_primary_address_as_sender():
    service = Mock()
    service.users().messages().send().execute.return_value = {"id": "m2"}

    await _unwrap(send_gmail_message)(
        service=service,
        user_google_email="paul.crouch1@gmail.com",
        to="recipient@example.com",
        subject="Hello",
        body="Hi",
        include_signature=False,
    )

    kwargs = service.users.return_value.messages.return_value.send.call_args.kwargs
    header = _raw_from_header(kwargs)
    assert "paul.crouch1@gmail.com" in header
    assert JOINT_GMAIL_ACCOUNT not in header


@pytest.mark.asyncio
async def test_forward_as_joint_uses_joint_address_as_sender():
    forward = AsyncMock(return_value="forwarded")
    with patch.object(gmail_tools, "_forward_gmail_message_impl", forward):
        await _unwrap(send_gmail_message)(
            service=Mock(),
            user_google_email="paul.crouch1@gmail.com",
            to="recipient@example.com",
            forward_message_id="abc",
            account="joint",
        )

    assert forward.await_args.kwargs["user_google_email"] == JOINT_GMAIL_ACCOUNT


@pytest.mark.asyncio
async def test_draft_as_joint_resolves_signature_for_joint_address():
    service = Mock()
    service.users().drafts().create().execute.return_value = {"id": "d1"}
    resolver = AsyncMock(return_value=(JOINT_GMAIL_ACCOUNT, ""))

    with patch.object(gmail_tools, "_get_send_as_identity_and_signature", resolver):
        await _unwrap(draft_gmail_message)(
            service=service,
            user_google_email="paul.crouch1@gmail.com",
            subject="Draft",
            body="Hi",
            to="recipient@example.com",
            include_signature=True,
            account="joint",
        )

    assert resolver.await_args.kwargs["fallback_email"] == JOINT_GMAIL_ACCOUNT
