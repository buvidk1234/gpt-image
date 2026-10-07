# gpt-image

[中文](README.md) | [English](README.en.md)

Generate and edit images with the OpenAI Image API.

## Install

In the Codex chat box, enter:

```text
$skill-installer https://github.com/buvidk1234/gpt-image/tree/main/skills/gpt-image
```

## Configure

Configure `~/.codex/config.toml`:

```toml
[features]
image_generation = false

[shell_environment_policy.set]
OPENAI_BASE_URL = "https://api.example.com/v1"
OPENAI_API_KEY = "your-api-key"
GPT_IMAGE_MODEL = "gpt-image-2.5-flare"
```

License: MIT
