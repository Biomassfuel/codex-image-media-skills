# CLI reference

Run `python <skill-dir>/scripts/media.py --help` or add `--help` after a subcommand. In a checkout, `<skill-dir>` is `skills/relay-media`.

## Configuration

Global options go **before** the subcommand:

```text
python <skill-dir>/scripts/media.py --env-file /absolute/path/media.env --timeout 300 image --prompt "A ceramic cup"
python <skill-dir>/scripts/media.py --base-url https://your-relay.example/v1 models --contains image
```

| Variable | Meaning |
| --- | --- |
| `RELAY_BASE_URL` | Explicit relay origin or base ending in `/v1` |
| `RELAY_API_KEY` | Key read from the environment or an explicit env file |
| `RELAY_IMAGE_MODEL` | Default image model; otherwise `gpt-image-2.5` |
| `RELAY_VIDEO_MODEL` | Optional video default; no video model is guessed |

Env files accept only these assignments, optionally quoted, blank lines and `#` comments. They do not execute code, expand variables, load automatically or override existing variables. HTTPS is required except for localhost development. `doctor` checks configuration without network access; `models [--contains text]` lists account-visible IDs; `catalog` prints the local model catalog, also offline; `choices` prints the interactive menu for one model, also offline.

Global `--no-proxy` ignores system and environment proxies for this invocation, including media downloads. Omit it to retain the normal system route. A longer `--timeout` cannot prevent a proxy or server from closing the connection earlier. For diagnostics, `doctor` reports the selected route without exposing proxy credentials.

## Model catalog

`catalog` reads `references/model-catalog.json` and prints every cataloged image model with the options it accepts. It needs no key and no network, so it is safe to run before asking the user anything.

- `size.mode: enum` — the value must be one of `size.values`; anything else exits 1 with the allowed list.
- `size.mode: fixed` — the model always returns `value`, so `--size` is rejected rather than silently ignored. None of the four current models uses fixed mode; all four expose the 12-size menu.
- A model absent from the catalog rejects any of the option flags unless `--allow-unverified` is passed.
- Omitting an option sends no field and leaves the choice to the provider. A `default` in the catalog is guidance for the chooser, not a value the client injects.

Edit the JSON to add a model or correct a limit; no code change is needed. `source` records whether a profile was observed in a real response or follows the documented contract. `size_reliability` records whether the canvas is `observed`, `documented`, `ignored` or `fixed`; `size_note` explains the evidence. For example, `gpt-image-2.5-flare` is marked `ignored` after a request for `1536x1024` delivered `1024x1536`.

The default GPT Image menu is exactly 12 canvases, in this order:

```text
1024x1024   1536x1024   1024x1536   1792x1024   1024x1792
2048x2048   2048x1152   1152x2048   2560x1440   1440x2560
3840x2160   2160x3840
```

`auto` is not a size in this menu. Quality remains `auto`, `low`, `medium` or `high` when the catalog lists it.

## Interactive choices

`choices [--model ID] [--lang zh|en]` reads the catalog offline and prints the menu the assistant should show before the first image request. It needs no key and no network.

Run it in two stages:

1. `choices` without `--model` returns `menu_version`, `model_required: true`, `model_options`, prompt modes and supplement, but `size.mode: pending` and `quality.mode: pending`. It does not pick a default model.
2. `choices --model <id>` returns the full menu for that model.

Fields:

- `model_options` — every catalog model with `id`, `label`, role, edit support, size mode/count, default size, quality values, `size_reliability`, `size_note`, `selected` and `recommended`.
- `prompt.options` — the original wording plus three optimized directions, with stable ids and descriptions.
- `supplement` — the optional free-text prompt details question, hint and examples.
- `size.options` — every value the model accepts, each with `index`, `value`, `label`, `width`, `height`, `aspect`, `orientation`, `tier` and `recommended`. Enum models set `do_not_filter: true`; show all values.
- `size.pages` — groups of four 1-based indices for paginated question cards (for 12 sizes: `[[1,2,3,4],[5,6,7,8],[9,10,11,12]]`).
- `quality.options` — the model's exact values with labels and a recommended default.
- `reply_hint` — the order in which the user can reply with numbers.

`--model` resolves `image2` to `gpt-image-2`. All four current models return `size.mode: enum` with 12 options; a future fixed-size model would return `size.mode: fixed` with no options. A model absent from the catalog returns `size.mode: unknown`; only a prompt can be sent to it. `menu_version` lets a caller detect a stale cached skill.

## Images

