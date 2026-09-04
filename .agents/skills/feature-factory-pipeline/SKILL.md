---
name: feature-factory-pipeline
description: >-
  Architecture reference and production conventions for The Feature Factory product-photo to short-form video ad generator.
  Covers pipeline stages, key functions, Replicate inpainting with product masking, text-free visual prompts, script pacing budgets, Edge TTS voiceover, Ken Burns animations, and MoviePy video assembly.
---

# The Feature Factory — Video Generation Pipeline Guide

The Feature Factory is an automated AI studio converting raw e-commerce product photos and descriptions into high-converting 9:16 vertical short-form video ads (Reels / TikTok / Shorts), thumbnails, and marketing kits.

---

## 1. Pipeline Architecture & Execution Flow

```
[User Input: Photo + Product Meta]
         │
         ▼
[Stage 1: Script & Storyboard Gen] ──► Gemini 2.5 Flash (generate_product_campaign / director.py)
         │                             ├─ Strict Word Budgeting: Max words/slide = max(4, int(slide_dur * 2.3))
         │                             ├─ Text-Free Visual Prompts (All text rendered by code, not diffusion)
         │                             └─ Output: Hook, Lifestyle, CTA copy + Visual Prompts + SEO Meta
         ▼
[Stage 2: Parallel Asset Generation]
    ├── Audio Gen ────────────────────► Edge-TTS / OpenAI / ElevenLabs (tts_providers.py)
    │                                  └─ Output: audio_{i}.mp3 + audio_{i}.json (WordBoundary timestamps)
    ├── Visual Asset Inpainting ──────► rembg (Product Cutout) + Binary Mask + Replicate flux-fill-pro
    │                                  └─ Exact Foreground Alpha Compositing (100% Product Fidelity)
    └── Thumbnail Generation ─────────► generate_thumbnail() with Product Inpainting Mask + 3D Text Overlay
         │
         ▼
[Stage 3: Video Assembly & Rendering] ─► MoviePy 2.x (generator.assemble_video)
         │                              ├─ Safe-Fit Ken Burns Animation (create_ken_burns_clip)
         │                              ├─ Semantic Clause-Based Subtitles (draw_text_on_frame)
         │                              ├─ Decoupled Master Audio Timeline (Zero speech crossfade collision)
         │                              ├─ Commercial Checkout Glassmorphic Badge (Slide 3)
         │                              ├─ Background Music Looping & Audio Ducking (12% during voiceover)
         │                              └─ Top-Right Brand Watermark & Sound Effects
         ▼
[Stage 4: Packaging & Distribution] ──► ZIP Campaign Kit + YouTube Shorts API Uploader
```

---

## 2. Key Files and Functions by Stage

