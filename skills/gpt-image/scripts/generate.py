#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=2.32.0",
# ]
# ///
"""Small, deterministic CLI for the OpenAI Image API."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


SIZE_SHORTCUTS = {
    "1k": "1024x1024",
    "2k": "2048x2048",
    "4k": "3840x2160",
    "portrait": "1024x1536",
    "landscape": "1536x1024",
    "square": "1024x1024",
    "wide": "2048x1152",
    "tall": "2160x3840",
}
QUALITY_CHOICES = ("auto", "low", "medium", "high", "xhigh", "max")
FORMAT_CHOICES = ("png", "jpeg", "webp")
DEFAULT_MODEL = "gpt-image-2.5-flare"
MAX_IMAGE_BYTES = 50 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
STANDARD_GPT_IMAGE_MODELS = re.compile(
    r"gpt-image-(?:1|1\.5|1-mini)(?:-\d{4}-\d{2}-\d{2})?"
)
GPT_IMAGE_2_MODELS = re.compile(r"gpt-image-2(?:-\d{4}-\d{2}-\d{2})?")
GPT_IMAGE_25_MODELS = re.compile(
    r"gpt-image-2\.5-(?:flare|sunburst)(?:-\d{4}-\d{2}-\d{2})?"
)


class CliError(Exception):
    """An expected user-facing CLI error."""


def _parse_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=value entries from a dotenv file without extra dependencies."""
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name.strip()):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name.strip()] = value
    return values


def _load_env_chain() -> None:
    """Load process env, then .env, then ~/.env without overriding existing values."""
    for path in (Path.cwd() / ".env", Path.home() / ".env"):
        for name, value in _parse_env_file(path).items():
            os.environ.setdefault(name, value)


def _slugify(text: str, max_len: int = 40) -> str:
    value = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    value = re.sub(r"[-\s]+", "-", value)[:max_len]
    return value or "image"


def _resolve_size(value: str | None) -> str | None:
    if not value or value.lower() == "auto":
        return None
    return SIZE_SHORTCUTS.get(value.lower(), value)


def _prompt_from_args(args: argparse.Namespace) -> str:
    if bool(args.prompt) == bool(args.prompt_file):
        raise CliError("Provide exactly one of --prompt or --prompt-file.")
    if args.prompt_file:
        path = Path(args.prompt_file).expanduser()
        if not path.is_file():
            raise CliError(f"Prompt file not found: {path}")
        prompt = path.read_text(encoding="utf-8").strip()
    else:
        prompt = str(args.prompt).strip()
    if not prompt:
        raise CliError("Prompt must not be empty.")
    return prompt


def _validate_size(value: str | None) -> None:
    if not value or value.lower() == "auto" or value.lower() in SIZE_SHORTCUTS:
        return
    if not re.fullmatch(r"\d+x\d+", value):
        raise CliError("--size must be auto, a shortcut, or WIDTHxHEIGHT.")
    width, height = (int(part) for part in value.lower().split("x"))
    if width <= 0 or height <= 0:
        raise CliError("--size dimensions must be positive.")


