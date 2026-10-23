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

Env files accept only these assignments, optionally quoted, blank lines and `#` comments. They do not execute code, expand variables, load automatically or override existing variables. HTTPS is required except for localhost development. `doctor` checks configuration without network access; `models [--contains text]` lists account-visible IDs.

## Images

`image` requires exactly one of `--prompt` and `--prompt-file`.

| Option | Meaning |
| --- | --- |
| `--model ID` | Exact ID; `image2` expands to `gpt-image-2` |
| `--image FILE` | Local reference; repeat for multiple images |
| `--mask FILE` | Edit mask; requires an input image |
| `--n N` | Positive image count; default 1 |
| `--size SIZE`, `--quality VALUE`, `--background VALUE` | Provider-supported parameters |
| `--output-format png\|jpeg\|webp` | Requested format; saved extension follows actual bytes |
| `--extra-json JSON` | Additional fields; prefix a JSON filename with `@` |
| `--dry-run` | Preview without a key, network or output directory |

Without reference files, requests use JSON generation. With references, requests use multipart editing. Base64 and URL results are saved with PNG, JPEG, WebP, GIF or AVIF signatures checked. Supported model output formats vary.

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

- Images: generated files, sanitized `response.json`, and `result.json`. Base64 is omitted from snapshots.
- Videos: sanitized `job.json` before polling/downloading; `result.json` on normal return; downloaded content when complete. Terminal failures retain the error snapshot. Another query can create another directory for the same job.
- Prompts and signed URLs may appear in metadata. Keep them local; the repository ignores generated outputs.

Success and pending jobs exit 0; pending results include `pending: true` and a task ID. Errors emit JSON on stderr and exit 1; invalid arguments exit 2; interrupts exit 130. The poll deadline is separate from each request's `--timeout`. No HTTP request is automatically retried. A creation timeout can be ambiguous; inspect task history before resubmitting. Downloads recalculate authorization on each redirect so external media hosts do not receive the relay key.
