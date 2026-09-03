"""OpenAI Images API — gpt-image-2 for GBP posts and Content Engine pages."""

from __future__ import annotations

import base64
import contextlib
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_openai_api_key, get_settings

logger = logging.getLogger(__name__)

# GBP posts: square. Website/suburb landing pages: landscape (~16:9).
OPENAI_SIZE_GBP = "1024x1024"
OPENAI_SIZE_WEBSITE = "1536x1024"

_OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


class OpenAIImageService:
    def __init__(self, settings: Settings | None = None):
        self._s = settings or get_settings()
        self._api_key = get_openai_api_key()
        self._model = (getattr(self._s, "openai_image_model", None) or "gpt-image-2").strip()
        self._quality = (getattr(self._s, "openai_image_quality", None) or "medium").strip() or "medium"

    def configured(self) -> bool:
        return bool(self._api_key)

    async def text_to_image(self, prompt: str, *, size: str | None = None) -> dict[str, Any]:
        """Generate an image; return { model, size, image_bytes }."""
        if not self.configured():
            raise ValueError("OPENAI_API_KEY is not configured in backend/.env")

        prompt_text = (prompt or "").strip()
        if not prompt_text:
            raise ValueError("Image prompt is required")

        # gpt-image-2 accepts long prompts; keep a sane upper bound for latency/cost.
        if len(prompt_text) > 8000:
            prompt_text = prompt_text[:7997].rstrip() + "..."

        out_size = (size or OPENAI_SIZE_GBP).strip() or OPENAI_SIZE_GBP
        quality = self._quality if self._quality in {"low", "medium", "high", "auto"} else "medium"

        body: dict[str, Any] = {
            "model": self._model or "gpt-image-2",
            "prompt": prompt_text,
            "size": out_size,
            "quality": quality,
            "n": 1,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=20.0)) as http:
            r = await http.post(_OPENAI_IMAGES_URL, headers=headers, json=body)

        if not r.is_success:
            detail = r.text[:500]
            with contextlib.suppress(Exception):
                err = r.json()
                if isinstance(err, dict):
                    eobj = err.get("error")
                    if isinstance(eobj, dict):
                        detail = str(eobj.get("message") or detail)
                    elif eobj:
                        detail = str(eobj)
            raise RuntimeError(f"OpenAI images.generate {r.status_code}: {detail}")

        data = r.json() if isinstance(r.json(), dict) else {}
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise RuntimeError("OpenAI returned no image data")

        first = rows[0] if isinstance(rows[0], dict) else {}
        b64 = str(first.get("b64_json") or "").strip()
        if not b64:
            # Some accounts may still return a temporary URL.
            url = str(first.get("url") or "").strip()
            if url:
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
                    img = await http.get(url)
                if not img.is_success:
                    raise RuntimeError("Failed to download OpenAI image URL")
                return {
                    "model": self._model,
                    "size": out_size,
                    "image_bytes": img.content,
                    "output_urls": [url],
                    "task_id": None,
                }
            raise RuntimeError("OpenAI response missing b64_json and url")

        try:
            image_bytes = base64.b64decode(b64)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to decode OpenAI image base64: {exc}") from exc

        if not image_bytes:
            raise RuntimeError("OpenAI returned empty image bytes")

        return {
            "model": self._model,
            "size": out_size,
            "image_bytes": image_bytes,
            "output_urls": [],
            "task_id": None,
        }
