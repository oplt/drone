import base64
import json
from typing import List, Optional, Dict, Any
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed

from drone.models import Detection



# Optional: use TurboJPEG if available (3-5x faster encode than OpenCV).
# Fallback to OpenCV if not installed.

# Optional: use TurboJPEG if available (3–5x faster encode than OpenCV).
# Fallback to OpenCV if not installed.
try:
    from turbojpeg import TurboJPEG, TJFLAG_FASTDCT  # type: ignore
    _jpeg = TurboJPEG()
    _use_turbo = True
except Exception:  # pragma: no cover - turbojpeg is optional
    _jpeg = None
    _use_turbo = False


def _encode_jpeg_sync(frame) -> str:
    """
    Synchronous JPEG encoding: NumPy BGR image -> base64 JPEG string (no prefix).
    This is CPU-heavy; prefer `encode_jpeg_async` from async code.
    """
    import cv2  # lazy import

    if _use_turbo and _jpeg is not None:
        # TurboJPEG expects BGR input
        buf = _jpeg.encode(frame, quality=85, flags=TJFLAG_FASTDCT)
        return base64.b64encode(buf).decode()
    else:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            raise RuntimeError("JPEG encode failed")
        return base64.b64encode(buf.tobytes()).decode()


def encode_jpeg(frame) -> str:
    """
    Backwards-compatible synchronous encoder.
    (Kept in case you call it from sync code elsewhere.)
    """
    return _encode_jpeg_sync(frame)


async def encode_jpeg_async(frame) -> str:
    """
    Async wrapper that offloads JPEG encode to a thread pool so it
    doesn't block the event loop.
    """
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _encode_jpeg_sync, frame)


class LLMAnalyzer:
    """
    Vendor-agnostic vision analyzer with DeepSeek support.

    provider:
      - 'ollama'         -> POST {api_base}/api/chat  (Ollama local)
      - 'openai_compat'  -> POST {api_base}/chat/completions (OpenAI-compatible)

    Expect the model to return a pure JSON array:
      [{"label":"trash","confidence":0.92,"bbox":[x1,y1,x2,y2]}, ...]
    If not pure JSON, we try to extract JSON via a naive fallback.
    """
    def __init__(self, api_base: str, api_key: str, model: str, provider: str = "ollama"):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key or ""
        self.model = model
        self.provider = provider


    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    async def detect_objects(self, frame) -> List[Detection]:
        """
        Encode frame to JPEG in a worker thread and call the vision LLM via HTTP.
        """
        # Offload CPU-heavy JPEG encoding
        img_b64 = await encode_jpeg_async(frame)

        # CURRENT: urban cleanliness prompt
        # (swap to your agricultural prompt later if you want)
        system_prompt = (
            "You are a precise vision detector for urban cleanliness. "
            "Detect objects such as trash, litter, plastic bottles, cans, paper, and bags. "
            "Always respond with ONLY a JSON array of objects: "
            '[{\"label\": \"...\",\"confidence\": 0.0, \"bbox\":[x1,y1,x2,y2]}]. '
            "Use 0-1 confidence. bbox in pixel coordinates if available, else omit bbox."
        )
        user_prompt = "Analyze the image. Output ONLY the JSON array—no extra text."

        # --- alternative agricultural prompt (keep commented for now) ---
        # system_prompt = (
        #     "You are a precise vision detector for aerial images of agricultural fields. "
        #     "Detect and describe anomalies in crops and soil, such as: poor growth areas, "
        #     "discolored patches, pest or disease damage, weed patches, water stress, irrigation leaks, "
        #     "flooded or extremely dry zones, bare soil, lodging (fallen plants), or infrastructure issues. "
        #     "Always respond with ONLY a JSON array of objects, each with at least:\n"
        #     '  { \"label\": \"<short category name>\", \"confidence\": 0.0, \"bbox\": [x1,y1,x2,y2] }\n'
        #     "You MAY add extra keys like 'severity' or 'notes', but the top-level response must be "
        #     "a pure JSON array. Use confidence in [0,1]. bbox should be pixel coordinates if you can infer it; "
        #     "if not, you may omit 'bbox'."
        # )
        # user_prompt = (
        #     "Analyze the image for anomalies in crop health or field conditions. "
        #     "Output ONLY the JSON array—no extra explanation or text."
        # )

        if self.provider == "ollama":
            content_text = f"{system_prompt}\n\n{user_prompt}"
            payload = {
                "model": self.model,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                        # Ollama vision models accept base64 images via 'images'
                        "images": [img_b64]
                    }
                ]
            }
            headers = {"Content-Type": "application/json"}
            url = f"{self.api_base}/api/chat"
            parser = self._parse_ollama

        elif self.provider == "openai_compat":
            payload = {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt + "\n\n" + user_prompt},
                        {"type": "image_url", "image_url": f"data:image/jpeg;base64,{img_b64}"}
                    ]
                }],
                "temperature": 0.0
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
                "Content-Type": "application/json"
            }
            url = f"{self.api_base}/chat/completions"
            parser = self._parse_openai_compat

        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=payload, timeout=120) as r:
                r.raise_for_status()
                data = await r.json()

        text = parser(data)
        items = self._coerce_json_list(text)
        return [self._to_detection(it) for it in items]


    # ---------- parsers ----------
    def _parse_ollama(self, data: Dict[str, Any]) -> str:
        # Ollama returns: {"message":{"role":"assistant","content":"..."},"done":true,...}
        msg = data.get("message") or {}
        return (msg.get("content") or "").strip()

    def _parse_openai_compat(self, data: Dict[str, Any]) -> str:
        # OpenAI-compatible: choices[0].message.content
        choices = data.get("choices") or []
        if not choices:
            return "[]"
        return (choices[0].get("message", {}).get("content") or "").strip()

    # ---------- helpers ----------
    def _coerce_json_list(self, text: str) -> List[Dict[str, Any]]:
        """
        Try to parse a JSON array. If the model added prose, extract the first array substring.
        """
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, list) else []
        except Exception:
            # crude fallback: find first '[' ... ']' block
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except Exception:
                    return []
            return []

    def _to_detection(self, it: Dict[str, Any]) -> Detection:
        label = str(it.get("label", "object"))
        confidence = float(it.get("confidence", 0.0))
        bbox = it.get("bbox")
        bbox_t = tuple(bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else None
        return Detection(label=label, confidence=confidence, bbox=bbox_t, extra=it)
