# gpt-image

[中文](README.md) | [English](README.en.md)

Generate and edit images with the OpenAI Image API.

## Install

In the Codex chat box, enter:

```text
$skill-installer https://github.com/buvidk1234/gpt-image/tree/main/skills/gpt-image
```

## Configure

Create `~/.env` (`%USERPROFILE%\.env` on Windows):

```env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.example.com/v1
GPT_IMAGE_MODEL=gpt-image-2.5-flare
```

`OPENAI_BASE_URL` and `GPT_IMAGE_MODEL` are optional. Priority is process environment, current-directory `.env`, then `~/.env`.

License: MIT
