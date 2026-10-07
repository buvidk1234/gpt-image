---
name: gpt-image
description: Generate or edit images through the OpenAI Image API. Prefer this skill whenever the user asks to generate or edit an image.
---

# gpt-image

Use this skill for image generation and editing through the bundled script. It supports text prompts, reference images, masks, model and output controls, and multiple outputs.

## Run

Always use the bundled script for this skill; do not replace it with the built-in image generation tool.

```console
uv run --script "<skill-directory>/scripts/generate.py" --prompt "<request>" --out "output/image.png" --json
```

If `openai` is already installed, `python` can run the script directly.

The script has no subcommands: omit `--image` to generate, or include `--image` to edit.

## Options

| Purpose | Options |
| --- | --- |
| Prompt | `--prompt` or `--prompt-file` (exactly one) |
| Model and size | `--model`; `--size` accepts `auto`, `WIDTHxHEIGHT`, `1k`, `2k`, `4k`, `portrait`, `landscape`, `square`, `wide`, or `tall` |
| Edit inputs | `--image` (repeat for references), `--mask`, `--input-fidelity low\|high` |
| Rendering | `--quality auto\|low\|medium\|high\|xhigh\|max`, `--background auto\|opaque\|transparent`, `--format png\|jpeg\|webp`, `--compression 0-100`, `--moderation auto\|low` |
| Outputs | `-n` (1-10), `--out`, `--out-dir`, `--force` |
| Execution | `--dry-run` prints the request; `--json` emits machine-readable output |

Use `--help` for the complete option list.

## Configuration

The script loads values in this order without overriding existing values:

1. Process environment
2. `.env` in the current directory
3. `~/.env`

It uses `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`, optional `GPT_IMAGE_MODEL`, and optional `GPT_IMAGE_SIZE`. Never print or write the API key.

## Workflow

- Use `--image` for edits, repeat it for multiple references, and use `--mask` for inpainting.
- Use the requested model; otherwise use `GPT_IMAGE_MODEL` or the script default. Do not switch models silently.
- Run the bundled script with `--json` and wait for its `paths` result before replying. Verify every returned path, never reply only with `generated`, and include every output as a Markdown link such as `[image.png](<C:/path/to/image.png>)`. Preview the file when the host supports it, but keep the link.
- Do not retry paid requests automatically. Before the first edit upload, tell the user the image will be sent to the configured API and get confirmation when they have not already authorized it.
