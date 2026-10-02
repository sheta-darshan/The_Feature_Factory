# 🏭 The Feature Factory — AI Product Content Studio

**The Feature Factory** is an end-to-end automated AI studio that transforms raw e-commerce product photos and descriptions into high-converting, professional short-form video ads (9:16 Instagram Reels, YouTube Shorts, and WhatsApp Statuses), click-worthy thumbnails, and full social marketing campaign kits.

---

## 🌟 Implemented Features

### 1. 100% Product Fidelity Inpainting
- **Binary Alpha Masking & Compositing**: Isolates product foreground using local `rembg` background subtraction, passes an inverted binary mask ($0=\text{product retain}$, $255=\text{background inpaint}$) to Replicate's `black-forest-labs/flux-fill-pro`, and alpha-composites the original unmodified cutout on top of the infilled canvas (`generator.py`).
- **Product Lock Metadata**: Automatically analyzes isolated product images to extract bounding boxes, aspect ratios, and dominant hex color palettes (`derive_product_lock`).
- **Multi-Angle Support**: Supports uploading multiple product photos (hero reveal, lifestyle angle, detail close-up) that stitch sequentially across storyboard scenes.

### 2. Pacing-Constrained Scripting & Multi-Platform Copywriting
- **Gemini 2.5 Flash Script Engine**: Generates 3-slide commercial scripts (Hook ➔ Lifestyle Benefit ➔ Closing Brand Offer & CTA) using Google Gemini (`generator.generate_product_campaign`).
- **Pacing Word-Budget Formula**: Constrains voiceover script length to $\text{max words} = \max(4, \text{int}(\text{slide\_duration} \times 2.3))$ based on total requested ad duration, preventing narration overrun.
- **Zero-Text Visual Prompt Policy**: Runs visual prompts through `sanitize_visual_prompt()` and appends negative exclusion clauses (`enrich_cinematic_prompt`) to prevent diffusion models from rendering illegible background text, numbers, or engraved plaques.
- **Multi-Platform Social Copy**: Generates fold-protected Instagram Reel captions (with hashtag packs), YouTube Shorts SEO titles & descriptions (`#shorts`), and conversational WhatsApp status text.

### 3. Multi-Provider Voiceovers (TTS)
- **Microsoft Edge TTS (Default / Free)**: High-quality neural voiceover synthesis with speed and pitch modulation (`tts_providers.py` / `generator.py`). Extracts real-time `WordBoundary` timestamps for synchronized karaoke subtitles.
- **OpenAI TTS-1-HD (Optional)**: Premium speech synthesis with voices like `alloy`, `echo`, `fable`, `onyx`, `nova`, and `shimmer` (requires `OPENAI_API_KEY`).
- **ElevenLabs (Optional)**: Ultra-premium voice cloning and lifelike narration with voices like `Rachel`, `Adam`, `Bella`, `Antoni`, `Domi`, and `Elli` (requires `ELEVENLABS_API_KEY`).

### 4. Dynamic Video Assembly (MoviePy 2.x)
- **Decoupled Master Audio Timeline**: Speech audio tracks are concatenated sequentially without crossfade collisions, while visual video clips have a $0.5\text{s}$ visual overlap for true cross-dissolve transitions.
- **Ken Burns Motion Engine**: Smooth panning, slow zooms, and tilting animations (`create_ken_burns_clip`).
- **Semantic Clause-Based Subtitles**: Groups spoken words into readable clauses bounded by punctuation and audio pauses ($> 0.35\text{s}$), with dynamic Yellow/Neon Green karaoke word highlighting.
- **Commercial Checkout Card**: Renders a glassmorphic badge on the closing slide displaying `[Brand] • [Price] • [CTA]`.
- **Audio Ducking**: Automatically scales background music volume down to 12% during active voiceover narration.
- **Watermark & SFX**: Overlays custom brand watermarks (`@BrandName`) and supports background audio tracks.

### 5. Product-Aware Thumbnail Generator
- Inpaints background environments using masked `flux-fill-pro` while preserving exact product pixels, then renders high-contrast 3D rotated Impact typography in the safe lower-third (`generator.generate_thumbnail`).

