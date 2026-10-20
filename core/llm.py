"""LLM abstraction layer: Gemini → Ollama → None fallback chain."""

import os
import json
import time
import requests
from typing import Optional, Dict, Any

# Gemini call tuning — Google's free tier can be slow under load.
# Kept short so a stalled LLM falls back to deterministic insights quickly
# (a chat response must arrive in seconds, not minutes).
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "10"))
GEMINI_MAX_ATTEMPTS = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "2"))
GEMINI_RETRY_DELAY = float(os.environ.get("GEMINI_RETRY_DELAY_SECONDS", "1"))


class LLMClient:
    """Tries Gemini first, then Ollama, then returns None (caller falls back)."""

    def __init__(self):
        self.gemini_key: str = os.environ.get("GEMINI_API_KEY", "")
        self.gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self.ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model: str = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self._ollama_ok: Optional[bool] = None  # cache probe

    # ── availability ────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return bool(self.gemini_key) or self._ollama_available()

    def _ollama_available(self) -> bool:
        if self._ollama_ok is not None:
            return self._ollama_ok
        try:
            r = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            self._ollama_ok = r.status_code == 200
        except Exception:
            self._ollama_ok = False
        return self._ollama_ok

    # ── generation ──────────────────────────────────────────────────────

    def generate(self, prompt: str, json_mode: bool = False) -> Optional[str]:
        """Return raw text from the first available backend, or None."""
        if self.gemini_key:
            result = self._try_gemini(prompt, json_mode)
            if result is not None:
                return result
        if self._ollama_available():
            result = self._try_ollama(prompt, json_mode)
            if result is not None:
                return result
        return None

    def generate_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Return parsed JSON dict, or None on any failure."""
        text = self.generate(prompt, json_mode=True)
        if text:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    # ── backends ────────────────────────────────────────────────────────

    def _try_gemini(self, prompt: str, json_mode: bool) -> Optional[str]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.gemini_model}:generateContent?key={self.gemini_key}"
        )
        body: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        if json_mode:
            body["generationConfig"] = {"response_mime_type": "application/json"}

        # Retry transient failures (503 high-demand, read timeouts).
        for attempt in range(GEMINI_MAX_ATTEMPTS):
            try:
                r = requests.post(url, json=body, timeout=GEMINI_TIMEOUT)
                if r.status_code == 200:
                    data = r.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                # 503 / 5xx → transient, retry; 4xx → permanent, give up
                if r.status_code < 500:
                    return None
            except Exception:
                pass
            if attempt < GEMINI_MAX_ATTEMPTS - 1:
                time.sleep(GEMINI_RETRY_DELAY * (attempt + 1))
        return None

    def _try_ollama(self, prompt: str, json_mode: bool) -> Optional[str]:
        try:
            body: Dict[str, Any] = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
            }
            if json_mode:
                body["format"] = "json"
            r = requests.post(
                f"{self.ollama_url}/api/generate", json=body, timeout=30
            )
            if r.status_code == 200:
                return r.json().get("response", "")
        except Exception:
            pass
        return None
