# Prompt guide

Use this guide with the `choices` command. The image menu asks for a model, four prompt versions (the user's original wording plus three optimized directions), all resolutions, quality, and an optional supplement. The user replies with numbers or a short phrase; never ask them to paste or rewrite a prompt.

## The 3 + 1 menu

| # | Version | What to do | Use when |
| --- | --- | --- | --- |
| 0 | Original | Copy the user's wording exactly. Do not fix, translate, shorten or add style. | The user has a precise prompt or wants full control. |
| 1 | Faithful enhancement | Keep the subject, action and intent. Add only visual specifics that make the request unambiguous: composition, lighting, materials, background, lens or render. | Most requests; the safest optimization. |
| 2 | Style-led | Choose one coherent visual language that fits the subject. Name its traits rather than borrowing an artist's name. | The user wants a stronger, more distinctive look. |
| 3 | Commercial/layout | Build a clean, usable frame with negative space and text-safe areas. Keep the background uncluttered. | Posters, e-commerce, social posts, thumbnails and ads. |

The three optimized versions must differ in art direction, not merely in adjectives. If two versions would produce nearly the same image, change the composition or medium instead of adding more superlatives.

## Prompt recipe

A useful image prompt usually covers five to seven of these, not all of them:

1. **Subject and action** — who or what, doing what, with what expression or state.
2. **Setting** — place, time, weather, background, surrounding objects.
3. **Composition** — shot size, camera angle, subject placement, horizon, negative space.
4. **Light** — source, direction, softness, time of day, contrast.
5. **Color and material** — palette, textures, finishes, surface details.
6. **Camera or medium** — lens, depth of field, film stock, photographic/3D/illustration treatment.
7. **Mood** — two or three concrete adjectives, not a pile of generic ones.
8. **Constraints** — what must stay, what must not appear, exact text and its placement.

Prefer concrete nouns and observable details over abstract praise. "Soft window light from the left, matte ceramic, shallow depth of field" is more useful than "beautiful, high quality, masterpiece".

Keep each prompt roughly 60–150 English words or 80–200 Chinese characters. Long prompts are acceptable when the request has many product or layout constraints, but remove repeated adjectives first.

## Variant rules

- **Original** must be untouched. If the user asks for a translation, translate only; do not add art direction.
- **Faithful enhancement** may add camera, light and material details, but must not add a new subject, a new prop or a different setting.
- **Style-led** commits to one direction. Do not mix "photorealistic, anime, watercolor and 3D" in one prompt.
- **Commercial/layout** must reserve usable space. Say where the subject sits and where the copy area is; do not fill the whole frame.
- Do not add text, logos, signatures or watermarks unless the user asks. When text is requested, quote it exactly and specify placement, size and language.
- Avoid naming living artists or imitating a specific living person's style. Describe the visual traits instead.
- For an edit, state both sides explicitly: "keep the face, pose and product label unchanged; replace only the background with ...". Do not restyle the whole image unless asked.

## Supplement prompt

After the user chooses a version, ask for optional extra details. This is not a fourth variant; it is the user's own addition.

- Offer a free-text field and examples: add a headline, blur the background, change the outfit/prop/light, or exclude text/watermark/logo.
- If the user replies "无" or "none", use the selected prompt unchanged.
- If the user supplies details, append a short block:

```text
Additional requirements:
- Keep the subject and pose unchanged.
- Add the exact headline "..." in the upper-left, simplified Chinese, clean sans-serif.
- No watermark, no extra logo.
```

- Let the supplement override the selected variant where they conflict. If the conflict is material (for example, the variant is a tight portrait but the supplement asks for a wide poster), say so and adjust the composition instead of silently ignoring either request.
- Show the final merged prompt before generating. Do not ask the user to copy it anywhere.

## Edits

An edit prompt should read as a change request, not a fresh image description:

```text
Keep the subject's identity, facial features, pose and clothing unchanged.
Keep the product shape, label text and logo position unchanged.
Replace only the background with a warm, out-of-focus studio wall.
Match the original light direction and preserve realistic contact shadows.
```

For multiple references, name the role of each one: "image 1 supplies the person, image 2 supplies the product, image 3 supplies the color palette". Do not ask the model to merge references without saying which attributes come from which.

## Text in images

- Quote the exact text, including punctuation and line breaks.
- Say where it goes and how large it should be relative to the frame.
- Keep text short; long paragraphs are usually unreliable.
- If the user does not ask for text, add "no text, no letters, no watermark" to the prompt.
- For Chinese text, specify "simplified Chinese" or "traditional Chinese" and a clean sans-serif or serif style. Check the result and report any garbled characters instead of presenting them as correct.

## Menu copy

In the menu, show one short line per version, for example:

```text
0. 原版直出 — 用你刚才的描述，不改写
1. 优化 A｜忠实增强 — 保留原意，补足构图、光线、材质
2. 优化 B｜风格强化 — 确定一种统一的视觉语言
3. 优化 C｜商业成片 — 留出文案空间，适合海报/电商/社媒
```

The full menu also asks for the model, all resolutions, quality and the optional supplement. Do not shorten the resolution list to a few "suitable" sizes; show every option and mark a recommendation only.

After the user chooses, show the full selected prompt in a short quote block, then generate. Do not ask the user to copy it into a file or paste it back.

## Examples

### A coffee-shop poster

Original: `一张极简咖啡店海报`

Faithful enhancement:

```text
A minimalist coffee-shop poster featuring a single matte ceramic cup on a warm concrete counter.
Soft morning window light from the left, gentle shadow, muted cream and espresso-brown palette.
Centered composition with generous empty space above the cup for a headline.
Editorial product photography, 50mm lens, shallow depth of field, calm and inviting mood.
No text, no logo, no watermark.
```

Style-led:

```text
A coffee-shop poster in a 1970s Japanese print aesthetic: flat shapes, visible paper grain,
burnt orange and deep brown ink, a stylized steam curl rising from a simple cup.
Bold off-center composition, limited palette, screen-printed texture, quiet nostalgic mood.
No text, no logo, no watermark.
```

Commercial/layout:

```text
A clean coffee-shop advertising image: one ceramic cup in the lower-right third,
soft neutral background, large empty copy area in the upper-left, warm side light,
natural contact shadow, crisp product edges, restrained cream and brown palette.
Shot for a vertical social post with room for a short headline.
No text, no logo, no watermark.
```

### An edit

Original: `把背景换成海边，保留人物`

Faithful enhancement:

```text
Keep the person's identity, face, hair, pose and clothing exactly unchanged.
Replace only the background with a calm seaside at golden hour, soft waves and distant horizon.
Match the original camera angle, perspective and light direction; add realistic rim light and contact shadows.
Natural color grading, no change to skin tone or body shape.
```

Style-led:

```text
Keep the person completely unchanged. Replace the background with a cinematic coastal scene:
overcast blue-hour sky, wet sand reflections, distant lighthouse, cool teal and silver palette.
Maintain the original framing and focal length; add subtle atmospheric haze and film grain.
Moody editorial travel photography, no text or watermark.
```

Commercial/layout:

```text
Keep the person and product exactly unchanged. Replace the background with a clean, sunlit beach
with a soft gradient sky and an uncluttered copy area on the left third.
Preserve the original lighting direction and realistic shadows; keep colors bright and natural.
Leave generous negative space for a travel campaign headline. No text, no logo, no watermark.
```
