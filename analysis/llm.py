import base64
import json
import time
import asyncio
from typing import List, Optional, Dict, Any
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed

from drone.models import Detection
import logging



# Optional: use TurboJPEG if available (3-5x faster encode than OpenCV).
# Fallback to OpenCV if not installed.
# try:
#     from turbojpeg import TurboJPEG, TJFLAG_FASTDCT  # type: ignore
#     _jpeg = TurboJPEG()
#     _use_turbo = True
# except Exception:  # pragma: no cover
#     _jpeg = None
#     _use_turbo = False
#
#
# def encode_jpeg(frame) -> str:
#     """NumPy image (H,W,3) BGR -> base64 JPEG string (no prefix)."""
#     if _use_turbo:
#         # Assume BGR input; TurboJPEG expects BGR for encode
#         buf = _jpeg.encode(frame, quality=85, flags=TJFLAG_FASTDCT)
#         return base64.b64encode(buf).decode()
#     else:
#         import cv2  # lazy import
#         ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
#         if not ok:
#             raise RuntimeError("JPEG encode failed")
#         return base64.b64encode(buf.tobytes()).decode()

def encode_jpeg(frame) -> str:
    """
    OpenCV BGR ndarray -> base64 JPEG string (no prefix).
    """
    import cv2
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return base64.b64encode(buf.tobytes()).decode()

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
        # Clean up API base URL - remove any existing /api/... paths
        if api_base:
            api_base = api_base.rstrip("/")
            # Remove /api/generate, /api/chat, /chat/completions if present (we'll add the correct one)
            for path in ["/api/generate", "/api/chat", "/chat/completions", "/v1/chat/completions"]:
                if api_base.endswith(path):
                    api_base = api_base[:-len(path)].rstrip("/")
                    break
        self.api_base = api_base if api_base else ""
        self.api_key = api_key or ""
        self.model = model or ""
        self.provider = provider
        
        # Check if LLM is properly configured
        self._is_configured = bool(self.api_base and self.model)
        if not self._is_configured:
            logging.warning("LLM API not configured: missing api_base or model. Object detection will be disabled.")
        
        # Circuit breaker state
        self._circuit_open = False
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._circuit_open_time = 0.0
        self._max_failures = 5  # Open circuit after 5 consecutive failures
        self._circuit_timeout = 60.0  # Keep circuit open for 60 seconds
        self._success_count = 0
        self._min_successes = 2  # Need 2 successes to close circuit

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows request"""
        current_time = time.time()
        
        # If circuit is open, check if timeout has passed
        if self._circuit_open:
            if current_time - self._circuit_open_time >= self._circuit_timeout:
                logging.info(f"Circuit breaker: Attempting to close circuit after {self._circuit_timeout}s timeout")
                self._circuit_open = False
                self._failure_count = 0
                return True
            else:
                logging.debug(f"Circuit breaker: Circuit is OPEN (opened {current_time - self._circuit_open_time:.1f}s ago)")
                return False
        
        return True
    
    def _record_success(self):
        """Record successful API call"""
        self._success_count += 1
        self._failure_count = 0
        
        # If we have enough successes and circuit was open, close it
        if self._circuit_open and self._success_count >= self._min_successes:
            logging.info("Circuit breaker: Circuit CLOSED after successful recovery")
            self._circuit_open = False
            self._failure_count = 0
            self._success_count = 0
    
    def _record_failure(self):
        """Record failed API call and check if circuit should open"""
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._success_count = 0
        
        if self._failure_count >= self._max_failures:
            if not self._circuit_open:
                self._circuit_open = True
                self._circuit_open_time = time.time()
                # Logging is handled in detect_objects() to avoid duplicate messages

    async def detect_objects(self, frame) -> List[Detection]:
        """Detect objects in frame with circuit breaker protection"""
        # Check if LLM is configured
        if not self._is_configured:
            return []  # Return empty list if not configured (no error logging)
        
        # Check circuit breaker before making request
        if not self._check_circuit_breaker():
            # Circuit is open - silently return empty list (no logging to reduce spam)
            return []  # Return empty list when circuit is open
        
        try:
            result = await self._detect_objects_impl(frame)
            self._record_success()
            return result
        except aiohttp.ClientResponseError as e:
            was_open = self._circuit_open
            self._record_failure()
            # Only log when circuit just opened (not on first failure to reduce spam)
            if not was_open and self._circuit_open:
                # Circuit just opened - log helpful message once
                error_msg = f"Circuit breaker opened: Ollama server at {self.api_base} is not responding"
                if e.status == 404:
                    error_msg += " (endpoint not found - check API URL)"
                elif e.status == 401:
                    error_msg += " (authentication failed - check API key)"
                elif e.status == 0:
                    error_msg += " (connection refused)"
                error_msg += f". Start Ollama with 'ollama serve'. API calls will be blocked for {self._circuit_timeout}s."
                logging.warning(error_msg)
            # Don't log on first failure or if circuit was already open
            return []  # Return empty list instead of raising
        except aiohttp.ClientConnectorError as e:
            was_open = self._circuit_open
            self._record_failure()
            # Only log when circuit just opened (not on first failure to reduce spam)
            if not was_open and self._circuit_open:
                logging.warning(f"Circuit breaker opened: Cannot connect to Ollama at {self.api_base}. "
                             f"Start Ollama server with 'ollama serve'. "
                             f"API calls will be blocked for {self._circuit_timeout}s.")
            # Don't log on first failure or if circuit was already open
            return []  # Return empty list instead of raising
        except asyncio.TimeoutError:
            was_open = self._circuit_open
            self._record_failure()
            # Only log when circuit just opened (not on first failure to reduce spam)
            if not was_open and self._circuit_open:
                logging.warning(f"Circuit breaker opened: Ollama at {self.api_base} is timing out. "
                             f"API calls will be blocked for {self._circuit_timeout}s.")
            # Don't log on first failure or if circuit was already open
            return []  # Return empty list instead of raising
        except Exception as e:
            was_open = self._circuit_open
            self._record_failure()
            # Only log when circuit just opened (not on first failure to reduce spam)
            if not was_open and self._circuit_open:
                # Circuit just opened - log once with helpful message
                error_detail = str(e)
                if hasattr(e, '__cause__') and e.__cause__:
                    error_detail = str(e.__cause__)
                logging.warning(f"Circuit breaker: Opening circuit after {self._failure_count} consecutive failures. "
                             f"LLM API at {self.api_base} is not responding ({type(e).__name__}). "
                             f"API calls will be blocked for {self._circuit_timeout}s. "
                             f"Check if Ollama server is running: 'ollama serve'")
            # Don't log anything on first failure or if circuit was already open
            return []  # Return empty list instead of raising

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))  # Reduced retries since we have circuit breaker
    async def _detect_objects_impl(self, frame) -> List[Detection]:
        """Internal implementation of object detection"""
        img_b64 = encode_jpeg(frame)
        system_prompt = (
            "You are a precise vision detector for urban cleanliness. "
            "Detect objects such as trash, litter, plastic bottles, cans, paper, and bags. "
            "Always respond with ONLY a JSON array of objects: "
            '[{"label": "...","confidence": 0.0, "bbox":[x1,y1,x2,y2]}]. '
            "Use 0-1 confidence. bbox in pixel coordinates if available, else omit bbox."
        )
        user_prompt = "Analyze the image. Output ONLY the JSON array—no extra text."

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
            # Ollama uses /api/chat endpoint (not /api/generate for chat)
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

        # Reduced timeout from 120s to 15s for faster failure detection
        async with aiohttp.ClientSession() as s:
            async with s.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
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
