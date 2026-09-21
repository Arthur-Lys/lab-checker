"""Drive one quiz session on the teacher's server. Body: {"session": cookie, "answer": "A".."D" (optional)}.
No answer -> the current question (the server's GET is idempotent); an answer -> the next question, or the result
once the 50th is in. The session cookie is the browser's to keep: Vercel functions hold nothing between calls."""

import html as htmllib
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

BASE = "https://laboratory-checker-actions.onrender.com"
HOST = "laboratory-checker-actions.onrender.com"
QUESTION = BASE + "/quiz/question"
LABELS = {"Код": "code", "Звіт": "report", "Статус звіту": "status", "Тест": "test", "Разом": "total",
          "Підсумкова оцінка": "grade", "Варіант:": "variant"}


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style).*?</\1>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    return "\n".join(line.strip() for line in htmllib.unescape(text).splitlines() if line.strip())


def parse_question(html: str) -> dict | None:
    progress = re.search(r"Питання\s+(\d+)\s+із\s+(\d+)", html)
    question = re.search(r"<h2>\s*(.*?)\s*</h2>", html, re.S)
    options = re.findall(r"<strong>([A-Z])\.</strong>\s*(.*?)\s*</label>", html, re.S)
    if not (progress and question and options):
        return None
    clean = lambda s: re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", s))).strip()
    return {"n": int(progress.group(1)), "total": int(progress.group(2)), "q": clean(question.group(1)),
            "opts": [{"k": k, "t": clean(t)} for k, t in options]}


def parse_result(html: str) -> dict:
    """The result page is label / value pairs; 'X / Y' values become numbers, the grade is the lab's points."""
    lines = strip_html(html).splitlines()
    out = {}
    for i, line in enumerate(lines):
        key = LABELS.get(line)
        if not key or i + 1 >= len(lines):
            continue
        value = lines[i + 1]
        if i + 3 < len(lines) and lines[i + 2] == "/":
            value = f"{value} / {lines[i + 3]}"
        pair = re.fullmatch(r"(\d+)\s*/\s*(\d+)", value)
        out[key] = {"got": int(pair.group(1)), "max": int(pair.group(2))} if pair else (int(value) if value.isdigit() else value)
    return out


def call(session: str, answer: str | None) -> dict:
    jar = http.cookiejar.CookieJar()
    jar.set_cookie(http.cookiejar.Cookie(0, "session", session, None, False, HOST, True, False, "/", True, True,
                                         None, True, None, None, {}))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = urllib.parse.urlencode({"answer": answer}).encode() if answer else None
    req = urllib.request.Request(QUESTION, data=body,
                                 headers={"content-type": "application/x-www-form-urlencoded"} if body else {})
    url = QUESTION
    try:
        with opener.open(req, timeout=55) as resp:
            status, html, url = resp.status, resp.read().decode("utf-8", "replace"), resp.geturl()
    except urllib.error.HTTPError as error:
        status, html = error.code, error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        return {"error": f"Сервер викладача не відповів: {error.reason}", "status": 0}
    if url.endswith("/quiz/result"):
        return {"done": True, "result": parse_result(html), "status": status}
    if url.endswith("/quiz/question") and status == 200:
        question = parse_question(html)
        if question:
            return {"done": False, "question": question, "status": status}
        return {"error": "Не зміг прочитати сторінку питання.", "status": status, "text": strip_html(html)[:400]}
    if status == 400:
        return {"error": strip_html(html)[:200] or "Сервер відхилив відповідь.", "status": status}
    if url.rstrip("/") == BASE:
        return {"expired": True, "status": status}
    return {"error": f"Несподівана відповідь ({status}).", "status": status, "text": strip_html(html)[:400]}


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0)) or b"{}"))
        except ValueError:
            return self._send(400, {"error": "bad json"})
        session = str(body.get("session") or "").strip()
        answer = str(body.get("answer") or "").strip().upper() or None
        if not session:
            return self._send(400, {"error": "no session"})
        if answer and answer not in ("A", "B", "C", "D"):
            return self._send(400, {"error": "answer must be A-D"})
        self._send(200, call(session, answer))

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