| Stage | Primary File | Key Functions | Description |
| :--- | :--- | :--- | :--- |
| **API & Routing** | [`main.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/main.py) | `api_generate_script`, `api_generate_assets`, `api_render_video`, `download_campaign_bundle` | FastAPI endpoints orchestrating the 3-step generation workflow and ZIP asset export. |
| **Data Contracts** | [`schemas.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/schemas.py) | `ScriptGenRequest`, `CampaignMetadata`, `DirectorScore`, `ProductLock` | Pydantic data models enforcing strict types, word limits, and execution logging. |
| **Scripting** | [`generator.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py) | `generate_product_campaign()`, `generate_script()`, `brainstorm_trending_topics()` | Calls Gemini 2.5 Flash with structured JSON output, strict word budgeting, and text-free visual prompts. |
| **Director Score** | [`director.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/director.py) | `generate_director_score()` | Structured JSON director storyboard generator planning camera movements and scene transitions. |
| **Voiceover & TTS** | [`tts_providers.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/tts_providers.py), [`generator.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py) | `generate_voiceover()`, `generate_voiceover_multi()` | Synthesizes voice tracks via Edge-TTS (with WordBoundary timing extraction), OpenAI TTS, or ElevenLabs. |
| **Image Inpainting & Compositing** | [`generator.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py) | `generate_product_image_replicate()`, `derive_product_lock()`, `enrich_cinematic_prompt()` | Strips background with `rembg`, generates binary mask, runs Replicate `flux-fill-pro`, and alpha-composites original product pixels. |
| **Thumbnail Generator** | [`generator.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py) | `generate_thumbnail()` | Generates high-converting thumbnails using masked inpainting for real product fidelity + angled 3D Impact typography. |
| **Stock Assets** | [`stock_footage.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/stock_footage.py) | `search_pexels_videos()`, `search_pixabay_images()` | Fetches royalty-free stock clips and images for hybrid visual pipelines. |
| **Model Registry** | [`ai_models.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/ai_models.py) | `IMAGE_MODELS`, `VIDEO_MODELS`, `TTS_PROVIDERS`, `estimate_cost()` | Model definitions, pricing per asset, and speed/quality presets. |
| **Video Assembly** | [`generator.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py) | `assemble_video()`, `create_ken_burns_clip()`, `draw_text_on_frame()` | MoviePy engine with decoupled audio timeline, Ken Burns framing, wrapped subtitles, and dynamic ducking. |

---

## 3. Critical Production Rules & Conventions

### Rule 1: 100% Product Fidelity (Zero Diffusion Hallucination)
- **Product Isolation**: `rembg` isolates the raw product foreground into a pristine RGBA cut-out (`transparent_img`).
- **Binary Inpainting Mask**: An explicit binary mask ($0 = \text{black/preserve product}$, $255 = \text{white/inpaint background}$) is passed to Replicate `black-forest-labs/flux-fill-pro`.
- **Exact Foreground Alpha-Compositing**: The original sharp product cut-out is alpha-composited on top of the infilled canvas (`filled_rgba.paste(transparent_img, (0, 0), transparent_img)`). This guarantees 100% authentic gemstones, enamel, metals, logos, and engravings without AI deformation.
- **Applied Universally**: This masking + compositing pipeline is used for **all video slides** and the **thumbnail generator**.

### Rule 2: Zero Text in Visual Prompts (All Text Coded)
- Diffusion models generate broken, illegible gibberish when asked to render text or buttons.
- Gemini system prompts strictly forbid text, words, brand names, discount percentages, prices, purity marks (e.g. `92.7`), or CTA banners in `visual_prompt`.
- `sanitize_visual_prompt()` scrubs any stray numeric purity ratings or CTA phrases.
- `enrich_cinematic_prompt()` appends `"clean blank background surfaces, absolutely no text, no numbers, no words, no signs, no logos, no typography, no watermarks"`.
- All on-screen elements (watermark, karaoke subtitles, checkout card badges, thumbnail CTA) are rendered programmatically via Pillow.

### Rule 3: Script Pacing & Word Budgeting Formula
- `duration` in `metadata.json` represents the **TOTAL video ad duration** across all slides.
- Natural speech rate for commercial voiceovers is $\approx 2.3\text{ words/second}$.
- Enforce the following mathematical constraints in all LLM prompts:
  $$\text{slide\_dur} = \frac{\text{duration\_seconds}}{\text{num\_slides}}$$
  $$\text{max\_words\_per\_slide} = \max\left(4, \text{int}(\text{slide\_dur} \times 2.3)\right)$$
  $$\text{total\_word\_budget} = \max\left(12, \text{int}(\text{duration\_seconds} \times 2.3)\right)$$
- Example: A 15-second ad across 3 slides allocates $\approx 10\text{--}11\text{ words per slide}$ ($31\text{ words total}$), yielding a tight, high-energy 21-second ad with speech and crossfades.

### Rule 4: Semantic Clause-Based Subtitle Chunking
- Subtitles must **never use unconstrained sliding windows** across sentence boundaries (e.g., merging the end of one sentence with the beginning of another).
- Words are grouped into coherent phrases bounded by punctuation (`.`, `!`, `?`, `,`, `;`) and audio pauses ($> 0.35\text{s}$).
- The active phrase is rendered centered in the lower 70% safe zone with the currently spoken word highlighted in bright Yellow/Neon Green, providing standard TikTok/Instagram dynamic captions.

### Rule 5: Decoupled Master Audio Timeline
- Never attach audio clips directly to video segments when applying crossfade padding (e.g., `padding=-0.5`), as this causes narration from adjacent slides to overlap and collide.
- Master narration audio is concatenated sequentially with zero overlap (`concatenate_audioclips`).
- Video clips are visually padded by $0.5\text{s}$ with `CrossFadeIn(0.5)` for smooth visual dissolves.
