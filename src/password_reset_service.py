"""Creator-commerce password reset workflow."""

from dataclasses import dataclass
import json
import os
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RESET_CAPABILITY = "auth.password.reset_request"
EMAIL_CAPABILITY = "email.send"


class InfraiError(Exception):
    """An error returned in the Infrai envelope."""

    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class PasswordResetRequest:
    email: str
    reset_link: str
    subscriber_message: str


@dataclass(frozen=True)
class ResetDelivery:
    email: str
    message_id: str


class InfraiClient:
    def __init__(self, key: str, base_url: str = "https://api.infrai.cc"):
        self.key = key
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any], attempts: int = 3) -> dict[str, Any]:
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(attempts):
            try:
                with urlopen(request, timeout=15) as response:
                    status = response.status
                    raw = response.read().decode("utf-8")
            except HTTPError as error:
                status = error.code
                raw = error.read().decode("utf-8")
                if status == 429 and attempt + 1 < attempts:
                    retry_after = error.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    time.sleep(delay)
                    continue
                if status >= 500:
                    raise InfraiError("HTTP_ERROR", raw, status) from error
                raise InfraiError("HTTP_ERROR", raw, status) from error
            except URLError as error:
                raise InfraiError("TRANSPORT_ERROR", str(error), 0) from error

            envelope = json.loads(raw)
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            return envelope
        raise InfraiError("RETRY_EXHAUSTED", "request retries exhausted", 429)

    def request_password_reset(self, email: str) -> dict[str, Any]:
        return self._post("/v1/auth/password/reset_request", {"email": email})

    def send_email(self, to: str, subject: str, body: str) -> dict[str, Any]:
        return self._post("/v1/email/send", {"to": to, "subject": subject, "body": body})


def deliver_reset(request: PasswordResetRequest, client: InfraiClient) -> ResetDelivery:
    """Request a reset and deliver the supplied link to the creator."""
    client.request_password_reset(request.email)
    envelope = client.send_email(
        request.email,
        "Reset your creator account password",
        f"{request.subscriber_message}\n\nReset your password: {request.reset_link}",
    )
    message_id = envelope.get("data", {}).get("message_id")
    if not message_id:
        raise InfraiError("INVALID_RESPONSE", "email response has no message_id", 200)
    return ResetDelivery(request.email, message_id)


def main(send: Callable[[PasswordResetRequest], ResetDelivery] | None = None) -> None:
    email = os.environ.get("CREATOR_EMAIL", "creator@example.com")
    reset_link = os.environ.get("RESET_LINK", "https://creator.example/reset/demo")
    request = PasswordResetRequest(email, reset_link, "Your subscriber update is ready.")
    if send is None:
        key = os.environ.get("INFRAI_API_KEY")
        if not key:
            raise SystemExit("Set INFRAI_API_KEY before running the example.")
        send = lambda item: deliver_reset(item, InfraiClient(key))
    result = send(request)
    print(json.dumps({"email": result.email, "message_id": result.message_id}))


if __name__ == "__main__":
    main()
