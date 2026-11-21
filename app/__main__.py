"""`uv run python -m app`: start the server on HN_PORT (default 8000), also on Windows without make."""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("HN_PORT") or 8000))
