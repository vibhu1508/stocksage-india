"""Auth on sockets and transcribe. Run: python -m tests.test_ws_auth (from backend/), or pytest.
Uses an in-memory SQLite DB, never the real one."""

import hashlib
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "test-only-secret")
os.environ["REDIS_URL"] = ""  # no shared Redis: TestClient runs each call on its own event loop

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import main  # noqa: E402
from database import Base, get_db  # noqa: E402
from models import User, UserSession  # noqa: E402
from routers import auth  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
auth.SessionLocal = TestSession  # sockets open their own session through this name


def _db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[get_db] = _db
client = TestClient(main.app)


def _session_token(valid=True):
    db = TestSession()
    user = User(email=f"u{datetime.now().timestamp()}@test.local", name="T", is_active=True)
    db.add(user)
    db.commit()
    token, _ = auth.create_access_token({"sub": str(user.id)})
    db.add(UserSession(
        user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1), is_valid=valid,
    ))
    db.commit()
    db.close()
    return token


def _first_frame(path):
    with client.websocket_connect(path) as ws:
        return ws.receive_json()


def test_sockets_reject_missing_bad_and_revoked_tokens():
    revoked = _session_token(valid=False)
    for q in ["", "?token=garbage", f"?token={revoked}"]:
        assert _first_frame(f"/api/chat/ws{q}")["type"] == "error"
        assert _first_frame(f"/api/market/dhan/chart/ws{q}{'&' if q else '?'}symbol=TCS")["detail"] == "Unauthorized"
        assert _first_frame(f"/api/market/dhan/stream/ws{q}")["error"] == "Unauthorized"


def test_chat_accepts_valid_session():
    with client.websocket_connect(f"/api/chat/ws?token={_session_token()}") as ws:
        ws.send_json({"action": "confirm_holding"})  # nothing pending -> answered, not closed
        assert ws.receive_json()["detail"] == "This request has expired. Please ask again."


def test_transcribe_requires_login():
    files = {"audio": ("a.webm", b"0", "audio/webm")}
    assert client.post("/api/chat/transcribe", files=files).status_code == 401
    r = client.post("/api/chat/transcribe", files=files, headers={"Authorization": f"Bearer {_session_token()}"})
    assert r.status_code != 401


def test_dhan_rest_requires_login():
    assert client.get("/api/market/dhan/status").status_code == 401
    r = client.get("/api/market/dhan/status", headers={"Authorization": f"Bearer {_session_token()}"})
    assert r.status_code == 200


def test_chat_and_transcribe_rate_limited():
    from routers import chat

    async def always_limited(*_):
        return True

    real, chat.is_rate_limited = chat.is_rate_limited, always_limited
    try:
        token = _session_token()
        with client.websocket_connect(f"/api/chat/ws?token={token}") as ws:
            ws.send_json({"message": "RELIANCE price"})
            assert ws.receive_json()["detail"] == chat.RATE_LIMITED_DETAIL
        r = client.post("/api/chat/transcribe", files={"audio": ("a.webm", b"0", "audio/webm")},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 429
    finally:
        chat.is_rate_limited = real


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
