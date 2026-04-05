#!/usr/bin/env python3
"""
Trust Graph local API server.
"""

import json
import sys
import textwrap
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
WHITE = "\033[97m"

PLATFORM_COLOUR = {
    "twitter": CYAN,
    "x": CYAN,
    "reddit": "\033[38;5;208m",
    "instagram": MAGENTA,
    "generic": DIM + WHITE,
}


def c(colour, text):
    return f"{colour}{text}{RESET}"


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, int(round(value))))


def section(title):
    bar = "-" * (len(title) + 4)
    print(f"\n{c(DIM, '.' + bar + '.')}")
    print(f"{c(DIM, '|')}  {c(BOLD + WHITE, title)}  {c(DIM, '|')}")
    print(c(DIM, "'" + bar + "'"))


def wrap_text(text, width=84, indent=4):
    if not text:
        return c(DIM, "  (empty)")
    lines = text.split("\n")
    result = []
    pad = " " * indent
    for line in lines:
        wrapped = textwrap.wrap(line, width - indent) or [""]
        result.extend(pad + item for item in wrapped)
    return "\n".join(result)


def compact_url(value, fallback=""):
    return value or fallback or ""


def normalize_payload(payload):
    platform = (payload.get("platform") or "generic").lower()

    if "post" in payload or "engagement" in payload or isinstance(payload.get("author"), dict):
        author_block = payload.get("author") or {}
        post_block = payload.get("post") or {}
        media = post_block.get("media") or {}
        comments = payload.get("comments") or []

        return {
            "platform": "x" if platform == "twitter" else platform,
            "url": payload.get("url") or "",
            "text": post_block.get("text") or payload.get("text") or "",
            "title": payload.get("title") or "",
            "author_name": author_block.get("name") or "",
            "author_handle": author_block.get("handle") or "",
            "author_profile": compact_url(author_block.get("profile_url")),
            "timestamp": post_block.get("created_at") or payload.get("timestamp") or "",
            "images": media.get("images") or payload.get("images") or [],
            "videos": media.get("videos") or ([] if not payload.get("vid_url") else [payload.get("vid_url")]),
            "likes": (payload.get("engagement") or {}).get("likes"),
            "comments_total": (payload.get("engagement") or {}).get("comments"),
            "shares": (payload.get("engagement") or {}).get("shares"),
            "comments_items": comments,
            "reactions": payload.get("reactions") or [],
            "metadata": payload.get("metadata") or {},
            "raw": payload,
        }

    user = payload.get("user") or {}
    comments_block = payload.get("comments") or {}
    comment_items = comments_block.get("items") if isinstance(comments_block, dict) else comments_block

    return {
        "platform": platform,
        "url": payload.get("url") or "",
        "text": payload.get("text") or "",
        "title": payload.get("title") or "",
        "author_name": payload.get("author") or user.get("name") or "",
        "author_handle": user.get("handle") or "",
        "author_profile": compact_url(user.get("profile_link")),
        "timestamp": payload.get("timestamp") or "",
        "images": payload.get("images") or ([payload.get("image_url")] if payload.get("image_url") else []),
        "videos": [payload.get("vid_url")] if payload.get("vid_url") else [],
        "likes": payload.get("nbre_of_reacts"),
        "comments_total": comments_block.get("total") if isinstance(comments_block, dict) else len(comment_items or []),
        "shares": payload.get("shares"),
        "comments_items": comment_items or [],
        "reactions": payload.get("reactions") or [],
        "metadata": payload.get("metadata") or {},
        "raw": payload,
    }


