# Trust Graph API

Small local API server for the browser extension.

## Run

```powershell
python api\server.py
```

The server starts on `http://127.0.0.1:8000`.

## Endpoints

### `GET /health`

Returns:

```json
{
  "status": "ok",
  "service": "trust-graph-api"
}
```

### `POST /analyze`

Accepts the scraped payload from the extension and returns analysis JSON in the shape the popup/content overlay already expects.

Example request:

```json
{
  "platform": "instagram",
  "url": "https://instagram.com/p/example",
  "text": "Breaking news example post",
  "author": "demo_account"
}
```