def _validate_model_options(args: argparse.Namespace) -> None:
    model = args.model
    size = _resolve_size(args.size)
    image25 = bool(GPT_IMAGE_25_MODELS.fullmatch(model))
    image2 = bool(GPT_IMAGE_2_MODELS.fullmatch(model))
    standard = bool(STANDARD_GPT_IMAGE_MODELS.fullmatch(model))

    if args.quality in ("xhigh", "max") and not image25:
        raise CliError("--quality xhigh/max requires a gpt-image-2.5-flare or gpt-image-2.5-sunburst model.")

    if image2 and args.input_fidelity:
        raise CliError("--input-fidelity is not supported by gpt-image-2.")

    if standard:
        if size not in {"auto", "1024x1024", "1536x1024", "1024x1536"}:
            raise CliError(
                "This model accepts --size 1024x1024, 1536x1024, 1024x1536, or auto."
            )
        if args.quality not in {"auto", "low", "medium", "high"}:
            raise CliError("This model accepts --quality auto, low, medium, or high.")

    if image25 or image2:
        if size == "auto":
            return
        match = re.fullmatch(r"(\d+)x(\d+)", size or "")
        if not match:
            raise CliError("This model requires --size auto or WIDTHxHEIGHT.")
        width, height = (int(part) for part in match.groups())
        pixels = width * height
        if (
            width % 16
            or height % 16
            or max(width, height) > 3840
            or max(width, height) > 3 * min(width, height)
            or not 655360 <= pixels <= 8294400
        ):
            raise CliError(
                "This model requires 16px multiples, edges <=3840px, an aspect ratio <=3:1, "
                "and 655360-8294400 pixels."
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gpt-image",
        description="Generate or edit images through the OpenAI Image API.",
    )
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("-p", "--prompt", help="Text prompt or edit instruction.")
    prompt.add_argument("--prompt-file", help="Read the prompt from a UTF-8 text file.")
    parser.add_argument(
        "--model",
        default=os.getenv("GPT_IMAGE_MODEL") or DEFAULT_MODEL,
        help=f"Model ID. Uses GPT_IMAGE_MODEL when configured; defaults to {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--size",
        default=os.getenv("GPT_IMAGE_SIZE", "1024x1024"),
        help="auto, WIDTHxHEIGHT, or 1k/2k/4k/portrait/landscape/square/wide/tall.",
    )
    parser.add_argument("--quality", choices=QUALITY_CHOICES, default="auto")
    parser.add_argument("-n", "--n", type=int, default=1, help="Number of images (1-10).")
    parser.add_argument("--background", choices=("auto", "opaque", "transparent"))
    parser.add_argument("--moderation", choices=("auto", "low"), default="auto")
    parser.add_argument("-i", "--image", action="append", type=Path, help="Reference image; repeat for multiple images.")
    parser.add_argument("-m", "--mask", type=Path, help="PNG mask for inpainting; requires --image.")
    parser.add_argument("--input-fidelity", choices=("low", "high"), help="Edit-only input fidelity.")
    parser.add_argument("--format", "--output-format", dest="output_format", choices=FORMAT_CHOICES, default="png")
    parser.add_argument("--compression", "--output-compression", type=int, help="0-100 compression for JPEG/WebP.")
    parser.add_argument("--user", help="Optional end-user identifier.")
    parser.add_argument("-f", "--out", "--file", dest="out", type=Path, help="Output file path. Defaults to output/imagegen/.")
    parser.add_argument("--out-dir", type=Path, help="Directory for numbered outputs.")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing output files.")
    parser.add_argument("--dry-run", action="store_true", help="Print the request without calling the API.")
    parser.add_argument("--json", action="store_true", help="Emit one machine-readable JSON object.")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = _build_parser().parse_args(argv)
    if not 1 <= args.n <= 10:
        raise CliError("--n must be between 1 and 10.")
    if args.compression is not None and not 0 <= args.compression <= 100:
        raise CliError("--compression must be between 0 and 100.")
    if args.background == "transparent" and args.output_format == "jpeg":
        raise CliError("--background transparent requires --format png or webp.")
    if args.mask and not args.image:
        raise CliError("--mask requires at least one --image.")
    if args.input_fidelity and not args.image:
        raise CliError("--input-fidelity is only valid with --image.")
    _validate_size(args.size)
    _validate_model_options(args)
    return args