def print_payload(payload):
    data = normalize_payload(payload)
    platform = data["platform"]
    platform_col = PLATFORM_COLOUR.get(platform, WHITE)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    text_len = len(data["text"])

    print()
    print(c(BOLD, "=" * 74))
    print(c(BOLD + WHITE, " TRUST GRAPH - SCRAPED PAYLOAD"))
    print(c(DIM, f" received at {timestamp}"))
    print(c(BOLD, "=" * 74))

    section("SOURCE")
    print(f"  {c(DIM, 'platform:')}  {c(platform_col, platform.upper())}")
    print(f"  {c(DIM, 'url:')}       {c(CYAN, data['url'])}")
    print(f"  {c(DIM, 'author:')}    {c(GREEN, data['author_name'] or 'unknown')}")
    if data["author_handle"]:
        print(f"  {c(DIM, 'handle:')}    {c(YELLOW, data['author_handle'])}")
    if data["author_profile"]:
        print(f"  {c(DIM, 'profile:')}   {c(CYAN, data['author_profile'])}")

    section("CONTENT")
    if data["title"]:
        print(f"  {c(DIM, 'title:')}     {c(WHITE, data['title'])}")
    if data["timestamp"]:
        print(f"  {c(DIM, 'posted:')}    {c(GREEN, data['timestamp'])}")
    print(f"  {c(DIM, 'text:')}      {c(DIM, f'({text_len} chars)')}")
    print(wrap_text(data["text"]))

    if data["images"]:
        print(f"  {c(DIM, 'images:')}")
        for img in data["images"][:5]:
            print(f"    {c(CYAN, '->')} {c(DIM, img)}")

    if data["videos"]:
        print(f"  {c(DIM, 'videos:')}")
        for vid in data["videos"][:3]:
            print(f"    {c(CYAN, '->')} {c(DIM, vid)}")

    section("ENGAGEMENT")
    print(f"  {c(DIM, 'likes:')}     {c(GREEN, data['likes'] if data['likes'] is not None else 'n/a')}")
    print(f"  {c(DIM, 'comments:')}  {c(YELLOW, data['comments_total'] if data['comments_total'] is not None else 'n/a')}")
    print(f"  {c(DIM, 'shares:')}    {c(BLUE, data['shares'] if data['shares'] is not None else 'n/a')}")

    if data["reactions"]:
        section("REACTIONS")
        for reaction in data["reactions"]:
            reaction_type = reaction.get("type", "reaction")
            count = reaction.get("count", 0)
            print(f"  {c(DIM, reaction_type + ':')}  {c(CYAN, count)}")
            top_users = reaction.get("top_users") or []
            for user in top_users[:5]:
                username = user.get("username") or "unknown"
                reaction_count = user.get("reaction_count")
                suffix = f" ({reaction_count})" if reaction_count not in (None, "") else ""
                reaction_type_label = user.get("reaction_type")
                label = f" [{reaction_type_label}]" if reaction_type_label else ""
                print(f"    {c(YELLOW, username)}{c(DIM, suffix + label)}")

    section(f"COMMENTS ({len(data['comments_items'])} shown)")
    if not data["comments_items"]:
        print(f"  {c(DIM, '(none)')}")
    for index, comment in enumerate(data["comments_items"][:10], 1):
        author = comment.get("author")
        if isinstance(author, dict):
            author_label = author.get("name") or author.get("handle") or "unknown"
        else:
            author_label = author or "unknown"
        depth = comment.get("depth") or 0
        indent = 2 + (depth * 2)
        prefix = (" " * indent) + f"{index}."
        relation = f" -> {comment.get('parent_id')}" if comment.get("parent_id") else ""
        print(f"{c(DIM, prefix)} {c(YELLOW, author_label)}{c(DIM, relation)}")
        print(wrap_text(comment.get("text", ""), indent=indent + 4))

    print(c(DIM, "-" * 74))
    print(c(DIM, "RAW JSON:"))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(c(DIM, "-" * 74))


def build_platform_explanation(data, verdict, trust_score, grounded_hits, suspicious_hits):
    platform = data["platform"]
    subject = {
        "reddit": "Reddit post",
        "instagram": "Instagram post",
        "x": "X post",
        "twitter": "Twitter post",
    }.get(platform, "post")

    if verdict == "trusted":
        tone = "The extracted content looks fairly grounded."
    elif verdict == "uncertain":
        tone = "The extracted content is mixed and needs verification."
    else:
        tone = "The extracted content shows several low-trust signals."

    platform_notes = {
        "reddit": f"This {subject} includes subreddit/post details and text context that help with interpretation.",
        "instagram": f"This {subject} relies more on caption/media context, so claims should be checked outside the app.",
        "x": f"This {subject} was scored using the tweet text, author block, media, and visible engagement signals.",
        "twitter": f"This {subject} was scored using the tweet text, author block, media, and visible engagement signals.",
    }

    signal_line = f"Positive grounding signals: {grounded_hits}. Suspicious pattern hits: {suspicious_hits}. Score: {trust_score}/100."
    explanation = " ".join([
        tone,
        platform_notes.get(platform, "The score is based only on what the extension could extract from the visible post."),
        signal_line,
    ])

    title = {
        "trusted": "Looks fairly credible",
        "uncertain": "Needs a second check",
        "suspicious": "High caution recommended",
    }[verdict]

    return title, explanation


def build_preview(data):
    preview = data["text"] or data["title"] or data["url"]
    return preview[:220]


def build_content_meta(data):
    bits = []
    if data["author_name"]:
        bits.append(f"Author: {data['author_name']}")
    if data["author_handle"]:
        bits.append(f"Handle: {data['author_handle']}")
    if data["metadata"].get("subreddit"):
        bits.append(f"Subreddit: {data['metadata']['subreddit']}")
    if data["likes"] is not None:
        bits.append(f"Likes: {data['likes']}")
    if data["comments_total"] is not None:
        bits.append(f"Comments: {data['comments_total']}")
    if data["images"]:
        bits.append(f"Images: {len(data['images'])}")
    if data["videos"]:
        bits.append(f"Videos: {len(data['videos'])}")
    if data["reactions"]:
        bits.append(", ".join(
            f"{reaction.get('type', 'reaction')}: {reaction.get('count', 0)}"
            for reaction in data["reactions"]
        ))
    return bits




