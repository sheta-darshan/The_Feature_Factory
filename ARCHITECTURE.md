# 🏗️ Architecture & Pipeline Guide — The Feature Factory

This document details the end-to-end architecture, data flow, component responsibilities, and external service integration points for **The Feature Factory**.

---

## 1. System Overview & End-to-End Pipeline Flow

The Feature Factory is a 3-stage generation pipeline that transforms e-commerce product photos and metadata into rendered short-form video ads (9:16 vertical MP4 reels), YouTube thumbnails, and social marketing packages.

```
                    ┌───────────────────────────────┐
                    │      Client / Web UI          │
                    │   (templates/index.html)      │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Stage 1: Upload & Script Generation                                               │
│                                                                                   │
│ 1. POST /api/upload-product-images                                                │
│    └─ Compresses images to max 1536px and stores in uploads/<timestamp>_name.jpg  │
│                                                                                   │
│ 2. POST /api/generate-script (schemas.ScriptRequest)                              │
│    ├─ main.py calls generator.generate_product_campaign()                         │
│    ├─ External Call: Google Gemini 2.5 Flash (google-genai)                       │
│    │  ├─ Generates storyboard slides (Hook, Lifestyle, CTA)                       │
│    │  ├─ Enforces pacing word budget: max_words/slide = max(4, int(dur/3 * 2.3))  │
│    │  ├─ Enforces zero-text / zero-plaque visual prompt policy                    │
│    │  └─ Generates multi-platform social copy (IG, Shorts, WhatsApp)              │
│    ├─ Director Scoring: director.generate_director_score() (Gemini 2.5 Flash)     │
│    │  ├─ Generates camera motion, transitions, scene types, and color palettes    │
│    │  ├─ Reconciles scene count 1:1 with campaign segments (safe fallback if mismatch)│
│    │  └─ Graceful Try/Except Fallback: keeps default motion if director times out │
│    └─ Outputs: outputs/project_<id>/metadata.json                                 │
└───────────────────────────────────┬───────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Stage 2: Parallel Asset Generation                                                │
│                                                                                   │
│ POST /api/generate-assets (schemas.AssetRequest)                                  │
│ ├─ Voiceover Synthesis (Parallel per segment):                                    │
│ │  ├─ generator.generate_voiceover() -> edge_tts.Communicate                      │
│ │  ├─ External Call: Microsoft Edge TTS (or tts_providers.py for OpenAI/11Labs)   │
│ │  └─ Outputs: outputs/project_<id>/audio_{i}.mp3 + audio_{i}.json (word timings) │
│ │                                                                                 │
│ └─ Visual Generation (Hybrid Waterfall per segment):                              │
│    ├─ Priority 1 (Product Photo Present): Local rembg mask + Replicate            │
│    │  flux-fill-pro inpainting + PIL alpha compositing (100% product fidelity)   │
│    ├─ Priority 2 (No Photo & Stock API Key): stock_footage.py (Pexels / Pixabay)  │
│    │  downloads stock video clip (.mp4) or photo (.jpg)                           │
│    ├─ Priority 3 (No Photo & No Stock Key / 0 results): Replicate flux-schnell    │
│    │  text-to-image fallback                                                      │
│    └─ Outputs: outputs/project_<id>/image_{i}.jpg (or .mp4)                       │
└───────────────────────────────────┬───────────────────────────────────────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Stage 3: Video Assembly & Distribution                                            │
│                                                                                   │
│ 1. POST /api/render-video (schemas.RenderRequest)                                 │
│    ├─ generator.assemble_video() -> MoviePy 2.x engine                            │
│    │  ├─ Decoupled speech timeline: Audio clips concatenated sequentially         │
│    │  ├─ Visual transitions: director-specified CrossDissolve / FadeBlack (0.5s) │
│    │  ├─ Ken Burns camera motions: slow_zoom_in, dolly_forward, pan_left/right,   │
│    │  │  tilt_up, orbit_left, static_hero via create_ken_burns_clip()             │
│    │  ├─ Stock Video Clips: Native VideoFileClip looped/trimmed to speech duration,│
│    │  │  center-cropped to 9:16 vertical, muted source audio                      │
│    │  ├─ PIL Subtitle Engine: draw_text_on_frame() with semantic clause chunking  │
│    │  ├─ Commercial Checkout Card: Glassmorphic badge on Slide 3                  │
│    │  └─ Audio Ducking: Background music scaled to 12% during voice narration     │
│    ├─ generator.generate_thumbnail()                                              │
│    │  ├─ Masked inpainting with flux-fill-pro + product composite                 │
│    │  └─ 3D Impact rotated typography in safe lower-third                         │
│    └─ Outputs: outputs/project_<id>/final_video.mp4 & thumbnail.jpg               │
│                                                                                   │
│ 2. Export & Publishing Endpoints:                                                 │
│    ├─ GET /api/download-campaign-bundle/{id} -> Creates client ZIP archive        │
│    └─ POST /api/youtube-upload -> Uploads to YouTube via youtube_uploader.py     │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Ownership & Directory Responsibilities

| File / Folder | Layer | Primary Responsibility | Key Functions / Classes |
| :--- | :--- | :--- | :--- |
| [`main.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/main.py) | API Gateway | FastAPI application, route handlers, project metadata persistence, static mounting, background tasks. | `api_generate_script`, `api_generate_assets`, `api_render_video`, `download_campaign_bundle` |
| [`generator.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py) | Core Engine | Gemini copywriting, prompt sanitization, Replicate inpainting, Edge-TTS audio, PIL text rendering, MoviePy assembly. | `generate_product_campaign`, `generate_product_image_replicate`, `generate_voiceover`, `assemble_video`, `generate_thumbnail` |
| [`schemas.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/schemas.py) | Data Contracts | Pydantic data models for API requests, project metadata, product lock descriptors, and execution logs. | `ScriptRequest`, `AssetRequest`, `RenderRequest`, `ProjectMetadata`, `ProductLock`, `GenerationStepLog` |
| [`job_manager.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/job_manager.py) | Job Orchestration | Unified execution engine and background queue for assets, render, and full-pipeline jobs with polling status. | `execute_asset_generation`, `execute_video_render`, `submit_assets_job`, `submit_render_job`, `submit_full_pipeline_job` |
| [`metadata_manager.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/metadata_manager.py) | Concurrency | Thread-safe and process-safe FileLock protection around outputs/<project_id>/metadata.json reads and writes. | `read_metadata`, `write_metadata`, `update_metadata`, `mutate_metadata`, `get_metadata_lock` |
| [`director.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/director.py) | Scene Planning | Structured JSON director storyboard generator planning camera angles, timing, transitions, and palettes. | `generate_director_score` |
| [`ai_models.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/ai_models.py) | Model Registry | Multi-model catalog definitions, cost estimation algorithms, and frontend model metadata. | `IMAGE_MODELS`, `VIDEO_MODELS`, `TTS_PROVIDERS`, `estimate_cost`, `get_available_models_for_frontend` |
| [`tts_providers.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/tts_providers.py) | Audio Routing | Unified multi-provider voiceover generator routing to Edge-TTS, OpenAI TTS, or ElevenLabs. | `generate_voiceover_multi`, `_generate_edge_tts`, `_generate_openai_tts`, `_generate_elevenlabs_tts` |
| [`stock_footage.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/stock_footage.py) | Stock Visuals | Async stock video and photo search using Pexels and Pixabay APIs. | `search_pexels_videos`, `search_pixabay_images`, `download_stock_asset` |
| [`youtube_uploader.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/youtube_uploader.py) | Distribution | Google OAuth2 authentication and chunked resumable video upload to YouTube channel. | `get_youtube_client`, `upload_video_to_youtube` |
| [`templates/index.html`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/templates/index.html) | Frontend | Single-page dark-mode studio UI with step-by-step wizard, interactive storyboard editor, and live preview. | HTML5 + Vanilla JS UI |
| [`static/`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/static) | Static Assets | Bundled fonts (`Outfit-Bold.ttf`), background music (`ambient_dream.mp3`, `synthwave_beat.mp3`), and audio SFX. | Media files |
| [`.agents/skills/`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/.agents/skills/feature-factory-pipeline/SKILL.md) | Agent Skill | Antigravity AI assistant skill defining codebase conventions, formulas, and working baselines. | Markdown knowledge base |

---

## 3. External Service Call Sites & Authentication

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ External Service Integrations                                                          │
├───────────────────────┬──────────────────────────────┬─────────────────────────────────┤
│ Provider              │ Files Calling Provider       │ Authentication / Keys           │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ Google Gemini         │ generator.py, director.py    │ GEMINI_API_KEY                  │
│ (gemini-2.5-flash)    │                              │                                 │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ Replicate             │ generator.py                 │ REPLICATE_API_TOKEN             │
│ (flux-fill-pro, dev)  │                              │                                 │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ Microsoft Edge TTS    │ generator.py,                │ Free / Built-in (No key needed) │
│ (edge-tts)            │ tts_providers.py             │                                 │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ OpenAI TTS (Optional) │ tts_providers.py             │ OPENAI_API_KEY                  │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ ElevenLabs (Optional) │ tts_providers.py             │ ELEVENLABS_API_KEY              │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ Pexels API (Optional) │ stock_footage.py             │ PEXELS_API_KEY                  │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ Pixabay (Optional)    │ stock_footage.py             │ PIXABAY_API_KEY                 │
├───────────────────────┼──────────────────────────────┼─────────────────────────────────┤
│ YouTube Data API v3   │ youtube_uploader.py          │ client_secrets.json (OAuth 2.0) │
└───────────────────────┴──────────────────────────────┴─────────────────────────────────┘
```

---

## 4. Key Data Flow & Transformation Invariants

1. **Product Fidelity Invariant**:
   - `rembg.remove()` extracts the product foreground into an RGBA cutout.
   - An inverted alpha channel ($0=\text{protect}$, $255=\text{inpaint}$) is passed to `black-forest-labs/flux-fill-pro`.
   - The original unmodified cutout is alpha-composited on top of the infilled background (`filled_rgba.paste(transparent_img, (0, 0), transparent_img)`). This ensures 100% true product geometry, logos, and materials.

2. **Zero-Text Diffusion Invariant**:
   - All visual prompts pass through `sanitize_visual_prompt()` (strips quotes, numbers, purity marks, and CTA words) and `enrich_cinematic_prompt()` (appends explicit negative text/engraving/plaque exclusion directives).
   - All on-screen typography is rendered strictly via PIL in `draw_text_on_frame()`.

3. **Script Pacing Budget Invariant**:
   - Natural speech cadence is modeled as $\approx 2.3\text{ words/second}$.
   - Max words per slide is dynamically calculated: $\text{max\_words} = \max(4, \text{int}(\text{slide\_duration} \times 2.3))$.

4. **Subtitle Semantic Chunking Invariant**:
   - Words are grouped into clauses based on punctuation (`.`, `!`, `?`, `,`, `;`) and pauses ($> 0.35\text{s}$). Subtitles never bridge across sentence boundaries onto the same line.