### 6. Multi-Language Translation
- Translates existing project scripts and voiceover tracks into **German, French, Spanish, Japanese, Portuguese, or Hindi** using Gemini, automatically switching to native Edge TTS neural voices (`/api/translate-project`).

### 7. YouTube Shorts Direct Publishing
- Authenticates with Google OAuth 2.0 (`youtube_uploader.py`) to perform chunked resumable video uploads directly to a YouTube channel with custom titles, descriptions, and tags.

### 8. Downloadable Campaign Bundle (ZIP)
- Packages the final 9:16 MP4 video, cover thumbnail (`thumbnail.jpg`), HD slide stills, and a formatted `04_Social_Media_Captions.txt` into a single downloadable client archive (`/api/download-campaign-bundle/{project_id}`).

---

## 📂 Repository File Tree & Component Directory

```text
The_Feature_Factory/
├── main.py                    # FastAPI web server, API route handlers & orchestration
├── generator.py               # Gemini copywriting, inpainting, Edge-TTS & MoviePy assembler
├── schemas.py                 # Pydantic data contracts (ScriptRequest, RenderRequest, ProductLock)
├── job_manager.py             # Shared execution engine & async job queue (assets, render, full pipeline)
├── metadata_manager.py        # FileLock protection for thread/process-safe outputs/<id>/metadata.json
├── jobs/                      # Disk-backed JSON persistence for async jobs and polling state
├── director.py                # Structured scene planner with camera movements & transitions (Gemini)
├── ai_models.py               # AI model catalog, pricing metadata & cost estimation engine
├── tts_providers.py           # Multi-provider voiceover router (Edge-TTS, OpenAI TTS, ElevenLabs)
├── stock_footage.py           # Stock video & photo search engine (Pexels & Pixabay APIs)
├── youtube_uploader.py        # YouTube Data API v3 OAuth2 uploader for publishing Shorts
├── merge_pitch_video.py       # Standalone script for mixing voiceover, BGM, and pitch demo video
├── content_calendar_365.md    # 365-day retail marketing reel idea catalog across 6 industries
├── requirements.txt           # Python package dependencies
├── .env.template              # Environment variable configuration template
├── .gitignore                 # Git ignore rules for artifacts, virtualenvs, and credentials
├── ARCHITECTURE.md            # Comprehensive end-to-end pipeline and data flow documentation
├── KNOWN_ISSUES.md            # Audit of technical debt, unwired modules, and code limitations
├── templates/
│   └── index.html             # Single-page studio dashboard with 3-step wizard and preview player
├── static/
│   ├── fonts/                 # Bundled typography (Outfit-Bold.ttf)
│   ├── music/                 # Background audio tracks (ambient_dream.mp3, synthwave_beat.mp3, etc.)
│   ├── sfx/                   # Sound effects (clock_tick.wav, coin_clink.wav, whoosh_transition.wav)
│   ├── css/                   # Static stylesheet directory (inline styles currently in index.html)
│   └── js/                    # Static JavaScript directory
├── uploads/                   # Upload storage for raw product photos (compressed to max 1536px)
├── outputs/                   # Project workspace storage (metadata.json, audio, images, final MP4)
└── .agents/
    └── skills/
        └── feature-factory-pipeline/
            └── SKILL.md       # Antigravity agent skill documenting production conventions
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python**: 3.10 or higher
- **FFmpeg**: Must be installed and accessible on your system `PATH` (used by MoviePy for video encoding).
  - *Windows*: `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/)
  - *macOS*: `brew install ffmpeg`
  - *Linux*: `sudo apt install ffmpeg`

### 2. Installation
```bash
# Clone repository
git clone https://github.com/sheta-darshan/The_Feature_Factory.git
cd The_Feature_Factory

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.template` to `.env` and fill in your API tokens:
```bash
cp .env.template .env
```

Edit `.env` with your credentials:
```ini
# Required: Google Gemini API Key (for script generation & copywriting)
GEMINI_API_KEY=your_gemini_api_key_here

# Required: Replicate API Token (for FLUX Fill Pro inpainting & image models)
REPLICATE_API_TOKEN=your_replicate_api_token_here

# Optional: Premium TTS Providers (used if selecting non-Edge TTS providers)
OPENAI_API_KEY=your_openai_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Optional: Stock Footage APIs
PEXELS_API_KEY=your_pexels_api_key_here
PIXABAY_API_KEY=your_pixabay_api_key_here
```

