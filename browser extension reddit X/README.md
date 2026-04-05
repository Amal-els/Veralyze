# Trust Graph

Trust Graph is a Chrome extension plus a small local API server for extracting social post data from Reddit, Instagram, and X/Twitter, then returning a structured JSON trust analysis.

The extension lets you turn on an inspector-style extraction mode, hover a supported post, click it, and send the scraped payload to the backend. The API prints the payload, returns analysis JSON, and the extension displays the result in both the popup and the in-page overlay.

## Features

- Works on Reddit, Instagram, X, and Twitter
- Toggle-based Extraction Mode so browsing stays normal until you turn it on
- Hover highlight plus click-to-analyze interaction
- Saves the raw extracted payload and the last analysis result in extension storage
- Platform-aware reaction extraction
- Reddit comment hierarchy support with `parent_id`, `depth`, and nested `thread`
- Reddit fallback hydration: if comments are not visible in feed view, the extension can open the post URL in a background tab, extract the full thread, and merge it back into the payload
- Local API server that returns analysis JSON in the shape the extension already expects

## Project Structure

```text
.
|-- api/                  Local analysis server
|-- assets/               Icons and visual assets
|-- background/           MV3 service worker
|-- content/              Content script + platform extractors
|-- options/              Extension settings page
|-- popup/                Extension popup UI
|-- scripts/              Utility scripts
|-- manifest.json         Chrome extension manifest
```

## Supported Platforms

### Reddit

- Extracts title, body text, author, subreddit, images, score, permalink, comments, and reaction summary
- Reactions include:
  - `upvotes`
  - `comments`
- Comment payload includes:
  - flat `items`
  - nested `thread`
  - `id`
  - `parent_id`
  - `depth`

### Instagram

- Extracts caption, author, profile link, images, video URL, hashtags, comments, and reaction summary
- Reactions include:
  - `likes`
  - `comments`

### X / Twitter

- Extracts tweet text, author, handle, media, reply count, repost count, likes, and visible reply data
- Reactions include:
  - `likes`
  - `replies`
  - `reposts`

## Requirements

- Google Chrome or another Chromium browser that supports Manifest V3
- Python 3 for the local API server

## Setup

### 1. Start the API server

From the project root:

```powershell
python api\server.py
```

Default server URL:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

## 2. Load the extension in Chrome

1. Open `chrome://extensions`
2. Turn on Developer mode
3. Click `Load unpacked`
4. Select this project folder
5. Reload the extension after code changes

## 3. Configure the API URL

The extension defaults to `http://localhost:8000`.

If needed:

1. Open the extension popup
2. Go to Settings
3. Set the API URL to `http://127.0.0.1:8000` or `http://localhost:8000`

## Usage

### Extraction Mode

1. Click the extension icon
2. Turn on `Extraction Mode`
3. Open Reddit, Instagram, or X/Twitter
4. Hover a post until it highlights
5. Click the highlighted post

When Extraction Mode is off, the extension stays passive and does not intercept clicks.

### What happens after click

1. The content script extracts platform-specific post data
2. The background service worker optionally enriches the payload
3. The payload is sent to `POST /analyze`
4. The API returns analysis JSON
5. The extension saves:
   - `lastPayload`
   - `lastResult`
6. The result appears in the page overlay and popup

## Stored Data

The extension stores the latest extraction locally in `chrome.storage.local`.

Keys:

- `lastPayload`
- `lastResult`

You can inspect them from the extension context with:

```js
chrome.storage.local.get(['lastPayload', 'lastResult']).then(console.log)
```

## API Overview

### `GET /`

Returns a small JSON description of the service.

### `GET /health`

Returns:

```json
{
  "status": "ok",
  "service": "trust-graph-api"
}
```

### `POST /analyze`

Accepts scraped extension payloads and returns analysis JSON, including:

- `trust_score`
- `verdict`
- `subscores`
- `summary_title`
- `explanation`
- `graph_nodes`
- `graph_edges`
- `metadata`

### `POST /extract`

Prints the payload and acknowledges receipt without scoring.

## Example Payload Shape

```json
{
  "platform": "reddit",
  "url": "https://www.reddit.com/r/example/comments/abc123/example_post/",
  "title": "Example post",
  "text": "Example post body",
  "author": "example_user",
  "comments": {
    "total": 2,
    "items": [
      {
        "id": "comment-1",
        "parent_id": null,
        "depth": 0,
        "text": "Top level comment",
        "author": "user_a",
        "reacts_count": 12
      },
      {
        "id": "comment-2",
        "parent_id": "comment-1",
        "depth": 1,
        "text": "Reply to top level comment",
        "author": "user_b",
        "reacts_count": 4
      }
    ],
    "thread": []
  },
  "reactions": [
    {
      "type": "upvotes",
      "count": 120,
      "top_users": []
    },
    {
      "type": "comments",
      "count": 2,
      "top_users": [
        {
          "username": "user_a",
          "reaction_type": "comment",
          "reaction_count": 12
        }
      ]
    }
  ]
}
```

## Development Notes

- Manifest version: MV3
- Background logic lives in [background/service_worker.js](/c:/AI/Hackathons/browser%20extension%20reddit%20X/background/service_worker.js)
- Main page interaction lives in [content.js](/c:/AI/Hackathons/browser%20extension%20reddit%20X/content/content.js)
- Platform extractors live in:
  - [reddit.js](/c:/AI/Hackathons/browser%20extension%20reddit%20X/content/extractors/reddit.js)
  - [instagram.js](/c:/AI/Hackathons/browser%20extension%20reddit%20X/content/extractors/instagram.js)
  - [twitter.js](/c:/AI/Hackathons/browser%20extension%20reddit%20X/content/extractors/twitter.js)
- Local backend lives in [server.py](/c:/AI/Hackathons/browser%20extension%20reddit%20X/api/server.py)

## Troubleshooting

### The extension popup opens, but nothing highlights

- Make sure `Extraction Mode` is enabled
- Reload the extension in `chrome://extensions`
- Refresh the active social media tab

### Reddit feed posts do not show comments

- The extension now tries to hydrate comments from the actual post URL
- If it still fails, open the post directly and extract again
- Some Reddit page variants expose less DOM data than others

### X/Twitter does not respond

- Reload the extension
- Refresh the `x.com` or `twitter.com` tab
- Confirm you are hovering an actual tweet card, not a sidebar/trending module

### API is running but `/` shows JSON or 404 behavior changed

- Use `/health` for a guaranteed health endpoint
- Use `POST /analyze` for analysis requests

## License

No license file is currently included in this repository.
