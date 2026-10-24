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
| 交互选择 | AI 用编号菜单询问模型、提示词版本、12 种分辨率和画质，支持补充提示词，自动映射参数并执行 |
| 强制选择 | 未显式选择模型/尺寸/画质时 `image` 返回 `missing_selection`，不会静默使用默认值生成 |
| 提示词 | 每次提供 3 个优化版本 + 1 个原版直出，用户回复编号即可 |
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

### DSH 用户

DSH 从 `%USERPROFILE%\.dsh\skills` 加载技能，不是 `~/.codex/skills`。安装到 DSH：

```powershell
python scripts/install.py --dest "$env:USERPROFILE\.dsh\skills" --force
```

DSH 会热加载技能目录；如果当前会话前面已经加载过旧版，开一个新会话最干净。用下面命令确认版本：

```powershell
python "$env:USERPROFILE\.dsh\skills\relay-media\scripts\media.py" doctor
```

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

`doctor` 和 `choices` 不联网，`models` 请求账户模型列表。环境变量优先于 env 文件；不读取其他工具的配置或密钥。

## 交互式生成（推荐）

直接说需求即可，不需要自己查尺寸、画质或复制提示词。AI 会按“模型 → 提示词/补充 → 分辨率/画质”给出选择：

```text
模型（回复编号）
1. gpt-image-2.5 · 画质优先（推荐）
2. gpt-image-2 · 精确尺寸优先
3. gpt-image-2.5-flare · 风格化；可能忽略尺寸
4. gpt-image-2.5-sunburst · 方形风格；支持 12 种尺寸

提示词版本（回复编号）
0. 原版直出：用你刚才的描述，不改写
1. 优化 A｜忠实增强：保留原意，补足构图、光线、材质
2. 优化 B｜风格强化：确定一种统一的视觉语言
3. 优化 C｜商业成片：留出文案空间，适合海报/电商/社媒

补充提示词（可选，直接输入）
例如：加一行英文标题 / 不要文字、水印 / 背景更虚化 / 服装换成...
没有补充就回复“无”。

分辨率（全部 12 个，回复编号）
1. 1024×1024 · 1:1
2. 1536×1024 · 3:2
3. 1024×1536 · 2:3
4. 1792×1024 · 7:4
5. 1024×1792 · 4:7
6. 2048×2048 · 2K · 1:1
7. 2048×1152 · 2K · 16:9
8. 1152×2048 · 2K · 9:16
9. 2560×1440 · 4K · 16:9
10. 1440×2560 · 4K · 9:16
11. 3840×2160 · 4K · 16:9
12. 2160×3840 · 4K · 9:16

画质（回复编号）
1. auto · 模型自动（推荐）
2. low · 快速草稿
3. medium · 标准
4. high · 最高细节
```

回复示例：`1 1 7 1 + 加一行英文标题 “MORNING”` 表示 `gpt-image-2.5` + 优化 A + 2048×1152 + auto，并补充标题。也可以直接说“用 gpt-image-2、原版、竖屏 2K、high”；已经说过的部分不会再问。

**12 个分辨率始终全部展示**，不会因为“半身像适合竖版”就删成 4 个；AI 只能标记推荐项，不能隐藏其余选项。如果提问卡片一页只能放 5 个，会按 `size.pages` 分成 1–4、5–8、9–12 三页，不会删掉任何一项。`gpt-image-2.5-flare` 已观察到可能忽略 `--size`，选择它时 AI 会在生成前提醒；要精确画布优先选 `gpt-image-2` 或 `gpt-image-2.5`。说“默认”或“你决定”时使用推荐项。AI 会把编号映射成精确参数、自己写提示词文件并调用 CLI，用户不需要复制命令、尺寸或提示词。

### 为什么还看不到模型选择？

如果你看到的仍然是“直接问尺寸”、只有 4–5 个选项、没有模型卡片，说明当前会话加载的是旧技能缓存。新版菜单版本是 `2026-10-24.4`，`choices` 会先返回 `model_required: true` 和 4 个模型选项；未选模型时不会返回尺寸。

新版 `image` 还加了硬门禁：没有显式 `--model`、`--size`、`--quality` 时不会生成，而是返回 `missing_selection`。所以即使 AI 想跳过提问直接生成，也会被拦下，必须回来问用户。

处理方式：**完全退出 Codex 进程再重新启动，然后新建一个对话**。只关窗口或只新建对话都不够；Windows 上 Codex 可能继续留在托盘/后台，旧进程会一直缓存旧技能。请在任务管理器确认 `codex.exe` 已结束（或从托盘菜单选择退出），再重新启动。在旧的“少女插画生成”对话里继续也不够，因为旧对话上下文里仍然带着旧版技能说明。新对话里再运行 `$relay-media`。也可以用下面命令确认版本：

```bash
python C:\Users\25647\.codex\skills\relay-media\scripts\media.py doctor
```

输出里应有 `"menu_version": "2026-10-24.4"`。

## 在 Codex 中使用

安装并配置后，可以直接说：

```text
用 $relay-media 生成一张极简咖啡店海报。          # 会先给模型/提示词/补充/分辨率/画质菜单

用 $relay-media 的 gpt-image-2 生成一张 1536×1024 的极简咖啡店海报，保存到当前项目。

用 $relay-media 的 gpt-image-2.5-sunburst 编辑这两张参考图，保留人物与产品外观，改成暖色摄影棚背景。

用 $relay-media 和中转站启用的 grok-imagine-video，把参考图做成 6 秒缓慢推进的视频，保存任务 ID 并下载结果。
```

## 命令行

查看交互菜单（离线，不需要密钥）：

```bash
python skills/relay-media/scripts/media.py choices
python skills/relay-media/scripts/media.py choices --model gpt-image-2.5
python skills/relay-media/scripts/media.py choices --model gpt-image-2.5 --lang en
```

文生图、多个模型和多参考图编辑：

```bash
python skills/relay-media/scripts/media.py image --model image2 --prompt "一只陶瓷杯，柔和自然光" --size 1024x1024
python skills/relay-media/scripts/media.py image --model gpt-image-2.5 --prompt "极简咖啡店海报" --size 1536x1024
python skills/relay-media/scripts/media.py image --model gpt-image-2.5-flare --prompt-file prompt.txt --quality high
python skills/relay-media/scripts/media.py image --model gpt-image-2.5-sunburst --prompt "保留主体，更换背景" --size 1024x1024 --quality high --image product.png --image style.png
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

详细参数见 [CLI 说明](skills/relay-media/references/cli.md)，提示词写法见 [提示词指南](skills/relay-media/references/prompting.md)，协议及边界见 [API 说明](skills/relay-media/references/api.md)。

## 开发验证

```bash
python -m unittest discover -s tests -v
python scripts/validate.py
```

测试使用本机模拟接口，覆盖图片、多参考图、视频任务恢复、密钥脱敏、下载重定向及安装备份，不调用付费生成。GitHub Actions 在 Windows/Linux 和多个 Python 版本上运行检查。

本项目独立实现，没有继承其他项目的代码、提交历史或作者信息。真实端到端生成需要配置自己的中转地址和密钥后验证。
