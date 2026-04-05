import urllib.request
import json

data = {
    "platform": "twitter",
    "post": {
        "text": "Breaking news: Fake aliens landed!",
    },
    "author": {
        "name": "BotNet",
        "handle": "@botnet"
    },
    "comments": [
        {"text": "Fake news", "author": {"name": "Bob", "handle": "@bob"}},
        {"text": "Is this real?", "author": {"name": "Alice", "handle": "@alice"}}
    ]
}

req = urllib.request.Request(
    "http://127.0.0.1:8000/analyze",
    data=json.dumps(data).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print(f"Error: {e}")
