---
name: relay-media
description: Generate or edit images and create videos through a user-configured media relay, including image2, gpt-image-2.5, flare, sunburst and compatible asynchronous video models. For images, ask for the model, prompt version, optional extra prompt details, one of all catalog resolutions, and quality as numbered choices; run the selected request without asking the user to copy values or commands.
---

# Relay Media

## STOP — image requests

Do not run the `image` command until all of these are true:

1. You ran `choices` without `--model`.
2. You showed every `model_options` entry and the user chose a model.
3. You ran `choices --model <id>`.
4. You showed every size option (12 for enum models) and the user chose one.
5. You showed every quality option and the user chose one.
6. You asked for the optional supplement.

`image` enforces this: an incomplete selection fails with `missing_selection`. That error means "go back and ask", not "retry with `--unattended`". Never use `--unattended` for an interactive request; it exists only for automation and tests.

Use `scripts/media.py` relative to this skill directory. It requires Python 3.10+ and the standard library only. Read [the CLI reference](references/cli.md) for arguments, [the prompt guide](references/prompting.md) for the image conversation, and [the API notes](references/api.md) when adapting a provider.

## Version check

This menu is `2026-10-24.4`; `doctor` and `choices` report `menu_version`. If a session shows a size/quality card before a model card, shows only 4–5 sizes, or runs `catalog` as its first step, it is using an old cached skill or an old conversation context. Stop and ask the user to fully quit the Codex process (not just the window), restart it, and start a new conversation. Continuing an old thread keeps the old skill text in context. Do not generate from the stale flow.

## Configuration and model choice

- Run `python <skill-dir>/scripts/media.py doctor` to inspect configuration without a request. `RELAY_BASE_URL` selects the user's relay; `RELAY_API_KEY` contains its key. An explicit `--env-file <local-file>` is supported before the subcommand. Existing environment variables take precedence.
- Requests use system proxy settings by default. For a suspected proxy disconnect, use global `--no-proxy` to connect directly for that invocation; it does not change system settings. A disconnected image request may already be billed, so check its saved `failure.json` and provider history before resubmitting.
- If configuration is missing, ask the user to configure it locally. Never ask for a key in chat, put a key in command arguments, or inspect unrelated credential files. Do not change the relay or borrow another service's key.
- `models` performs a read-only `/v1/models` lookup of what the account can see. `catalog` reads the local catalog offline and prints every image model with its allowed options and its `size_reliability`.
- `choices` reads the same catalog offline and returns the model list, prompt modes, supplement prompt, size options, quality options, defaults and reply hint. Run it before the first image request in a conversation.
- `choices` without `--model` is the model-selection step: it returns `model_required: true`, `model_options`, and `size.mode: pending`. It deliberately does not return a default model's sizes. After the user picks a model, run `choices --model <id>` for the full size and quality menu.
- Do not use `catalog` as the first step; `catalog` is only for advanced inspection. Do not use `RELAY_IMAGE_MODEL` as a substitute for asking.
- Never silently use `RELAY_IMAGE_MODEL` or a hard-coded model. Ask the user to choose a model first, unless they already named one. If they say "你决定", choose and explain: `gpt-image-2.5` for quality, `gpt-image-2` when the exact canvas matters.
- Model tradeoffs: `gpt-image-2.5` is quality-first; `gpt-image-2` is exact-canvas-first; `gpt-image-2.5-flare` is style-led but has been observed to ignore `--size`; `gpt-image-2.5-sunburst` is square-style and also supports the 12-size menu. All four current models expose size choices.
- Honor the exact requested model. Only `image2` expands to `gpt-image-2`; cataloged models keep their ID. Videos require `--model` or `RELAY_VIDEO_MODEL`.
- A model listing does not establish account permissions or parameter support. Explain a provider rejection instead of silently substituting another model.

## Image requests: choose model, prompt, size, quality

