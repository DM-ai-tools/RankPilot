"""Runway API — text-to-image (Gemini / Nano Banana family via Runway)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_IMAGE_SIZE_TO_RATIO = {
    "1K": "1024:1024",
    "2K": "2048:2048",
    "4K": "4096:4096",
}
_FALLBACK_IMAGE_MODELS = ("gemini_2.5_flash", "gemini_image3.1_flash", "gen4_image", "gemini_image3_pro")
# Minimum credits per successful image (see https://docs.dev.runwayml.com/guides/pricing/)
_MODEL_MIN_CREDITS: dict[str, int] = {
    "gemini_2.5_flash": 5,
    "gemini_image3.1_flash": 5,
    "gemini_image3_pro": 20,
    "gen4_image": 5,
    "gen4_image_turbo": 2,
    "gpt_image_2": 1,
}
_DEFAULT_MIN_CREDITS = 5


class RunwayService:
    def __init__(self, settings: Settings | None = None):
        self._s = settings or get_settings()
        base = (self._s.runwayml_base_url or "https://api.dev.runwayml.com/v1").rstrip("/")
        self._base = base
        self._version = (self._s.runwayml_api_version or "2024-11-06").strip()
        self._api_key = (self._s.runwayml_api_key or "").strip()

    def configured(self) -> bool:
        return bool(self._api_key)

    async def credit_balance(self, http: httpx.AsyncClient | None = None) -> int | None:
        """Return API credit balance from GET /organization (dev.runwayml.com credits only)."""
        if not self.configured():
            return None
        owns = http is None
        client = http or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))
        try:
            r = await client.get(f"{self._base}/organization", headers=self._headers())
            if not r.is_success:
                return None
            data = r.json() if isinstance(r.json(), dict) else {}
            bal = data.get("creditBalance")
            return int(bal) if bal is not None else None
        except Exception:
            return None
        finally:
            if owns:
                await client.aclose()

    def _min_credits_for_models(self, models: list[str]) -> int:
        mins = [_MODEL_MIN_CREDITS.get(m, _DEFAULT_MIN_CREDITS) for m in models]
        return min(mins) if mins else _DEFAULT_MIN_CREDITS

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "X-Runway-Version": self._version,
            "Content-Type": "application/json",
        }

    def _ratio(self) -> str:
        size = (self._s.runwayml_image_size or "1K").strip().upper()
        return _IMAGE_SIZE_TO_RATIO.get(size, "1024:1024")

    async def text_to_image(self, prompt: str) -> dict[str, Any]:
        """Create task, poll until done, return { task_id, output_urls }."""
        if not self.configured():
            raise ValueError("RUNWAYML_API_KEY is not configured in backend/.env")

        prompt_text = (prompt or "").strip()
        if not prompt_text:
            raise ValueError("Image prompt is required")

        primary = (self._s.runwayml_model_image or "gemini_2.5_flash").strip()
        models = [primary, *[m for m in _FALLBACK_IMAGE_MODELS if m != primary]]
        last_err = ""
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=20.0)) as http:
            balance = await self.credit_balance(http)
            need = self._min_credits_for_models(models)
            if balance is not None and balance < need:
                raise ValueError(
                    f"Runway API credit balance is {balance} credits, but image generation needs at least "
                    f"{need} credits for the configured models. Add credits at https://dev.runwayml.com "
                    f"(Billing tab). Note: credits on app.runwayml.com are separate and do not apply to the API."
                )
            for model in models:
                try:
                    task_id = await self._create_task(http, model, prompt_text)
                    output = await self._poll_task(http, task_id)
                    return {"task_id": task_id, "model": model, "output_urls": output}
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    logger.warning("Runway model %s failed: %s", model, exc)
            raise RuntimeError(last_err or "Runway image generation failed")

    def _text_to_image_body(self, model: str, prompt_text: str) -> dict[str, Any]:
        """Build request body; Gemini models require referenceImages (may be empty)."""
        body: dict[str, Any] = {
            "model": model,
            "promptText": prompt_text,
            "ratio": self._ratio(),
        }
        m = (model or "").lower()
        if m.startswith("gemini") or m.startswith("gpt_image") or "nano" in m:
            body["referenceImages"] = []
        return body

    async def _create_task(self, http: httpx.AsyncClient, model: str, prompt_text: str) -> str:
        body = self._text_to_image_body(model, prompt_text)
        r = await http.post(f"{self._base}/text_to_image", headers=self._headers(), json=body)
        if not r.is_success:
            msg = ""
            try:
                msg = str(r.json())
            except Exception:
                msg = r.text
            raise RuntimeError(f"Runway text_to_image {r.status_code}: {msg[:500]}")
        data = r.json()
        task = (data.get("task") or data) if isinstance(data, dict) else {}
        task_id = str(task.get("id") or data.get("id") or "").strip()
        if not task_id:
            raise RuntimeError(f"Runway returned no task id: {data!s}"[:300])
        return task_id

    async def _poll_task(self, http: httpx.AsyncClient, task_id: str) -> list[str]:
        for attempt in range(60):
            r = await http.get(f"{self._base}/tasks/{task_id}", headers=self._headers())
            if not r.is_success:
                raise RuntimeError(f"Runway task poll {r.status_code}: {r.text[:300]}")
            data = r.json() if isinstance(r.json(), dict) else {}
            status = str(data.get("status") or "").upper()
            if status in ("SUCCEEDED", "SUCCESS", "COMPLETED"):
                out = data.get("output") or data.get("outputs") or []
                urls = [str(u) for u in out if u] if isinstance(out, list) else []
                if urls:
                    return urls
                raise RuntimeError("Runway task succeeded but returned no image URLs")
            if status in ("FAILED", "CANCELLED", "CANCELED"):
                err = data.get("failure") or data.get("error") or data.get("failureCode") or status
                raise RuntimeError(f"Runway task failed: {err}")
            await asyncio.sleep(3 if attempt < 10 else 5)
        raise TimeoutError("Runway image generation timed out (try again)")
