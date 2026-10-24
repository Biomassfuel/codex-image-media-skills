#!/usr/bin/env python3
"""Image and asynchronous video client for configurable media relays."""

from __future__ import annotations

import argparse
import base64
import binascii
import http.client
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import ssl
import struct
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
import uuid


IMAGE_ALIASES = {"image2": "gpt-image-2"}
IMAGE_MODELS = ("gpt-image-2", "gpt-image-2.5", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst")
DEFAULT_IMAGE_MODEL = "gpt-image-2.5"
MENU_VERSION = "2026-10-24.4"
CATALOG_FILE = Path(__file__).resolve().parent.parent / "references" / "model-catalog.json"
IMAGE_OPTIONS = ("size", "quality", "background", "output_format")
PROMPT_MODES = (
    {
        "id": "original",
        "label_zh": "原版直出",
        "label_en": "Original",
        "description_zh": "用你刚才的描述直接生成，不改写提示词。",
        "description_en": "Use the user's description verbatim; no prompt rewriting.",
    },
    {
        "id": "optimized-1",
        "label_zh": "优化 A｜忠实增强",
        "label_en": "Option A - Faithful enhancement",
        "description_zh": "保留原意，补足构图、光线、材质和背景。",
        "description_en": "Keep the intent; add composition, lighting, materials and background.",
    },
    {
        "id": "optimized-2",
        "label_zh": "优化 B｜风格强化",
        "label_en": "Option B - Style-led",
        "description_zh": "选定一种统一的视觉语言，让画面更有辨识度。",
        "description_en": "Commit to one coherent visual language for a stronger look.",
    },
    {
        "id": "optimized-3",
        "label_zh": "优化 C｜商业成片",
        "label_en": "Option C - Commercial layout",
        "description_zh": "留出文案空间和干净背景，适合海报、电商和社媒。",
        "description_en": "Build negative space and a clean background for posters, e-commerce and social.",
    },
)
QUALITY_TEXT = {
    "auto": ("自动", "由模型决定，通常最稳妥。", "Auto", "Let the model decide; usually the safest."),
    "low": ("低", "最快、最省，适合草稿。", "Low", "Fastest and cheapest; good for drafts."),
    "medium": ("中", "质量与速度平衡。", "Medium", "Balanced quality and speed."),
    "high": ("高", "细节最多，通常最慢、最贵。", "High", "Most detail; usually slower and more expensive."),
}
ORIENTATION_TEXT = {
    "square": ("方形", "Square"),
    "landscape": ("横屏", "Landscape"),
    "portrait": ("竖屏", "Portrait"),
}
SIZE_TIERS = {
    "2048x2048": "2K",
    "2048x1152": "2K",
    "1152x2048": "2K",
    "2560x1440": "4K",
    "1440x2560": "4K",
    "3840x2160": "4K",
    "2160x3840": "4K",
}
MODEL_ORDER = ("gpt-image-2.5", "gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst")
MODEL_ROLES = {
    "gpt-image-2.5": ("画质优先", "Quality first"),
    "gpt-image-2": ("精确尺寸优先", "Exact canvas first"),
    "gpt-image-2.5-flare": ("风格化；可能忽略尺寸", "Style-led; may ignore size"),
    "gpt-image-2.5-sunburst": ("方形风格；支持 12 种尺寸", "Square style; supports 12 sizes"),
}
DONE = {"completed", "succeeded", "success", "finished", "done"}
FAILED = {"failed", "failure", "error", "cancelled", "canceled", "expired"}
PENDING = {"queued", "pending", "submitted", "created"}
RUNNING = {"in_progress", "processing", "running", "generating"}


class MediaError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def checked_url(value: str) -> str:
    parts = urllib.parse.urlsplit(value)
    if not parts.hostname or parts.username is not None or parts.password is not None:
        raise MediaError("Use an absolute API/media URL without embedded credentials.")
    if parts.scheme not in {"https", "http"}:
        raise MediaError("Only HTTPS URLs and local HTTP development URLs are supported.")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise MediaError("Remote URLs must use HTTPS.")
    if parts.fragment:
        raise MediaError("URLs must not contain a fragment.")
    return value


def origin(url: str) -> tuple[str, str | None, int | None]:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def api_base(value: str) -> str:
    value = checked_url(value.strip().rstrip("/"))
    if urllib.parse.urlsplit(value).query:
        raise MediaError("The API base URL must not include query parameters.")
    return value if value.endswith("/v1") else value + "/v1"


def redact(value: Any, secret: str = "") -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key.lower() in {"authorization", "api_key", "apikey", "access_token", "b64_json"}:
                result[key] = "[redacted]"
            else:
                result[key] = redact(item, secret)
        return result
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, str):
        value = value.replace(secret, "[redacted]") if secret else value
        if value.startswith("data:"):
            return "[inline media omitted]"
        return re.sub(r"(?i)Bearer\s+[^\s\"'<>]+", "Bearer [redacted]", value)
    return value


