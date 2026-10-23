# API compatibility

This client implements common relay contracts. Availability, limits and billing depend on the provider and key. There is no embedded account, mandatory host or upload service.

## Endpoints

The base can include a prefix, e.g. `https://example.com/proxy/v1`. A missing `/v1` is appended once. Requests authenticate with `Authorization: Bearer <RELAY_API_KEY>`.

| Operation | Method and path | Encoding |
| --- | --- | --- |
| Account models | `GET /v1/models` | Expects `data[].id` |
| Text to image | `POST /v1/images/generations` | JSON |
| Image edit | `POST /v1/images/edits` | Multipart; one `image` or repeated `image[]`, optional `mask` |
| Video creation | `POST /v1/videos` | JSON or multipart |
| Video status | `GET /v1/videos/{id}` | JSON |
| Video content | `GET /v1/videos/{id}/content` | Binary or redirect |

Image results support `data[].b64_json` and `data[].url`. No `response_format` is sent by default because GPT Image endpoints return base64 and some providers reject that parameter; use `--extra-json` for a relay requiring it.

Streaming, chat-completions-based images, `/v1/video/generations`, Gemini-native requests and other task routes need another adapter. A different model ID does not translate an incompatible protocol.

## Models and video adapters

Model IDs are unrestricted. Account-enabled IDs can include `gpt-image-2`, `gpt-image-2.5`, `gpt-image-2.5-flare` and `gpt-image-2.5-sunburst`. Only `image2` is expanded locally. Bare `gpt-image-2.5` may be a provider alias; it is not presented as a guaranteed official endpoint model. Dimensions, quality, reference counts and formats must follow the selected relay's requirements.

Grok-style adapters usually use `seconds` and can accept multipart `input_reference`. Seedance/doubao/H3 IDs use `duration` by default; override with `--duration-field` if needed. URL fields are `reference_image_urls`, `reference_video_urls`, `reference_audio_urls`, `first_frame_image_url`, `last_frame_image_url`. Seedance-family reference inputs generally require reachable URLs; no public hosting upload occurs automatically.

Task parsing accepts a root object or nested `data`, IDs `id`/`task_id`/`taskId`, and `status` or `state`. These are compatibility fallbacks, not verified promises about every relay.

| Normalized state | Accepted values |
| --- | --- |
| `queued` | queued, pending, submitted, created |
| `in_progress` | in_progress, processing, running, generating |
| `completed` | completed, succeeded, success, finished, done |
| `failed` | failed, failure, error, cancelled, canceled, expired |

Unknown states remain visible and polling stays bounded. Download URL parsing accepts `url`, `video_url`, `download_url`, also inside `output`/`result`; otherwise it uses `/content`. Other structures require an adapter update. Do not create a duplicate job to resolve a parsing problem.

This is a relay video integration. The historical OpenAI Videos schema is a protocol reference and does not establish official service availability.

## Primary schema references

- Images generation: https://developers.openai.com/api/reference/resources/images/methods/generate
- Images editing: https://developers.openai.com/api/reference/resources/images/methods/edit
- Historical video object: https://developers.openai.com/api/reference/resources/videos/methods/retrieve

These describe HTTP shapes, not relay permissions or commercial terms.