def build_reaction_summary(data):
    summary = []
    for reaction in data["reactions"]:
        summary.append({
            "type": reaction.get("type", "reaction"),
            "count": reaction.get("count", 0),
            "top_users": [
                {
                    "username": user.get("username") or "unknown",
                    "reaction_type": user.get("reaction_type") or reaction.get("type", "reaction"),
                    "reaction_count": user.get("reaction_count", 0),
                }
                for user in (reaction.get("top_users") or [])[:5]
            ],
        })
    return summary

def truncate_label(value):
    return value if len(value) <= 18 else value[:15] + "..."


def platform_label(platform):
    return {
        "reddit": "Reddit Post",
        "instagram": "Instagram Post",
        "x": "X Post",
        "twitter": "Twitter Post",
    }.get(platform, "Post")


def score_payload(payload):
    data = normalize_payload(payload)
    text = "\n".join([
        data["title"],
        data["text"],
        data["author_name"],
        data["author_handle"],
        data["url"],
    ]).strip()
    lower = text.lower()

    suspicious_terms = [
        "breaking",
        "urgent",
        "shocking",
        "secret",
        "share now",
        "they don't want you to know",
        "100% true",
        "guaranteed",
        "miracle",
    ]
    grounded_terms = [
        "source",
        "study",
        "report",
        "official",
        "data",
        "evidence",
        "analysis",
        "according to",
    ]

    suspicious_hits = sum(term in lower for term in suspicious_terms)
    grounded_hits = sum(term in lower for term in grounded_terms)
    image_bonus = min(len(data["images"]), 3) * 3
    comment_bonus = min(data["comments_total"] or 0, 20) * 0.4
    reaction_total = sum((reaction.get("count") or 0) for reaction in data["reactions"])
    reaction_bonus = min(reaction_total, 500) / 60
    detail_bonus = min(len(text), 1200) / 70

    trust_score = clamp(50 + grounded_hits * 8 + image_bonus + comment_bonus + reaction_bonus + detail_bonus - suspicious_hits * 12, 10, 95)
    authenticity = clamp(trust_score + 5 - suspicious_hits * 3)
    context = clamp(trust_score + grounded_hits * 3 - suspicious_hits * 2)
    source = clamp(trust_score + 4 + (2 if data["author_name"] else -3) + grounded_hits * 2 - suspicious_hits * 4)

    if trust_score >= 70:
        verdict = "trusted"
    elif trust_score >= 40:
        verdict = "uncertain"
    else:
        verdict = "suspicious"

    summary_title, explanation = build_platform_explanation(data, verdict, trust_score, grounded_hits, suspicious_hits)

    return {
        "trust_score": trust_score,
        "verdict": verdict,
        "subscores": {
            "authenticity": authenticity,
            "context": context,
            "source": source,
        },
        "summary_title": summary_title,
        "explanation": explanation,
        "graph_nodes": [
            {"id": "post", "label": platform_label(data["platform"]), "score": trust_score, "type": "post"},
            {"id": "source", "label": truncate_label(data["author_name"] or "Source"), "score": source, "type": "source"},
            {"id": "claim", "label": "Claim", "score": authenticity, "type": "claim"},
            {"id": "context", "label": "Context", "score": context, "type": "context"},
        ],
        "graph_edges": [
            {"from": "source", "to": "post", "weight": 0.8},
            {"from": "post", "to": "claim", "weight": 0.65},
            {"from": "post", "to": "context", "weight": 0.72},
        ],
        "metadata": {
            "mock": False,
            "platform": data["platform"],
            "received_at": datetime.now(timezone.utc).isoformat(),
            "content_preview": build_preview(data),
            "content_meta": build_content_meta(data),
            "reactions": build_reaction_summary(data),
        },
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "TrustGraphApi/0.2"

    def do_OPTIONS(self):
        self._send_json(204, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_json(200, {
                "service": "trust-graph-api",
                "status": "ok",
                "endpoints": ["/health", "/analyze", "/extract"],
            })
            return
        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "service": "trust-graph-api"})
            return
        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/analyze", "/extract"):
            self._send_json(404, {"error": "Not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        if not isinstance(payload, dict):
            self._send_json(400, {"error": "Payload must be a JSON object"})
            return

        print_payload(payload)

        if parsed.path == "/extract":
            self._send_json(200, {"status": "ok", "received": True})
            return

        self._send_json(200, score_payload(payload))

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(c(BOLD + GREEN, f"\n  Trust Graph API listening on http://{HOST}:{PORT}"))
    print(c(DIM, "  GET  /health   -> server health"))
    print(c(DIM, "  POST /analyze  -> print payload + return analysis JSON"))
    print(c(DIM, "  POST /extract  -> print payload only\n"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(c(DIM, "\n  server stopped."))