`image` requires exactly one of `--prompt` and `--prompt-file`.

| Option | Meaning |
| --- | --- |
| `--model ID` | Exact ID; `image2` expands to `gpt-image-2`. Pick one from `catalog` |
| `--prompt TEXT` | Inline prompt; prefer `--prompt-file` for long text |
| `--prompt-file FILE` | UTF-8 prompt file; exactly one prompt option is required |
| `--image FILE` | Local reference; repeat for multiple images |
| `--mask FILE` | Edit mask; requires an input image |
| `--n N` | Positive image count; default 1 |
| `--size SIZE` | One of the model's `size.values`; rejected for a `fixed` model |
| `--quality VALUE` | One of the model's `quality.values` |
| `--background VALUE` | One of the model's `background.values` |
| `--output-format png\|jpeg\|webp` | Requested format; saved extension follows actual bytes |
| `--allow-unverified` | Send options for a model absent from the catalog |
| `--unattended` | Automation/tests only: allow omitted model/size/quality and provider defaults. Never use for an interactive request |
| `--extra-json JSON` | Additional fields; prefix a JSON filename with `@` |
| `--dry-run` | Preview without a key, network or output directory |

Without `--unattended`, `image` requires an explicit `--model`; for a catalog model with enum size it also requires `--size`, and for enum quality it requires `--quality`. A missing value exits 1 with `missing_selection`, so a caller cannot silently fall back to `RELAY_IMAGE_MODEL` or provider defaults. Fixed-size models omit `--size` but still require `--quality`.

Without reference files, requests use JSON generation. With references, requests use multipart editing. Base64 and URL results are saved with PNG, JPEG, WebP, GIF or AVIF signatures checked. Supported model output formats vary.

The result reports `sizes` for saved PNGs and adds `warnings` when the delivered canvas differs from the requested `--size`, so a model that ignores the parameter is visible instead of silent.

## Videos

`video` requires a prompt and an explicit/default model. It submits once; it returns pending metadata unless `--wait` is set or the relay returns a terminal state immediately.

| Option | Meaning |
| --- | --- |
| `--seconds N` | Positive duration sent under the selected field |
| `--duration-field auto\|seconds\|duration` | Auto uses `duration` for IDs containing seedance/doubao/h3, otherwise `seconds` |
| `--size SIZE`, `--resolution VALUE`, `--aspect-ratio VALUE` | Provider-specific parameters |
| `--image FILE` | Local multipart `input_reference`; verify model support |
| `--reference-image-url URL` | Repeatable `reference_image_urls` |
| `--reference-video-url URL` | Repeatable `reference_video_urls` |
| `--reference-audio-url URL` | Repeatable `reference_audio_urls` |
| `--first-frame-url URL`, `--last-frame-url URL` | First/last frame image URLs |
| `--encoding auto\|json\|multipart` | Auto selects multipart with a local input, JSON otherwise |
| `--extra-json JSON`, `--dry-run` | Same semantics as images |
| `--wait`, `--wait-timeout SECONDS` | Bounded polling; default deadline 600 seconds |
| `--poll-interval SECONDS` | Delay between queries; default 10 |
| `--no-download` | Keep completed metadata without downloading |

`status TASK_ID` queries an existing job and accepts wait/no-download options. `download TASK_ID` retries only the content download. Neither command submits another job. Downloads recognize MP4/MOV and WebM.

## Files and errors

Image/video/status/download commands accept `--output-dir` (default `outputs`), `--download-timeout` (default 300 seconds per connection) and `--max-download-mb` (default 1024). Each invocation creates a unique child directory without overwriting prior files.

- Images: generated files, sanitized `response.json`, and `result.json`. Base64 is omitted from snapshots. A failed HTTP request saves sanitized `failure.json` with the model, endpoint, route, timeout and error; transport errors include the exception type, response phase and elapsed time.
- Videos: sanitized `job.json` before polling/downloading; `result.json` on normal return; downloaded content when complete. Terminal failures retain the error snapshot. Another query can create another directory for the same job.
- Prompts and signed URLs may appear in metadata. Keep them local; the repository ignores generated outputs.

Success and pending jobs exit 0; pending results include `pending: true` and a task ID. Errors emit JSON on stderr and exit 1; invalid arguments exit 2; interrupts exit 130. The poll deadline is separate from each request's `--timeout`. No HTTP request is automatically retried. A creation timeout can be ambiguous; inspect task history before resubmitting. Downloads recalculate authorization on each redirect so external media hosts do not receive the relay key.
