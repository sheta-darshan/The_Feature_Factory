# ⚠️ Known Issues, Technical Debt & Unfinished Modules

This document lists identified code gaps, unwired modules, missing dependencies, hardcoded values, and potential failure points discovered during codebase inspection. **Do not modify functional code without prior approval; this is an audit reference.**

---

## 1. Missing API Endpoints & Frontend Discrepancies

### Missing `/api/random-product-demo` Endpoint
- **Location**: [`templates/index.html` (Line 1910)](file:///g:/100%20Days%20of%20code/The_Feature_Factory/templates/index.html#L1910)
- **Issue**: The UI contains a button / handler calling `fetch('/api/random-product-demo')` to populate sample demo data. This route is not defined in [`main.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/main.py), resulting in a `404 Not Found` response when triggered in the browser.

---

## 2. Unwired / Orphaned Modules

### 1. AI Director Score Engine (`director.py`)
- **Location**: [`director.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/director.py)
- **Issue**: `generate_director_score()` is fully implemented with Gemini prompt engineering, camera movements (`slow_zoom_in`, `dolly_forward`), scene transitions, and global styling palettes. However, it is never imported or called in [`main.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/main.py), which currently routes all script generation directly through `generator.generate_product_campaign()`.

### 2. Stock Footage Integration (`stock_footage.py`)
- **Location**: [`stock_footage.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/stock_footage.py)
- **Issue**: `search_pexels_videos()`, `search_pixabay_images()`, and `download_stock_asset()` are implemented, but neither [`main.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/main.py) nor [`generator.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py) currently calls them during video assembly.

---

## 3. Dependency Specification Gaps (`requirements.txt`)

The following libraries are imported in source files but missing from the root [`requirements.txt`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/requirements.txt):
- **`httpx`**: Imported in `generator.py`, `stock_footage.py`, and `tts_providers.py`.
- **`google-api-python-client`**, **`google-auth-oauthlib`**, **`google-auth-httplib2`**: Imported in `youtube_uploader.py`. If a user attempts to upload to YouTube without manually installing these, an `ImportError` will occur.
- **`anthropic`**: Imported in `content-automation/integrations/captions.py`.

---

## 4. Code Duplication & Hardcoded Paths

### 1. Duplicate Function Definition in `generator.py`
- **Location**: [`generator.py` (Line 29 and Line 676)](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py)
- **Issue**: `sanitize_visual_prompt(prompt: str)` is defined twice in the same file. Python uses the second definition at runtime, but the duplicate creates dead code and maintenance confusion.

### 2. Hardcoded Absolute Windows Path in `merge_pitch_video.py`
- **Location**: [`merge_pitch_video.py` (Line 7)](file:///g:/100%20Days%20of%20code/The_Feature_Factory/merge_pitch_video.py#L7)
- **Issue**: `voiceover_path = r"C:\Users\sheta\.gemini\antigravity-ide\brain\aee98736-edd7-474d-a428-7af079615d93\pitch_voiceover.mp3"` is hardcoded to a local system directory. This script fails if run on any other machine.

### 3. Hardcoded Windows Font Paths in `generator.py`
- **Location**: [`generator.py` (Lines 1182, 1441)](file:///g:/100%20Days%20of%20code/The_Feature_Factory/generator.py)
- **Issue**: Font paths point directly to `C:\Windows\Fonts\arialbd.ttf` and `C:\Windows\Fonts\impact.ttf`. When run on Linux/macOS or containers, font loading throws an exception and falls back to PIL's unscaled default bitmap font, rather than utilizing the bundled font in [`static/fonts/Outfit-Bold.ttf`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/static/fonts/Outfit-Bold.ttf).

---

## 5. Feature Inconsistencies & Limitations

### 1. Multi-TTS Provider Subtitle Timestamp Degradation
- **Location**: [`generator.py` / `tts_providers.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/tts_providers.py)
- **Issue**: `generator.generate_voiceover()` extracts word boundary events (`WordBoundary`) from Edge TTS to write `audio_{i}.json`. When selecting `openai-tts` or `elevenlabs`, `tts_providers.py` generates the MP3 audio file but does not return word-level timestamps. Consequently, subtitle highlighting cannot synchronize dynamically with spoken words on non-Edge TTS providers.

### 2. Content-Automation Sub-Project Provider Stubs
- **Location**: [`content-automation/integrations/image_gen.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/content-automation/integrations/image_gen.py) and [`content-automation/integrations/video_gen.py`](file:///g:/100%20Days%20of%20code/The_Feature_Factory/content-automation/integrations/video_gen.py)
- **Issue**: Both integration files operate in dry-run mode (copying source images or creating static ffmpeg clips). If an API key is set in `.env` without implementing the actual HTTP client call, they raise `NotImplementedError`.

### 3. Thumbnail Default Aspect Ratio Discrepancy
- **Location**: [`main.py` (Line 777)](file:///g:/100%20Days%20of%20code/The_Feature_Factory/main.py#L777)
- **Issue**: When reading metadata during thumbnail rendering, `main.py` defaults to `"16:9"` (`aspect_ratio = meta.get("aspectRatio", "16:9")`), whereas the core campaign generation workflow defaults to `"9:16"` vertical video.
