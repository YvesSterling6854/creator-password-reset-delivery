import pytest

from src.password_reset_service import InfraiError, PasswordResetRequest, ResetDelivery, deliver_reset


class FakeClient:
    def __init__(self):
        self.calls = []

    def request_password_reset(self, email):
        self.calls.append(("reset", email))
        return {"ok": True}

    def send_email(self, to, subject, body):
        self.calls.append(("email", to, subject, body))
        return {"ok": True, "data": {"message_id": "msg_123"}}


def test_reset_decision_requests_reset_before_delivering_link():
    client = FakeClient()
    request = PasswordResetRequest("maker@example.com", "https://example.com/reset/abc", "New subscriber content")

    result = deliver_reset(request, client)

    assert isinstance(result, ResetDelivery)
    assert client.calls[0] == ("reset", "maker@example.com")
    assert client.calls[1][0:3] == ("email", "maker@example.com", "Reset your creator account password")
    assert "https://example.com/reset/abc" in client.calls[1][3]
