"""Check the deployed build and database-backed CRUD without touching other tasks."""
import argparse
import json
import re
import time
import uuid
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class Cards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = []
        self.depth = 0
        self.card = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            if self.card is not None:
                self.depth += 1
            elif "task-card" in attrs.get("class", "").split():
                self.card = {"text": [], "delete": None}
                self.depth = 1
        if self.card is not None and tag == "form":
            action = attrs.get("action", "")
            if re.fullmatch(r"/delete/\d+", action):
                self.card["delete"] = action

    def handle_data(self, data):
        if self.card is not None:
            self.card["text"].append(data.strip())

    def handle_endtag(self, tag):
        if tag == "div" and self.card is not None:
            self.depth -= 1
            if self.depth == 0:
                self.cards.append(self.card)
                self.card = None


def request(base, path, data=None):
    payload = None if data is None else urlencode(data).encode()
    with urlopen(Request(base.rstrip("/") + path, data=payload), timeout=10) as response:
        return response.read().decode()


def find_task(html, title):
    parser = Cards()
    parser.feed(html)
    matches = [c for c in parser.cards if title in c["text"]]
    if len(matches) > 1:
        raise RuntimeError("Smoke task is not unique")
    return matches[0]["delete"] if matches else None


def wait_ready(base, build_id, seconds=90):
    deadline = time.monotonic() + seconds
    while True:
        try:
            health = json.loads(request(base, "/health"))
            if health.get("status") == "healthy" and health.get("build_id") == build_id:
                request(base, "/")  # Unlike /health, this exercises a database read.
                return
        except Exception:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("Expected build did not become ready")
        time.sleep(2)


def smoke(base, build_id):
    health = json.loads(request(base, "/health"))
    if health.get("status") != "healthy" or health.get("build_id") != build_id:
        raise RuntimeError("Unexpected deployed build")
    request(base, "/")
    title = "pipeline-smoke-" + uuid.uuid4().hex
    failure = None
    try:
        request(base, "/add", {"title": title, "assignee": "pipeline-smoke"})
        if not find_task(request(base, "/"), title):
            raise RuntimeError("Smoke task was not persisted")
    except Exception as exc:
        failure = exc
    finally:
        try:
            # Re-query even when the add request failed: it might have committed.
            action = find_task(request(base, "/"), title)
            if action:
                request(base, action, {})
                if find_task(request(base, "/"), title):
                    raise RuntimeError("Smoke task cleanup failed")
        except Exception as exc:
            print("Smoke task cleanup failed; inspect the deployment report.")
            if failure is None:
                failure = exc
    if failure:
        raise failure


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--build-id", required=True)
    args = parser.parse_args()
    wait_ready(args.url, args.build_id)
    smoke(args.url, args.build_id)
    print("Smoke test passed; test task removed.")