Do not ask the user to type a size or quality, and do not ask them to copy or paste a prompt. Do not print a command for them to run. When the user asks for an image or an edit, use the question UI and cover these decisions in order:

1. **Model (mandatory first question)** — run `choices` without `--model` and show every `model_options` entry. `model_required` is `true`; do not show a size or quality card before the user picks a model.
2. **Prompt version + optional supplement** — after the model is chosen, run `choices --model <chosen>` and show the original plus three optimized directions, and ask for any extra prompt details in a free-text field.
3. **Resolution + quality** — show every size option and every quality option for that model.

```text
python <skill-dir>/scripts/media.py choices
python <skill-dir>/scripts/media.py choices --model gpt-image-2.5
```

The JSON gives `model_options` (all catalog models with roles and reliability), `prompt.options` (the original plus three optimized directions), `supplement` (free-text hint and examples), `size.options` (every canvas with label, aspect, orientation and 2K/4K tier), `size.pages` (groups of four for paginated question cards), `quality.options` and `reply_hint`. Render it in the user's language, one line per option, and mark the recommended item.

The standard GPT Image size menu is exactly these 12 values, in this order:

```text
1024x1024   1536x1024   1024x1536   1792x1024   1024x1792
2048x2048   2048x1152   1152x2048   2560x1440   1440x2560
3840x2160   2160x3840
```

- **Show all 12.** Never filter, rank away, or replace the list with a composition-specific subset such as "four sizes for a half-body portrait". You may mark one as recommended, but every option must remain visible.
- If the question UI caps a card at 5 options, do not show 5 and drop the rest. Use `size.pages` (three pages of four: 1–4, 5–8, 9–12) or a single text list. The same rule applies to every model's full size list.
- Do not add `auto` as a size. Quality is `auto`, `low`, `medium` or `high` when the catalog lists them.
- If the user already named a model, size, quality or prompt version, do not ask for it again; map their words to the exact catalog value.
- If the user says "默认", "你决定" or "直接生成", use the recommended model and options and proceed. If they require an exact canvas, prefer `gpt-image-2`.
- Accept a reply such as `1 1 7 1`, `2 优化B 2048×1152 high` or `gpt-image-2 原版 竖屏 2K`. Map it yourself.
- Ask at most one short follow-up if a reply is ambiguous. Do not restart the whole menu.
- Never ask the user to copy a prompt, a size, a quality value or a command. Write the final prompt to a temporary UTF-8 file in the task workspace and pass `--prompt-file`, then run the image command yourself.
- After the choice, show the final prompt briefly for transparency and generate immediately.

### Three prompt versions plus the original

Prepare these before showing the menu:

| # | Version | What it does |
| --- | --- | --- |
| 0 | Original | Uses the user's wording unchanged. Adds no style, camera, lighting or details. |
| 1 | Faithful enhancement | Keeps subject, action and intent; adds composition, lighting, materials, background and lens/render details. |
| 2 | Style-led | Commits to one coherent visual language that fits the subject, such as editorial photography, cinematic still, 3D render or ink illustration. |
| 3 | Commercial/layout | Builds a clean frame with negative space and text-safe areas for a poster, e-commerce image or social post. |

The three optimized versions must differ in art direction, not just adjectives. Show a one-line direction for each in the menu; keep the full prompts out of the menu unless the user asks to see them. For edits, preserve the parts the user wants unchanged and state exactly what changes. Do not add text, logos or watermarks unless requested; quote requested text exactly. Follow [the prompt guide](references/prompting.md).

### Supplement prompt

After the prompt version, always offer the optional supplement from `choices`:

- Ask: "补充提示词（可选）：要加文字、改背景、调光线、换服装/道具，或指定不要出现的内容吗？没有就回复“无”。"
- If the user supplies details, append them as an explicit `Additional requirements:` block to the selected prompt. Let the supplement override the variant where they conflict, and show the final prompt.
- If the supplement adds text, quote it exactly and specify placement, language and size.
- Do not silently turn a supplement into a fourth variant or ignore it.