def _output_paths(args: argparse.Namespace, prompt: str) -> list[Path]:
    extension = "." + args.output_format
    if args.out_dir:
        directory = args.out_dir.expanduser().resolve()
        return [directory / f"image_{index}{extension}" for index in range(1, args.n + 1)]

    if args.out:
        output = args.out.expanduser().resolve()
        if not output.suffix:
            output = output.with_suffix(extension)
    else:
        directory = (Path.cwd() / "output" / "imagegen").resolve()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = directory / f"{stamp}-{_slugify(prompt)}{extension}"

    if args.n == 1:
        return [output]
    return [output.with_name(f"{output.stem}_{index}{output.suffix}") for index in range(1, args.n + 1)]


def _check_input_files(args: argparse.Namespace) -> list[Path]:
    images = [path.expanduser().resolve() for path in (args.image or [])]
    for path in images:
        if not path.is_file():
            raise CliError(f"Input image not found: {path}")
        size = path.stat().st_size
        if size == 0:
            raise CliError(f"Input image is empty: {path}")
        if size > MAX_IMAGE_BYTES:
            raise CliError(f"Input image exceeds the 50 MB limit: {path}")
    if args.mask:
        args.mask = args.mask.expanduser().resolve()
        if not args.mask.is_file():
            raise CliError(f"Mask not found: {args.mask}")
        size = args.mask.stat().st_size
        if size == 0:
            raise CliError(f"Mask is empty: {args.mask}")
        if size > MAX_IMAGE_BYTES:
            raise CliError(f"Mask exceeds the 50 MB limit: {args.mask}")
        _validate_mask(args.mask)
    return images


def _validate_mask(path: Path) -> None:
    if path.suffix.lower() != ".png":
        raise CliError(f"Mask must be a PNG file: {path}")
    data = path.read_bytes()
    if len(data) < 33 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise CliError(f"Mask is not a valid PNG file: {path}")

    color_type = data[25]
    if color_type in (4, 6):
        return

    offset = 8
    has_transparency = False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            break
        chunk_type = data[offset + 4 : offset + 8]
        if chunk_type == b"tRNS":
            has_transparency = True
            break
        if chunk_type == b"IEND":
            break
        offset = chunk_end

    if not has_transparency:
        raise CliError("Mask PNG must contain an alpha channel or transparency data.")


def _payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "size": _resolve_size(args.size),
        "quality": args.quality,
        "n": args.n,
        "background": args.background,
        "output_format": args.output_format,
        "user": args.user,
    }
    if args.compression is not None and args.output_format in ("jpeg", "webp"):
        payload["output_compression"] = args.compression
    if not args.image:
        payload["moderation"] = args.moderation
    if args.image and args.input_fidelity:
        payload["input_fidelity"] = args.input_fidelity
    return {key: value for key, value in payload.items() if value is not None}


def _load_openai() -> tuple[Any, type[BaseException]]:
    try:
        from openai import APIError, OpenAI
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise CliError(
            "The openai package is missing. Install it with `python -m pip install openai` "
            "or run this file with `uv run --script scripts/generate.py ...`."
        ) from exc
    return OpenAI, APIError


def _format_api_error(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    detail = str(exc).strip()
    name = type(exc).__name__
    if status == 401:
        message = "OpenAI API authentication failed"
    elif status == 403:
        message = "OpenAI API access was denied"
    elif status == 404:
        message = "OpenAI API endpoint or model was not found"
    elif status == 429:
        message = "OpenAI API rate limit or quota was exceeded"
    elif isinstance(status, int) and status >= 500:
        message = f"OpenAI API server error (HTTP {status})"
    elif isinstance(status, int):
        message = f"OpenAI API rejected the request (HTTP {status})"
    elif "Connection" in name or "Timeout" in name:
        message = "Could not connect to the OpenAI API"
    else:
        message = f"OpenAI API error ({name})"

    request_id = getattr(exc, "request_id", None)
    if not request_id:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) or {}
        request_id = headers.get("x-request-id")
    if request_id:
        message += f" [request_id={request_id}]"
    return f"{message}: {detail}" if detail else message


def _new_client(OpenAI: Any) -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise CliError("OPENAI_API_KEY is not set.")
    # Let the official SDK read OPENAI_API_KEY and OPENAI_BASE_URL itself.
    return OpenAI(max_retries=0)


