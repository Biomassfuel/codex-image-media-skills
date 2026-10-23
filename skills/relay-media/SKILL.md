---
name: relay-media
description: Generate or edit images and create videos through a user-configured media relay, including image2, gpt-image-2.5, flare, sunburst and compatible asynchronous video models. Use for an explicit relay, API image model, reference-image edit, or relay video request.
---

# Relay Media

Use `scripts/media.py` relative to this skill directory. It requires Python 3.10+ and the standard library only. Read [the CLI reference](references/cli.md) for arguments and [the API notes](references/api.md) when adapting a provider.

## Configuration and model choice

- Run `python <skill-dir>/scripts/media.py doctor` to inspect configuration without a request. `RELAY_BASE_URL` selects the user's relay; `RELAY_API_KEY` contains its key. An explicit `--env-file <local-file>` is supported before the subcommand. Existing environment variables take precedence.
- If configuration is missing, ask the user to configure it locally. Never ask for a key in chat, put a key in command arguments, or inspect unrelated credential files. Do not change the relay or borrow another service's key.
- `models` performs a read-only `/v1/models` lookup. Honor the exact requested model. Only `image2` expands to `gpt-image-2`; all other model IDs pass through unchanged. Image default: `RELAY_IMAGE_MODEL` or `gpt-image-2.5`. Videos require `--model` or `RELAY_VIDEO_MODEL`.
- A model catalog does not establish account permissions or parameter support. Explain a provider rejection instead of silently substituting another model.

## Images

Pass visual requirements as `--prompt`, or write a UTF-8 prompt file and use `--prompt-file`. Set `--output-dir` inside the task workspace.

```text
python <skill-dir>/scripts/media.py image --model gpt-image-2.5-flare --prompt-file prompt.txt --size 1536x1024 --output-dir outputs
python <skill-dir>/scripts/media.py image --model gpt-image-2.5-sunburst --prompt-file edit.txt --image reference.png --image style.png --output-dir outputs
```

Repeated `--image` selects multipart editing; `--mask` requires an input image. Preserve edit requests as edits. Use provider-supported quality, dimensions and formats. `--extra-json @options.json` adds documented provider-specific fields without overriding named arguments. `--dry-run` prepares a request without network access, a key or generated files.

## Videos

For reference-driven generation, read the API notes: local `--image` uses multipart `input_reference`; URLs use provider-specific reference fields. Seedance-family adapters generally need reachable URLs. Do not upload local files to third-party hosting without authorization.

```text
python <skill-dir>/scripts/media.py video --model grok-imagine-video --prompt-file video.txt --seconds 6 --wait --output-dir outputs
python <skill-dir>/scripts/media.py status <task-id> --wait --output-dir outputs
python <skill-dir>/scripts/media.py download <task-id> --output-dir outputs
```

Creation is submitted once. The script saves `job.json` before polling, with a bounded `--wait-timeout` (600 seconds by default). Continue pending jobs with `status` using the saved ID. A timeout or ambiguous submission error is not permission to create another job: check the provider's task history first. A failed job preserves its error snapshot; do not automatically generate a replacement.

## Delivery

Commands return JSON with absolute `files` paths. Inspect returned images with the available local image tool and show them with Markdown image syntax using those paths. Link generated videos and report task IDs. Report pending/failed states accurately; a dry run or offline test is not a successful generation. Keep metadata local and publish outputs only when requested.
