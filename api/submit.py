"""Proxy one submission to the teacher's checker and return the verdict as JSON (the browser can't call it directly)."""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

CHECKER = "https://laboratory-checker-actions.onrender.com/quiz/start"
FIELDS = ("student_name", "course", "group", "lab", "repository")


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style).*?</\1>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def submit(form: dict) -> dict:
    body = urllib.parse.urlencode({k: str(form.get(k, "")).strip() for k in FIELDS}).encode()
    req = urllib.request.Request(CHECKER, data=body, headers={"content-type": "application/x-www-form-urlencoded"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=55) as resp:
            status, html = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        status, html = error.code, error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        status, html = 0, f"Error: {error.reason}"
    return {"status": status, "seconds": round(time.perf_counter() - started, 1), "text": strip_html(html)}


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            form = json.loads(self.rfile.read(int(self.headers.get("content-length", 0)) or b"{}"))
        except ValueError:
            return self._send(400, {"error": "bad json"})
        self._send(200, submit(form))

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