def _call_generate(client: Any, payload: dict[str, Any]) -> Any:
    return client.images.generate(**payload)


def _call_edit(client: Any, payload: dict[str, Any], images: list[Path], mask: Path | None) -> Any:
    handles = [path.open("rb") for path in images]
    mask_handle = mask.open("rb") if mask else None
    try:
        request = dict(payload)
        request["image"] = handles
        if mask_handle:
            request["mask"] = mask_handle
        return client.images.edit(**request)
    finally:
        for handle in handles:
            handle.close()
        if mask_handle:
            mask_handle.close()


def _item_value(item: Any, key: str) -> Any:
    value = getattr(item, key, None)
    if value is not None:
        return value
    if isinstance(item, dict):
        return item.get(key)
    return None


def _image_bytes(item: Any) -> bytes:
    encoded = _item_value(item, "b64_json")
    if encoded:
        try:
            return base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise CliError("The API returned invalid base64 image data.") from exc
    url = _item_value(item, "url")
    if url:
        try:
            with urllib.request.urlopen(str(url), timeout=300) as response:  # noqa: S310
                return response.read()
        except Exception as exc:  # pragma: no cover - network-dependent
            raise CliError(f"Could not download the image URL returned by the API: {exc}") from exc
    raise CliError("The API response item contains neither b64_json nor url.")


def _write_outputs(result: Any, paths: list[Path], force: bool) -> list[Path]:
    data = getattr(result, "data", None)
    if data is None and isinstance(result, dict):
        data = result.get("data")
    if not data:
        raise CliError("The API returned no image data.")
    if len(data) < len(paths):
        raise CliError(f"The API returned {len(data)} image(s), expected {len(paths)}.")
    for path in paths:
        if path.exists() and not force:
            raise CliError(f"Output already exists: {path}. Use --force to overwrite it.")
    written: list[Path] = []
    for item, path in zip(data, paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_image_bytes(item))
        written.append(path)
    return written


def _emit(value: dict[str, Any], json_mode: bool, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if json_mode:
        print(json.dumps(value, ensure_ascii=False), file=stream)
    elif error:
        print(f"error: {value.get('error', 'unknown error')}", file=stream)
    else:
        for path in value.get("paths", []):
            print(path)


def main(argv: list[str] | None = None) -> int:
    raw_args = argv if argv is not None else sys.argv[1:]
    json_mode = "--json" in raw_args
    try:
        _load_env_chain()
        args = parse_args(argv)
        prompt = _prompt_from_args(args)
        images = _check_input_files(args)
        paths = _output_paths(args, prompt)
        payload = _payload(args, prompt)
        mode = "edit" if images else "generate"
        endpoint = "/v1/images/edits" if images else "/v1/images/generations"

        if args.dry_run:
            _emit({
                "ok": True,
                "dry_run": True,
                "mode": mode,
                "endpoint": endpoint,
                "model": args.model,
                "payload": payload,
                "paths": [str(path) for path in paths],
                "images": [str(path) for path in images],
                "mask": str(args.mask) if args.mask else None,
            }, json_mode)
            return 0

        OpenAI, OpenAIError = _load_openai()
        client = _new_client(OpenAI)
        try:
            result = _call_edit(client, payload, images, args.mask) if images else _call_generate(client, payload)
        except OpenAIError as exc:
            raise CliError(_format_api_error(exc)) from exc
        written = _write_outputs(result, paths, args.force)
        _emit({
            "ok": True,
            "mode": mode,
            "endpoint": endpoint,
            "model": args.model,
            "paths": [str(path) for path in written],
        }, json_mode)
        return 0
    except CliError as exc:
        _emit({"ok": False, "error": str(exc)}, json_mode, error=True)
        return 2
    except Exception as exc:
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, json_mode, error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
