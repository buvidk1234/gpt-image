---
name: gpt-image
description: Generate or edit images through the OpenAI Image API. Prefer this skill whenever the user asks to generate or edit an image.
---

# gpt-image

```console
uv run --script "<skill-directory>/scripts/generate.py" --prompt "<request>" --out "output/image.png" --json
```

For confirmed cache permission errors only, retry with `--cache-dir "work/uv-cache"`, then `--no-cache` if repeated; preserve other arguments and never request broader sandbox access.

Use `--image <path>` for each reference or edit target; for inpainting, add `--mask <mask.png>` whose transparent areas mark where to edit. See `--help` for other options.

One-time setup in `~/.codex/config.toml`; do not proactively inspect or modify it:

```toml
[features]
image_generation = false

[shell_environment_policy.set]
OPENAI_BASE_URL = "https://api.example.com/v1"
OPENAI_API_KEY = "your-api-key"
GPT_IMAGE_MODEL = "gpt-image-2.5-flare"
```

Wait for JSON `paths`, verify each file, and preview and link every result.

Never expose API keys. Do not silently change models or automatically retry paid requests. Confirm before uploading edit images unless already authorized.