#### YouTube Upload Setup (Optional)
If you wish to use the direct YouTube Shorts uploader:
1. Go to [Google Cloud Console](https://console.cloud.google.com/) and enable the **YouTube Data API v3**.
2. Create an **OAuth 2.0 Client ID** (Application type: *Desktop App*).
3. Download the credentials JSON and save it in the root folder as `client_secrets.json`.
4. The first upload will prompt an interactive browser login to generate `client_token.json`.

### 4. Running the Studio
```bash
python main.py
```
Open your browser at `http://127.0.0.1:8001`.

---

## 📡 API Endpoint Reference (`main.py`)

All API routes in the FastAPI backend:

| Method | Endpoint | Request Body / Parameters | Response | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | None | HTML | Serves the main web dashboard (`templates/index.html`). |
| `GET` | `/api/list-music` | None | `list[str]` | Lists available BGM audio files in `static/music/`. |
| `GET` | `/api/list-projects` | None | `list[ProjectMetadata]` | Scans `outputs/` and returns metadata for all past projects sorted by timestamp. |
| `GET` | `/api/daily-topic` | None | `{"topic": str}` | Picks a random unused product marketing prompt from `content_calendar_365.md`. |
| `GET` | `/api/trending-topics` | None | `{"status": "success", "topics": list}` | Brainstorms trending e-commerce niches using live Google Search grounding. |
| `GET` | `/api/models` | None | `{"image_models": dict, "video_models": dict, "tts_providers": dict}` | Returns available AI model catalog for UI selectors. |
| `POST` | `/api/estimate-cost` | `{"imageModel": str, "videoModel": str, "ttsProvider": str, "numSlides": int, "charCount": int}` | Cost breakdown dict | Returns estimated generation cost across images, video, and TTS. |
| `POST` | `/api/upload-product-image` | Form-data: `file: UploadFile` | `{"filePath": str}` | Uploads a single raw product photo to `uploads/`. |
| `POST` | `/api/upload-product-images` | Form-data: `files: list[UploadFile]` | `{"filePaths": list[str]}` | Uploads and compresses multiple photos (max 1536px JPEG) to `uploads/`. |
| `POST` | `/api/generate-script` | JSON: `schemas.ScriptRequest` | Campaign JSON with segments & copy | Generates campaign metadata, social copy, and 3-slide storyboard via Gemini. |
| `POST` | `/api/generate-assets` | JSON: `schemas.AssetRequest` | `{"projectId": str, "segments": list}` | Synthesizes voiceovers (Edge TTS) and inpaints backgrounds (`flux-fill-pro`) for all slides. |
| `POST` | `/api/regenerate-segment` | JSON: `schemas.RegenerateSegmentRequest` | Updated segment dict | Regenerates audio and/or inpainting for a single slide. |
| `POST` | `/api/render-video` | JSON: `schemas.RenderRequest` | `{"projectId": str, "video_url": str, "thumbnail_url": str}` | Assembles the final MP4 video via MoviePy and creates the cover thumbnail. |
| `POST` | `/api/translate-project` | JSON: `schemas.TranslateProjectRequest` | `{"status": "success", "voice": str, "segments": list}` | Translates script copy and updates voice selection to target language. |
| `DELETE` | `/api/delete-project/{projectId}` | Path: `projectId: str` | `{"status": "success", "message": str}` | Deletes project directory and all associated assets from `outputs/`. |
| `GET` | `/api/download-campaign-bundle/{project_id}` | Path: `project_id: str` | `FileResponse` (application/zip) | Bundles video, thumbnail, still images, and formatted copy into a ZIP file. |
| `GET` | `/api/youtube-check-auth` | None | `{"secretsConfigured": bool, "authenticated": bool}` | Checks whether `client_secrets.json` and `client_token.json` exist. |
| `POST` | `/api/youtube-upload` | JSON: `schemas.YouTubeUploadRequest` | `{"status": "success", "videoId": str}` | Uploads rendered `final_video.mp4` to YouTube channel. |

---

## 📄 License
MIT License. Built for automated, high-converting short-form product video production.
