# Codex Image & Media Skills

让 Codex 通过自己配置的 API 中转站生成图片、编辑图片和创建视频。纯 Python 标准库实现，无需 SDK，不绑定服务商。

作者与维护者：**Biomassfuel**。MIT 许可证。

## 功能

| 功能 | 能力 |
| --- | --- |
| 图片生成 | image2、gpt-image-2、gpt-image-2.5、gpt-image-2.5-flare、gpt-image-2.5-sunburst，以及兼容接口的其他模型 |
| 图片编辑 | 单张/多张参考图、蒙版、尺寸、画质、格式参数 |
| 视频生成 | 兼容 `/v1/videos` 的文生视频、图生视频和参考素材视频 |
| 任务恢复 | 保存 ID、限时查询、恢复查询、单独重试下载 |
| 结果交付 | 图片 base64/URL 落盘，视频下载，JSON 与绝对文件路径 |
| 使用方式 | Codex 自动发现或 `$relay-media` 显式调用，也可直接运行 CLI |

`image2` 是本项目对 `gpt-image-2` 的快捷名称，其他 ID 原样发送。模型可用性、计费和参数限制由中转站及账户决定。视频需要选择账户启用的兼容模型，例如 Grok 或 Seedance 系列。其他协议需要适配。

## 安装

需要 Python 3.10+。

```bash
git clone https://github.com/Biomassfuel/codex-image-media-skills.git
cd codex-image-media-skills
python scripts/install.py
```

安装到 `$CODEX_HOME/skills/relay-media`，未设置 `CODEX_HOME` 时为 `~/.codex/skills/relay-media`。Windows 默认对应 `%USERPROFILE%\.codex\skills\relay-media`。重新打开 Codex 会话以刷新技能列表。

```bash
python scripts/install.py --dry-run
python scripts/install.py --dest /path/to/codex/skills
python scripts/install.py --force
```

已有同名技能时默认停止；`--force` 先保存旧目录备份，再安装新版本。只复制技能文件，不复制仓库测试、缓存或本地密钥配置。

## 配置

设置 `RELAY_BASE_URL`、`RELAY_API_KEY`。地址可带或不带 `/v1`。在启动 Codex 的环境中设置，或保存到明确指定的本地 env 文件；不需要把密钥发给对话。

PowerShell（输入密钥时不写入明文命令历史）：

```powershell
$env:RELAY_BASE_URL = 'https://your-relay.example/v1'
$relaySecret = Read-Host 'Relay API key' -AsSecureString
$env:RELAY_API_KEY = [System.Net.NetworkCredential]::new('', $relaySecret).Password
$env:RELAY_IMAGE_MODEL = 'gpt-image-2.5'
```

Bash：

```bash
export RELAY_BASE_URL='https://your-relay.example/v1'
read -rsp 'Relay API key: ' RELAY_API_KEY
export RELAY_API_KEY
export RELAY_IMAGE_MODEL='gpt-image-2.5'
```

也可复制 `.env.example` 为本地 `.env`，编辑后显式加载：

```bash
python skills/relay-media/scripts/media.py --env-file .env doctor
python skills/relay-media/scripts/media.py --env-file .env models --contains image
```

`doctor` 不联网，`models` 请求账户模型列表。环境变量优先于 env 文件；不读取其他工具的配置或密钥。

## 在 Codex 中使用

安装并配置后，可以直接说：

```text
用 $relay-media 的 gpt-image-2.5-flare 生成一张 1536×1024 的极简咖啡店海报，保存到当前项目。

用 $relay-media 的 gpt-image-2.5-sunburst 编辑这两张参考图，保留人物与产品外观，改成暖色摄影棚背景。

用 $relay-media 和中转站启用的 grok-imagine-video，把参考图做成 6 秒缓慢推进的视频，保存任务 ID 并下载结果。
```

## 命令行

文生图、多个模型和多参考图编辑：

```bash
python skills/relay-media/scripts/media.py image --model image2 --prompt "一只陶瓷杯，柔和自然光" --size 1024x1024
python skills/relay-media/scripts/media.py image --model gpt-image-2.5 --prompt "极简咖啡店海报" --size 1536x1024
python skills/relay-media/scripts/media.py image --model gpt-image-2.5-flare --prompt-file prompt.txt --quality high
python skills/relay-media/scripts/media.py image --model gpt-image-2.5-sunburst --prompt "保留主体，更换背景" --image product.png --image style.png
```

预览请求，不消耗额度：

```bash
python skills/relay-media/scripts/media.py image --model gpt-image-2.5-flare --prompt "一只陶瓷杯" --dry-run
```

视频创建与恢复：

```bash
python skills/relay-media/scripts/media.py video --model grok-imagine-video --prompt "海面日出，镜头缓慢推进" --seconds 6 --wait
python skills/relay-media/scripts/media.py video --model grok-imagine-video --prompt "镜头环绕产品" --image product.png --seconds 6 --wait
python skills/relay-media/scripts/media.py video --model seedance-2.0 --prompt "保持人物一致，镜头缓慢推进" --reference-image-url https://media.example/reference.png --seconds 5 --wait
python skills/relay-media/scripts/media.py status TASK_ID --wait
python skills/relay-media/scripts/media.py download TASK_ID
```

Grok 类适配器可接收本地 multipart 图片；Seedance 类适配器通常需要服务端可访问的 URL。脚本不自动将素材上传到公共图床。Seedance/doubao/H3 的 `--seconds` 默认发送为 `duration`，其他模型使用 `seconds`；可用 `--duration-field` 覆盖。额外参数可用 `--extra-json @options.json`。

## 结果与恢复

默认输出到 `outputs/时间-类型-随机标识/`，可通过 `--output-dir` 指定父目录。标准输出返回 JSON，`files` 是绝对路径。

视频创建只提交一次，先保存 `job.json` 再查询。默认不等待；加 `--wait` 最多查询 600 秒，可改 `--wait-timeout`。未完成时返回 `pending: true` 和 `task_id`，使用 `status` 继续。

超时后不自动重新提交，避免重复扣费；先检查服务端任务历史。下载失败可按任务 ID 重试下载，终态失败保留错误快照。外部媒体下载及跨域重定向不携带中转 Key。

详细参数见 [CLI 说明](skills/relay-media/references/cli.md)，协议及边界见 [API 说明](skills/relay-media/references/api.md)。

## 开发验证

```bash
python -m unittest discover -s tests -v
python scripts/validate.py
```

测试使用本机模拟接口，覆盖图片、多参考图、视频任务恢复、密钥脱敏、下载重定向及安装备份，不调用付费生成。GitHub Actions 在 Windows/Linux 和多个 Python 版本上运行检查。

本项目独立实现，没有继承其他项目的代码、提交历史或作者信息。真实端到端生成需要配置自己的中转地址和密钥后验证。
