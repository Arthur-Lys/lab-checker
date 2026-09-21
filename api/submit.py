"""Proxy one submission to the teacher's checker and return the verdict as JSON (the browser can't call it directly).
A pass is a redirect into the quiz: the session cookie and the first question come back so the page can drive
the test through api/quiz.py."""

import html as htmllib
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

BASE = "https://laboratory-checker-actions.onrender.com"
CHECKER = BASE + "/quiz/start"
FIELDS = ("student_name", "course", "group", "lab", "repository")


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style).*?</\1>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    return "\n".join(line.strip() for line in htmllib.unescape(text).splitlines() if line.strip())


def parse_question(html: str) -> dict | None:
    """The quiz page: 'Питання N із T', an <h2>, four labelled radio options."""
    progress = re.search(r"Питання\s+(\d+)\s+із\s+(\d+)", html)
    question = re.search(r"<h2>\s*(.*?)\s*</h2>", html, re.S)
    options = re.findall(r"<strong>([A-Z])\.</strong>\s*(.*?)\s*</label>", html, re.S)
    if not (progress and question and options):
        return None
    clean = lambda s: re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", s))).strip()
    return {"n": int(progress.group(1)), "total": int(progress.group(2)), "q": clean(question.group(1)),
            "opts": [{"k": k, "t": clean(t)} for k, t in options]}


def submit(form: dict) -> dict:
    body = urllib.parse.urlencode({k: str(form.get(k, "")).strip() for k in FIELDS}).encode()
    req = urllib.request.Request(CHECKER, data=body, headers={"content-type": "application/x-www-form-urlencoded"})
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    started = time.perf_counter()
    url = CHECKER
    try:
        with opener.open(req, timeout=55) as resp:
            status, html, url = resp.status, resp.read().decode("utf-8", "replace"), resp.geturl()
    except urllib.error.HTTPError as error:
        status, html = error.code, error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        status, html = 0, f"Error: {error.reason}"
    out = {"status": status, "seconds": round(time.perf_counter() - started, 1), "text": strip_html(html)}
    if url.endswith("/quiz/question"):
        out.update(passed=True, session=next((c.value for c in jar if c.name == "session"), None),
                   question=parse_question(html),
                   text="До захисту ДОПУЩЕНО. Статус звіту: OK. Тест розпочато.\n" + out["text"])
    return out


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
