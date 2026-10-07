# gpt-image

[中文](README.md) | [English](README.en.md)

使用 OpenAI Image API 生成和编辑图片。

## 安装

在 Codex 对话框中输入：

```text
$skill-installer https://github.com/buvidk1234/gpt-image/tree/main/skills/gpt-image
```

## 配置

在 `~/.codex/config.toml` 中配置：

```toml
[features]
image_generation = false

[shell_environment_policy.set]
OPENAI_BASE_URL = "https://api.example.com/v1"
OPENAI_API_KEY = "your-api-key"
GPT_IMAGE_MODEL = "gpt-image-2.5-flare"
```

许可证：MIT
