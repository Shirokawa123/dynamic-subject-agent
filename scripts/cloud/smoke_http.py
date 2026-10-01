"""Validate the repository's offline loopback lab without external requests."""
import json
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

base = sys.argv[1].rstrip("/")
parsed = urlparse(base)
assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
assert parsed.port and not parsed.username and not parsed.password
assert parsed.path == "" and not parsed.query and not parsed.fragment

with urlopen(base + "/status", timeout=5) as response:
    initial = json.load(response)
assert initial["status"] == "ready" and initial["mode"] == "offline"
assert initial["attempts"] < 20

with urlopen(base + "/", timeout=5) as response:
    assert response.status == 200
    page = response.read().decode("utf-8")
    token = re.search(r"const token='([^']+)'", page).group(1)

payload = dict(
    lab_id=initial["lab_id"],
    revision=initial["revision"],
    idempotency_key=uuid4().hex,
    message="云环境离线联调检查",
    use_history=False,
)
request = Request(
    base + "/send",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "X-Lab-Token": token},
)
with urlopen(request, timeout=10) as response:
    result = json.load(response)
assert result["status"] == "replied" and result["mode"] == "offline"
assert result["reply_text"] == "离线联调已收到消息。这是固定测试回声，不是纱雾的生成回复。"
assert result["revision"] == initial["revision"] + 1
assert result["attempts"] == initial["attempts"] + 1

with urlopen(request, timeout=10) as response:
    assert json.load(response) == result
with urlopen(base + "/status", timeout=5) as response:
    current = json.load(response)
assert current["revision"] == result["revision"]
assert current["attempts"] == result["attempts"]
assert current["history_enabled"] is False
print("Offline HTTP smoke passed: page, expected echo, replay and history control")