def load_env(path: str | None) -> None:
    if not path:
        return
    for line in Path(path).expanduser().read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, value = line.partition("=")
        if not sep or key not in {"RELAY_BASE_URL", "RELAY_API_KEY", "RELAY_IMAGE_MODEL", "RELAY_VIDEO_MODEL"}:
            raise MediaError("Env files accept only RELAY_BASE_URL, RELAY_API_KEY, RELAY_IMAGE_MODEL and RELAY_VIDEO_MODEL assignments.")
        value = value.strip()
        if value[:1] in {"'", '"'} and value[-1:] == value[:1]:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def read_prompt(args) -> str:
    text = Path(args.prompt_file).expanduser().read_text(encoding="utf-8-sig") if args.prompt_file else args.prompt
    if not text or not text.strip():
        raise MediaError("A non-empty --prompt or --prompt-file is required.")
    return text.strip()


def extra_fields(value: str | None, reserved: set[str]) -> dict:
    if not value:
        return {}
    text = Path(value[1:]).expanduser().read_text(encoding="utf-8-sig") if value.startswith("@") else value
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MediaError(f"Invalid --extra-json: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise MediaError("--extra-json must contain a JSON object.")
    conflicts = reserved.intersection(data)
    if conflicts:
        raise MediaError("Use named options for reserved fields: " + ", ".join(sorted(conflicts)))
    return data


def local_file(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise MediaError(f"Input file does not exist: {path}")
    return path


def multipart(fields: dict, files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = "relay-" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        if not re.fullmatch(r"[A-Za-z0-9_.\[\]-]+", name):
            raise MediaError("Multipart field names must contain only letters, digits, dots, dashes, underscores and brackets.")
        if value is None:
            continue
        if isinstance(value, (dict, list, bool)):
            value = json.dumps(value, ensure_ascii=False)
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    for name, path in files:
        filename = re.sub(r'[^A-Za-z0-9._-]', "_", path.name)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8"))
        chunks.extend((path.read_bytes(), b"\r\n"))
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


class Client:
    def __init__(self, base: str, key: str, timeout: float = 300, no_proxy: bool = False):
        self.base = api_base(base)
        self.key = key
        self.timeout = timeout
        handlers = [NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())]
        if no_proxy:
            handlers.insert(0, urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def endpoint(self, path: str) -> str:
        return self.base + "/" + path.lstrip("/")

    def request(self, method: str, path: str, fields: dict | None = None, files=None, force_multipart=False) -> Any:
        headers = {"Accept": "application/json", "Authorization": "Bearer " + self.key, "User-Agent": "relay-media/1.0"}
        body = None
        if files or force_multipart:
            body, headers["Content-Type"] = multipart(fields or {}, files)
        elif fields is not None:
            body = json.dumps(fields, ensure_ascii=False, allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.endpoint(path), data=body, headers=headers, method=method)
        started = time.monotonic()
        phase = "before response headers"
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                phase = "while reading response body"
                raw = response.read(32 * 1024 * 1024 + 1)
                if len(raw) > 32 * 1024 * 1024:
                    raise MediaError("JSON response exceeds 32 MiB; request fewer images or use URL responses.")
                data = json.loads(raw)
                if isinstance(data, dict) and data.get("error") and not any(data.get(name) for name in ("id", "task_id", "status", "state")):
                    raise MediaError("Relay error: " + json.dumps(redact(data["error"], self.key), ensure_ascii=False)[:1500])
                return data
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            detail = str(redact(detail, self.key))[:1500]
            suffix = " Creation was not retried; check the provider before submitting again." if method == "POST" else ""
            raise MediaError(f"HTTP {exc.code}: {detail}.{suffix}") from exc
        except (http.client.HTTPException, urllib.error.URLError, TimeoutError, OSError) as exc:
            suffix = " Creation was not retried; the provider may already have accepted it." if method == "POST" else ""
            elapsed = time.monotonic() - started
            raise MediaError(f"Network request failed ({type(exc).__name__}, {phase}, {elapsed:.1f}s): {redact(str(exc), self.key)}.{suffix}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MediaError("The relay returned invalid JSON.") from exc

    def download(self, url: str, target: Path, kind: str, timeout: float, max_bytes: int) -> Path:
        url = checked_url(urllib.parse.urljoin(self.base + "/", url))
        part = target.with_name(target.name + "-" + uuid.uuid4().hex + ".part")
        created_part = False
        try:
            for _ in range(6):
                headers = {"User-Agent": "relay-media/1.0"}
                if origin(url) == origin(self.base):
                    headers["Authorization"] = "Bearer " + self.key
                try:
                    response = self.opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)
                except urllib.error.HTTPError as exc:
                    if exc.code in {301, 302, 303, 307, 308} and exc.headers.get("Location"):
                        url = checked_url(urllib.parse.urljoin(url, exc.headers["Location"]))
                        exc.close()
                        continue
                    raise MediaError(f"Media download failed with HTTP {exc.code}; saved job metadata can be used to retry the download.") from exc
                with response:
                    media_type = response.headers.get_content_type()
                    first = response.read(8192)
                    extension = media_extension(first, kind, media_type)
                    size = len(first)
                    if size > max_bytes:
                        raise MediaError("Media exceeds the configured download limit.")
                    with part.open("xb") as output:
                        created_part = True
                        output.write(first)
                        while block := response.read(1024 * 1024):
                            size += len(block)
                            if size > max_bytes:
                                raise MediaError("Media exceeds the configured download limit.")
                            output.write(block)
                    destination = target.with_suffix(extension)
                    if destination.exists():
                        raise MediaError(f"Refusing to overwrite {destination}")
                    part.rename(destination)
                    return destination.resolve()
            raise MediaError("Too many media download redirects.")
        except (http.client.HTTPException, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MediaError(f"Media download failed: {redact(str(exc), self.key)}") from exc
        finally:
            if created_part:
                part.unlink(missing_ok=True)


def media_extension(data: bytes, kind: str, content_type: str = "") -> str:
    signatures = ((b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"))
    if kind == "image":
        for magic, extension in signatures:
            if data.startswith(magic):
                return extension
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        if data[4:8] == b"ftyp" and data[8:12] in {b"avif", b"avis"}:
            return ".avif"
    if kind == "video":
        if data[4:8] == b"ftyp":
            return ".mov" if data[8:12] == b"qt  " else ".mp4"
        if data.startswith(b"\x1aE\xdf\xa3"):
            return ".webm"
    raise MediaError(f"The {kind} response does not contain a recognized media file (content type: {content_type or 'unknown'}).")


def run_dir(root: str, label: str) -> Path:
    directory = Path(root).expanduser().resolve() / (time.strftime("%Y%m%d-%H%M%S") + "-" + label + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def save_json(path: Path, value: Any, secret: str = "") -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(redact(value, secret), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def job_object(data: Any) -> dict:
    if not isinstance(data, dict):
        raise MediaError("Expected a JSON object for the video job.")
    nested = data.get("data")
    return nested if isinstance(nested, dict) else data


def job_summary(data: Any) -> dict:
    job = job_object(data)
    identifier = job.get("id") or job.get("task_id") or job.get("taskId")
    state = str(job.get("status") or job.get("state") or "unknown").lower()
    state = "completed" if state in DONE else "failed" if state in FAILED else "queued" if state in PENDING else "in_progress" if state in RUNNING else state
    result = {"task_id": str(identifier) if identifier is not None else None, "status": state}
    for key in ("progress", "error"):
        if job.get(key) is not None:
            result[key] = job[key]
    return result


def video_url(data: Any) -> str | None:
    job = job_object(data)
    for key in ("url", "video_url", "download_url"):
        if isinstance(job.get(key), str) and job[key]:
            return job[key]
    for key in ("output", "result"):
        nested = job.get(key)
        if isinstance(nested, str) and nested.startswith(("https://", "http://", "/")):
            return nested
        if isinstance(nested, dict):
            for name in ("url", "video_url", "download_url"):
                if isinstance(nested.get(name), str) and nested[name]:
                    return nested[name]
    return None


def task_path(task_id: str) -> str:
    return "videos/" + urllib.parse.quote(task_id, safe="")


def poll(client: Client, data: dict, args, directory: Path) -> dict:
    deadline = time.monotonic() + args.wait_timeout
    while True:
        summary = job_summary(data)
        save_json(directory / "job.json", {**summary, "response": data}, client.key)
        if summary["status"] in {"completed", "failed"}:
            return data
        if not args.wait or time.monotonic() >= deadline:
            return data
        if not summary["task_id"]:
            raise MediaError(f"No task ID in response; inspect {directory / 'job.json'} before submitting again.")
        time.sleep(min(args.poll_interval, max(0, deadline - time.monotonic())))
        if time.monotonic() >= deadline:
            return data
        data = client.request("GET", task_path(summary["task_id"]))
        retrieved = job_object(data)
        if not any(retrieved.get(name) for name in ("id", "task_id", "taskId")):
            retrieved["id"] = summary["task_id"]


def video_result(client: Client, data: dict, args, directory: Path) -> dict:
    data = poll(client, data, args, directory)
    result = {**job_summary(data), "job_file": str((directory / "job.json").resolve()), "files": []}
    if result["status"] == "failed":
        raise MediaError(f"Video job failed: {json.dumps(redact(result.get('error', 'no error detail'), client.key), ensure_ascii=False)}. Job: {result['job_file']}")
    if result["status"] == "completed":
        url = video_url(data)
        if not url and result["task_id"]:
            url = client.endpoint(task_path(result["task_id"]) + "/content")
        if not url:
            raise MediaError(f"Completed video has neither a download URL nor a task ID; inspect {result['job_file']}.")
        if not args.no_download:
            result["files"] = [str(client.download(url, directory / "video", "video", args.download_timeout, int(args.max_download_mb * 1024 * 1024)))]
    else:
        if not result["task_id"]:
            raise MediaError(f"No task ID in response; inspect {result['job_file']} before submitting again.")
        result["pending"] = True
    save_json(directory / "result.json", result, client.key)
    return result


def load_catalog() -> dict:
    """Read the local model catalog; a missing file means no constraints are configured."""
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema": 0, "image_models": {}}
    except (OSError, json.JSONDecodeError) as exc:
        raise MediaError(f"Cannot read the model catalog at {CATALOG_FILE}: {exc}") from exc
    models = data.get("image_models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        raise MediaError(f"The model catalog at {CATALOG_FILE} has no image_models object.")
    return data


def option_spec(profile: dict, name: str) -> dict:
    spec = profile.get(name) if isinstance(profile, dict) else None
    return spec if isinstance(spec, dict) else {"mode": "none"}


def size_option(value: str) -> dict:
    """Describe a catalog size for a menu without changing the value sent to the API."""
    match = re.fullmatch(r"(\d+)x(\d+)", value)
    if not match:
        return {"value": value, "label": value, "width": None, "height": None, "aspect": None, "orientation": None, "tier": None}
    width, height = int(match.group(1)), int(match.group(2))
    divisor = math.gcd(width, height) or 1
    aspect = f"{width // divisor}:{height // divisor}"
    orientation = "square" if width == height else "landscape" if width > height else "portrait"
    tier = SIZE_TIERS.get(value)
    if tier is None:
        long_edge = max(width, height)
        tier = "4K" if long_edge >= 3840 else "2K" if long_edge >= 2048 else None
    label = f"{width}×{height}" + (f" · {tier}" if tier else "")
    return {"value": value, "label": label, "width": width, "height": height, "aspect": aspect, "orientation": orientation, "tier": tier}


def localized(entry: dict, field: str, lang: str) -> str:
    suffix = "zh" if lang == "zh" else "en"
    return str(entry.get(f"{field}_{suffix}") or entry.get(field) or "")


def prompt_option(mode: dict, index: int, lang: str) -> dict:
    return {
        "index": index,
        "id": mode.get("id", f"mode-{index}"),
        "label": localized(mode, "label", lang),
        "description": localized(mode, "description", lang),
        "recommended": mode.get("id") == "optimized-1",
    }


def quality_option(value: str, default: str | None, lang: str) -> dict:
    text = QUALITY_TEXT.get(value)
    if text:
        label, description = (text[0], text[1]) if lang == "zh" else (text[2], text[3])
    else:
        label, description = value, ""
    return {"value": value, "label": label, "description": description, "recommended": value == default}


def model_option(model_id: str, profile: dict, selected: str, lang: str) -> dict:
    size_spec = option_spec(profile, "size")
    quality_spec = option_spec(profile, "quality")
    role = MODEL_ROLES.get(model_id, ("", ""))[0 if lang == "zh" else 1]
    return {
        "id": model_id,
        "label": profile.get("label", model_id),
        "role": role,
        "edit": bool(profile.get("edit")),
        "size_mode": size_spec.get("mode", "none"),
        "size_count": len(size_spec.get("values") or []),
        "default_size": size_spec.get("default") or size_spec.get("value"),
        "quality_values": [str(value) for value in (quality_spec.get("values") or [])],
        "size_reliability": profile.get("size_reliability", "unknown"),
        "size_note": profile.get("size_note", ""),
        "selected": model_id == selected,
        "recommended": model_id == "gpt-image-2.5",
    }


def choices_payload(catalog: dict, model: str | None, lang: str) -> dict:
    """Build the offline model/prompt/size/quality menu shown before an image request."""
    explicit_model = model is not None
    requested = model or os.getenv("RELAY_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL
    resolved = IMAGE_ALIASES.get(requested, requested)
    profiles = catalog.get("image_models") if isinstance(catalog.get("image_models"), dict) else {}
    profile = profiles.get(resolved) if explicit_model and isinstance(profiles, dict) else None
    zh = lang == "zh"
    model_ids = sorted(
        profiles,
        key=lambda item: (MODEL_ORDER.index(item) if item in MODEL_ORDER else len(MODEL_ORDER), item),
    )
    result = {
        "menu_version": MENU_VERSION,
        "model": resolved if explicit_model else None,
        "label": profile.get("label", resolved) if isinstance(profile, dict) else None,
        "cataloged": isinstance(profile, dict),
        "language": lang,
        "model_required": not explicit_model,
        "selection_order": ["model", "prompt", "supplement", "size", "quality"],
        "model_question": "选择模型" if zh else "Choose a model",
        "model_options": [model_option(item, profiles[item], resolved if explicit_model else "", lang) for item in model_ids],
        "prompt": {
            "question": "选择提示词版本" if zh else "Choose a prompt version",
            "options": [prompt_option(mode, index, lang) for index, mode in enumerate(PROMPT_MODES)],
        },
        "supplement": {
            "question": "补充提示词（可选）" if zh else "Additional prompt details (optional)",
            "free_text": True,
            "placeholder": "例如：加一行英文标题 / 不要文字 / 背景更虚化" if zh else "e.g. add a headline / no text / blur the background",
            "hint": "可以直接输入要补充的要求；没有就回复“无”。" if zh else "Type any extra requirements, or reply \"none\".",
            "examples": (
                ["加一行标题：\"...\"", "背景更虚化，保留主体", "不要文字、水印或 logo", "服装/道具/光线改成..."]
                if zh
                else ["Add a headline: \"...\"", "Blur the background more; keep the subject", "No text, watermark or logo", "Change the outfit/prop/lighting to ..."]
            ),
        },
    }

    if not explicit_model:
        result["next_command"] = "choices --model <model-id>"
        result["size"] = {
            "mode": "pending",
            "options": [],
            "note": "先让用户选模型，再用 choices --model <id> 获取该模型的全部尺寸。" if zh else "Ask the user to choose a model, then run choices --model <id> for its full size list.",
        }
        result["quality"] = {
            "mode": "pending",
            "options": [],
            "note": "模型选定后再展示画质选项。" if zh else "Quality options appear after a model is selected.",
        }
        result["reply_hint"] = "先回复模型编号；选定后再回复提示词、分辨率、画质和补充要求。" if zh else "Reply with a model number first; then choose prompt, size, quality and any extra details."
        return result

    size_spec = option_spec(profile, "size")
    size_mode = size_spec.get("mode", "none")
    if not isinstance(profile, dict):
        result["size"] = {
            "mode": "unknown",
            "reliability": "unknown",
            "options": [],
            "note": "该模型不在本地目录中；先只发提示词，尺寸和画质由服务商决定。" if zh else "This model is not in the local catalog; send the prompt only and let the provider decide size and quality.",
        }
    elif size_mode == "fixed":
        fixed = str(size_spec.get("value") or "")
        result["size"] = {
            "mode": "fixed",
            "value": fixed,
            "label": size_option(fixed)["label"],
            "reliability": profile.get("size_reliability", "fixed"),
            "reliability_note": profile.get("size_note", ""),
            "options": [],
            "note": size_spec.get("note") or ("该模型固定输出 " + fixed + "，不需要选择尺寸。" if zh else "This model always returns " + fixed + "; no size choice."),
        }
    elif size_mode == "enum":
        default = size_spec.get("default")
        options = []
        for index, raw in enumerate(size_spec.get("values") or [], 1):
            value = str(raw)
            option = {"index": index, **size_option(value)}
            orientation = option.get("orientation")
            option["orientation_label"] = (ORIENTATION_TEXT[orientation][0 if zh else 1] if orientation in ORIENTATION_TEXT else "")
            option["recommended"] = value == default
            options.append(option)
        pages = [list(range(start, min(start + 4, len(options) + 1))) for start in range(1, len(options) + 1, 4)]
        result["size"] = {
            "mode": "enum",
            "default": default,
            "reliability": profile.get("size_reliability", "unknown"),
            "reliability_note": profile.get("size_note", ""),
            "do_not_filter": True,
            "page_size": 4,
            "pages": pages,
            "options": options,
            "note": "展示全部尺寸，不要按构图删减；回复编号即可，尺寸值会原样发送给模型。" if zh else "Show every size; do not filter by composition. Reply with a number; the exact value is sent to the model.",
        }
    else:
        result["size"] = {"mode": size_mode, "options": [], "note": "该模型没有可用的尺寸选项。" if zh else "This model has no size options."}

    quality_spec = option_spec(profile, "quality")
    quality_mode = quality_spec.get("mode", "none")
    if quality_mode == "fixed":
        fixed = str(quality_spec.get("value") or "")
        result["quality"] = {"mode": "fixed", "value": fixed, "options": [], "note": "该模型固定使用 " + fixed + " 画质。" if zh else "This model always uses " + fixed + " quality."}
    else:
        default = quality_spec.get("default")
        values = [str(value) for value in (quality_spec.get("values") or [])]
        result["quality"] = {
            "mode": quality_mode,
            "default": default,
            "options": [quality_option(value, default, lang) for value in values],
            "note": "" if values else ("该模型没有可用的画质选项。" if zh else "This model has no quality options."),
        }

    result["reply_hint"] = (
        "按“模型 提示词 分辨率 画质”的顺序回复编号即可，例如 1 1 7 1；补充要求写在后面，没有就写“无”。"
        if zh
        else "Reply with model, prompt, size and quality numbers in order, e.g. 1 1 7 1; append extra requirements or say \"none\"."
    )
    return result


def chosen_value(profile: dict, name: str, model: str, value):
    """Return the value to send, rejecting anything the catalog does not allow."""
    label = name.replace("_", "-")
    spec = option_spec(profile, name)
    mode = spec.get("mode", "none")
    if mode == "fixed":
        fixed = spec.get("value")
        if value is not None and value != fixed:
            note = spec.get("note") or f"Omit --{label} to accept the fixed value."
            raise MediaError(f"{model} always returns {fixed}, so --{label} {value} cannot be honored. {note}")
        return None
    values = [str(item) for item in (spec.get("values") or [])]
    if value is None:
        return None
    if mode != "enum" or not values:
        raise MediaError(f"{model} does not accept --{label}. Omit it or choose a model that supports it.")
    if value not in values:
        raise MediaError(f"Unsupported --{label} '{value}' for {model}. Choose one of: " + ", ".join(values))
    return value


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        length = int.from_bytes(data[index + 2:index + 4], "big")
        if length < 2:
            return None
        if 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC}:
            height = int.from_bytes(data[index + 5:index + 7], "big")
            width = int.from_bytes(data[index + 7:index + 9], "big")
            return (width, height) if width and height else None
        index += 2 + length
    return None


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    return png_dimensions(data) or jpeg_dimensions(data)


def file_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as stream:
            return image_dimensions(stream.read(256 * 1024))
    except OSError:
        return None


def image_payload(args) -> tuple[str, dict, list]:
    profiles = load_catalog()["image_models"]
    unattended = bool(getattr(args, "unattended", False))
    if not args.model and not unattended:
        raise MediaError(
            "missing_selection: choose an explicit --model. Run 'choices' without --model, "
            "ask the user to pick a model, then run 'choices --model <id>'. "
            "Do not guess or use RELAY_IMAGE_MODEL for an interactive request."
        )
    requested = args.model or os.getenv("RELAY_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL
    model = IMAGE_ALIASES.get(requested, requested)
    profile = profiles.get(model)
    if profile is not None and not unattended:
        missing = []
        if option_spec(profile, "size").get("mode") == "enum" and not args.size:
            missing.append("--size")
        if option_spec(profile, "quality").get("mode") == "enum" and not args.quality:
            missing.append("--quality")
        if missing:
            raise MediaError(
                "missing_selection: " + ", ".join(missing) + ". Ask the user to choose from the full "
                "choices menu, then pass the exact values. Do not use provider defaults or guess."
            )
    fields = {"model": model, "prompt": read_prompt(args), "n": args.n}
    if profile is None:
        supplied = [name for name in IMAGE_OPTIONS if getattr(args, name) is not None]
        if supplied and not getattr(args, "allow_unverified", False):
            flags = ", ".join("--" + name.replace("_", "-") for name in supplied)
            raise MediaError(
                f"'{model}' is not in the verified catalog, so {flags} cannot be validated. "
                "Run 'catalog' and pick a cataloged model, or pass --allow-unverified to send raw values."
            )
        for name in supplied:
            fields[name] = getattr(args, name)
    else:
        for name in IMAGE_OPTIONS:
            value = chosen_value(profile, name, model, getattr(args, name))
            if value is not None:
                fields[name] = value
    fields.update(extra_fields(args.extra_json, {"model", "prompt", "n", "size", "quality", "background", "output_format", "image", "image[]", "mask"}))
    images = [local_file(value) for value in args.image]
    if args.mask and not images:
        raise MediaError("--mask requires at least one --image.")
    files = [("image" if len(images) == 1 else "image[]", path) for path in images]
    if args.mask:
        files.append(("mask", local_file(args.mask)))
    return ("images/edits" if images else "images/generations"), fields, files


def video_payload(args) -> tuple[str, dict, list]:
    model = args.model or os.getenv("RELAY_VIDEO_MODEL")
    if not model:
        raise MediaError("Set --model or RELAY_VIDEO_MODEL using a video model enabled by your relay.")
    fields = {"model": model, "prompt": read_prompt(args)}
    duration_field = args.duration_field
    if duration_field == "auto":
        duration_field = "duration" if any(tag in model.lower() for tag in ("seedance", "doubao", "h3")) else "seconds"
    if args.seconds:
        fields[duration_field] = args.seconds
    for name in ("size", "resolution", "aspect_ratio"):
        if getattr(args, name) is not None:
            fields[name] = getattr(args, name)
    for option, field in (("reference_image_url", "reference_image_urls"), ("reference_video_url", "reference_video_urls"), ("reference_audio_url", "reference_audio_urls")):
        if getattr(args, option):
            fields[field] = [checked_url(value) for value in getattr(args, option)]
    for option, field in (("first_frame_url", "first_frame_image_url"), ("last_frame_url", "last_frame_image_url")):
        if getattr(args, option):
            fields[field] = checked_url(getattr(args, option))
    fields.update(extra_fields(args.extra_json, {"model", "prompt", "seconds", "duration", "size", "resolution", "aspect_ratio", "input_reference", "reference_image_urls", "reference_video_urls", "reference_audio_urls", "first_frame_image_url", "last_frame_image_url"}))
    files = [("input_reference", local_file(args.image))] if args.image else []
    if files and args.encoding == "json":
        raise MediaError("A local --image requires multipart encoding. Use --reference-image-url for JSON.")
    return "videos", fields, files


def execute(args) -> dict:
    load_env(args.env_file)
    base = args.base_url or os.getenv("RELAY_BASE_URL")
    key = os.getenv("RELAY_API_KEY", "").strip()
    catalog = load_catalog()
    if args.command == "doctor":
        return {"menu_version": MENU_VERSION, "base_url": api_base(base) if base else None, "key_configured": bool(key), "image_model": os.getenv("RELAY_IMAGE_MODEL", DEFAULT_IMAGE_MODEL), "video_model": os.getenv("RELAY_VIDEO_MODEL"), "catalog_models": sorted(catalog["image_models"]), "python": sys.version.split()[0], "network_route": "direct" if args.no_proxy else "system_proxy_settings", "network_checked": False}
    if args.command == "catalog":
        entries = []
        for model_id in sorted(catalog["image_models"]):
            profile = catalog["image_models"][model_id]
            entry = {
                "id": model_id,
                "label": profile.get("label", model_id),
                "source": profile.get("source", "documented"),
                "edit": bool(profile.get("edit")),
                "size_reliability": profile.get("size_reliability", "unknown"),
                "size_note": profile.get("size_note", ""),
                "size": option_spec(profile, "size"),
                "quality": option_spec(profile, "quality"),
                "background": option_spec(profile, "background"),
                "output_format": option_spec(profile, "output_format"),
            }
            if profile.get("note"):
                entry["note"] = profile["note"]
            entries.append(entry)
        return {"menu_version": MENU_VERSION, "catalog_file": str(CATALOG_FILE), "updated": catalog.get("updated"), "default_image_model": os.getenv("RELAY_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL, "models": entries}
    if args.command == "choices":
        return choices_payload(catalog, args.model, args.lang)
    prepared = None
    if args.command in {"image", "video"}:
        prepared = image_payload(args) if args.command == "image" else video_payload(args)
        if args.dry_run:
            path, fields, files = prepared
            return {"dry_run": True, "method": "POST", "endpoint": api_base(base) + "/" + path if base else "<RELAY_BASE_URL>/v1/" + path, "encoding": "multipart" if files or getattr(args, "encoding", "auto") == "multipart" else "json", "body": fields, "files": [{"field": name, "path": str(path)} for name, path in files], "authorization": "Bearer [RELAY_API_KEY]"}
    if not base or not key:
        raise MediaError("Configure RELAY_BASE_URL and RELAY_API_KEY, or use --base-url with RELAY_API_KEY. Store the key locally; do not paste it into chat.")
    client = Client(base, key, args.timeout, no_proxy=args.no_proxy)
    if args.command == "models":
        data = client.request("GET", "models")
        values = data.get("data", []) if isinstance(data, dict) else data
        if not isinstance(values, list):
            raise MediaError("Expected data[] from /models.")
        models = sorted(str(item["id"]) for item in values if isinstance(item, dict) and "id" in item)
        return {"models": [name for name in models if not args.contains or args.contains.lower() in name.lower()]}
    directory = run_dir(args.output_dir, args.command)
    if args.command == "image":
        path, fields, files = prepared
        try:
            data = client.request("POST", path, fields, files)
        except MediaError as exc:
            failure_file = directory / "failure.json"
            save_json(failure_file, {"model": fields["model"], "endpoint": client.endpoint(path),
                      "timeout_seconds": args.timeout, "network_route": "direct" if args.no_proxy else "system_proxy_settings",
                      "error": str(exc), "automatically_retried": False}, key)
            raise MediaError(f"{exc} Details: {failure_file}") from exc
        save_json(directory / "response.json", data, key)
        values = data.get("data") if isinstance(data, dict) else None
        if not isinstance(values, list) or not values:
            raise MediaError(f"No data[] images in response; inspect {directory / 'response.json'}.")
        paths = []
        dimensions: list[tuple[int, int] | None] = []
        for index, item in enumerate(values, 1):
            if not isinstance(item, dict):
                raise MediaError("Each image result must be an object.")
            target = directory / f"image-{index:02d}"
            if item.get("b64_json"):
                try:
                    raw = base64.b64decode(item["b64_json"], validate=True)
                except (ValueError, binascii.Error, TypeError) as exc:
                    raise MediaError("Invalid base64 image in relay response.") from exc
                target = target.with_suffix(media_extension(raw, "image"))
                with target.open("xb") as stream:
                    stream.write(raw)
                paths.append(str(target.resolve()))
                dimensions.append(image_dimensions(raw))
            elif isinstance(item.get("url"), str):
                saved = client.download(item["url"], target, "image", args.download_timeout, int(args.max_download_mb * 1024 * 1024))
                paths.append(str(saved))
                dimensions.append(file_dimensions(saved))
            else:
                raise MediaError("An image result has neither b64_json nor url.")
        result = {"model": fields["model"], "files": paths, "response_file": str((directory / "response.json").resolve())}
        reported = [f"{entry[0]}x{entry[1]}" for entry in dimensions if entry]
        if reported:
            result["sizes"] = reported
        expected = fields.get("size") or option_spec(catalog["image_models"].get(fields["model"]) or {}, "size").get("value")
        unexpected = sorted({size for size in reported if expected and size != expected})
        if unexpected:
            result["warnings"] = [f"Requested {expected} but the relay returned {', '.join(unexpected)}; the model ignored the size parameter."]
        save_json(directory / "result.json", result, key)
        return result
    if args.command == "video":
        path, fields, files = prepared
        data = client.request("POST", path, fields, files, force_multipart=args.encoding == "multipart")
        # Persist the ID before polling or downloading, so work is resumable.
        save_json(directory / "job.json", {**job_summary(data), "model": fields["model"], "response": data}, key)
        return video_result(client, data, args, directory)
    if args.command == "status":
        data = client.request("GET", task_path(args.task_id))
        # Some gateways omit the ID when retrieving an existing task.
        retrieved = job_object(data)
        if not any(retrieved.get(name) for name in ("id", "task_id", "taskId")):
            retrieved["id"] = args.task_id
        return video_result(client, data, args, directory)
    if args.command == "download":
        path = client.download(client.endpoint(task_path(args.task_id) + "/content"), directory / "video", "video", args.download_timeout, int(args.max_download_mb * 1024 * 1024))
        return {"task_id": args.task_id, "files": [str(path)]}
    raise MediaError("Unknown command.")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--env-file", help="Explicit local env file; existing environment variables take precedence")
    root.add_argument("--base-url", help="Relay API origin or base ending in /v1")
    root.add_argument("--timeout", type=positive_float, default=300, help="API request timeout in seconds (default: 300)")
    root.add_argument("--no-proxy", action="store_true", help="Connect directly, ignoring system and environment proxy settings for this invocation")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Inspect local configuration without network access")
    sub.add_parser("catalog", help="List cataloged image models with the sizes and qualities each accepts (offline)")
    choices = sub.add_parser("choices", help="Print the offline model, prompt, size and quality menu")
    choices.add_argument("--model", help="Image model to describe; omit for the model-selection step")
    choices.add_argument("--lang", choices=("zh", "en"), default="zh", help="Menu language (default: zh)")
    models = sub.add_parser("models", help="List model IDs enabled for this key")
    models.add_argument("--contains")
    for name in ("image", "video", "status", "download"):
        command = sub.add_parser(name)
        command.add_argument("--output-dir", default="outputs", help="Parent for a new, unique result directory")
        command.add_argument("--download-timeout", type=positive_float, default=300)
        command.add_argument("--max-download-mb", type=positive_float, default=1024)
        if name in {"status", "download"}:
            command.add_argument("task_id")
        if name in {"video", "status"}:
            command.add_argument("--wait", action="store_true", help="Poll the existing task, with a bounded wait")
            command.add_argument("--wait-timeout", type=positive_float, default=600)
            command.add_argument("--poll-interval", type=positive_float, default=10)
            command.add_argument("--no-download", action="store_true")
        if name not in {"image", "video"}:
            continue
        command.add_argument("--model")
        prompts = command.add_mutually_exclusive_group(required=True)
        prompts.add_argument("--prompt")
        prompts.add_argument("--prompt-file")
        command.add_argument("--size")
        command.add_argument("--extra-json", help="Provider-specific JSON object, or @path.json")
        command.add_argument("--dry-run", action="store_true", help="Prepare a request without a key, network or output files")
        if name == "image":
            command.add_argument("--allow-unverified", action="store_true", help="Send size/quality for a model missing from the catalog instead of rejecting it")
            command.add_argument("--unattended", action="store_true", help="Automation/tests only: allow omitted model/size/quality and provider defaults. Never use for an interactive request")
            command.add_argument("--image", action="append", default=[], help="Local reference image; repeat for multiple inputs")
            command.add_argument("--mask")
            command.add_argument("--n", type=positive_int, default=1)
            command.add_argument("--quality")
            command.add_argument("--background")
            command.add_argument("--output-format", choices=("png", "jpeg", "webp"))
        else:
            command.add_argument("--seconds", type=positive_int)
            command.add_argument("--duration-field", choices=("auto", "seconds", "duration"), default="auto")
            command.add_argument("--encoding", choices=("auto", "json", "multipart"), default="auto")
            command.add_argument("--image", help="Local input_reference (multipart; verify model support)")
            command.add_argument("--resolution")
            command.add_argument("--aspect-ratio")
            for option in ("reference-image-url", "reference-video-url", "reference-audio-url"):
                command.add_argument("--" + option, action="append", default=[])
            command.add_argument("--first-frame-url")
            command.add_argument("--last-frame-url")
    return root


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(redact(result, os.getenv("RELAY_API_KEY", "")), ensure_ascii=False, indent=2))
        return 0
    except (MediaError, OSError, ValueError) as exc:
        print(json.dumps({"error": redact(str(exc), os.getenv("RELAY_API_KEY", ""))}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"error": "Interrupted. Resume any saved task with status; do not recreate the video job."}), file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