### Preflight size warning

Before generating, read `size.reliability` and `size.reliability_note`:

- `ignored` — the model has been observed to ignore `--size`. Warn before generating: "这个模型可能忽略尺寸；要精确画布建议改用 gpt-image-2 或 gpt-image-2.5。仍要用它生成吗？" Do not silently proceed and explain only after the result.
- `fixed` — only if a future catalog model uses fixed mode: say the fixed canvas and omit `--size`. None of the four current models is fixed; all offer the 12-size menu.
- `observed` / `documented` — still report the actual `sizes` after generation and warn on a mismatch.
- `unknown` — the model is not in the catalog; send a prompt only and explain that size and quality are provider-controlled.

## Options are chosen, not typed

- Offer the exact `choices`/`catalog` values as a numbered choice. Never ask the user to type a value, never guess one, and never pass a value outside the list; the client rejects it and prints the allowed values.
- A model whose `size.mode` is `fixed` has no size choice. None of the four current models uses fixed mode; all four accept the 12-size menu. Keep the fixed rule for future catalog entries.
- A model missing from the catalog accepts a prompt only. `--size` or `--quality` for it fails unless `--allow-unverified` is passed, which is for one-off exploration, not for normal use.
- An omitted option sends nothing and leaves the choice to the provider default. The catalog's `default` is a suggestion to show the user, not a value the client injects.
- The 12 canvases above are the normal menu. If the user explicitly asks for the provider default instead, omit `--size`; do not invent another canvas.

## Images

Pass the final prompt with `--prompt-file` (write the file yourself) or `--prompt`. Set `--output-dir` inside the task workspace.

```text
python <skill-dir>/scripts/media.py choices
python <skill-dir>/scripts/media.py image --model gpt-image-2 --prompt-file prompt.txt --size 2048x1152 --quality high --output-dir outputs
python <skill-dir>/scripts/media.py image --model gpt-image-2.5 --prompt-file prompt.txt --size 1536x1024 --quality high --output-dir outputs
python <skill-dir>/scripts/media.py image --model gpt-image-2.5-sunburst --prompt-file edit.txt --size 1024x1024 --quality high --image reference.png --image style.png --output-dir outputs
```

Repeated `--image` selects multipart editing; `--mask` requires an input image. Preserve edit requests as edits. `--extra-json @options.json` adds documented provider-specific fields without overriding named arguments. `--dry-run` prepares a request without network access, a key or generated files.

The result carries `sizes` for each saved PNG and a `warnings` entry when the delivered canvas differs from the requested one. Report a mismatch instead of claiming the requested size.

## Videos

For reference-driven generation, read the API notes: local `--image` uses multipart `input_reference`; URLs use provider-specific reference fields. Seedance-family adapters generally need reachable URLs. Do not upload local files to third-party hosting without authorization.

```text
python <skill-dir>/scripts/media.py video --model grok-imagine-video --prompt-file video.txt --seconds 6 --wait --output-dir outputs
python <skill-dir>/scripts/media.py status <task-id> --wait --output-dir outputs
python <skill-dir>/scripts/media.py download <task-id> --output-dir outputs
```

Creation is submitted once. The script saves `job.json` before polling, with a bounded `--wait-timeout` (600 seconds by default). Continue pending jobs with `status` using the saved ID. A timeout or ambiguous submission error is not permission to create another job: check the provider's task history first. A failed job preserves its error snapshot; do not automatically generate a replacement.

## Delivery

Commands return JSON with absolute `files` paths. Inspect returned images with the available local image tool and show them with Markdown image syntax using those paths. Report `sizes` and any `warnings`. Link generated videos and report task IDs. Report pending/failed states accurately; a dry run or offline test is not a successful generation. Keep metadata local and publish outputs only when requested.
