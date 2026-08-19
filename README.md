# 🏭 The Feature Factory — AI Product Content Studio

**The Feature Factory** is an end-to-end automated AI studio that transforms raw product photos into high-converting, professional short-form video ads (Instagram Reels, YouTube Shorts, and WhatsApp Statuses) for local retail businesses, brands, and e-commerce stores.

---

## 🌟 What It Does

Local businesses often lack professional photography, lighting gear, video editors, and agency budgets. **The Feature Factory** allows them to turn simple product snaps into agency-grade marketing assets in seconds:

1. **AI Background Isolation & Inpainting**: Uses local `rembg` background subtraction combined with Replicate's `black-forest-labs/flux-fill-pro` to place isolated products into photorealistic commercial lifestyle environments.
2. **Multi-Angle Support**: Upload up to 3 product angles (Hero front, lifestyle wearing/model shot, detail close-up) that stitch seamlessly across slides.
3. **Problem-Solution Commercial Copywriting**: Uses Google Gemini to generate high-retention 3-slide ad scripts (Hook & Pain Point ➔ Lifestyle Product Solution ➔ Closing Brand Offer & CTA).
4. **Studio Voiceovers**: Generates voiceover narrations with Microsoft Edge TTS customized by product category (Luxury Studio, Fashion Editorial, Cozy Home Decor, Gourmet Food).
5. **Dynamic Video Assembly**: MoviePy-powered compilation with true cross-dissolve slide transitions, audio ducking (BGM reduces during speech), Slide 1 attention-grabbing Hook banners, and Slide 3 Commercial Checkout Cards (`[Brand] | [Price] | [CTA]`).
6. **Platform-Specific Social Media Kits**: Delivers one-click copy-pasteable captions formatted for **Instagram Reels** (with first-line fold protection & hashtag packs), **YouTube Shorts** (with `#shorts` indexing), and **WhatsApp Statuses** (conversational chat reply triggers).

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) installed and available in your system `PATH`.
- API keys:
  - `GEMINI_API_KEY` (Google AI Studio)
  - `REPLICATE_API_TOKEN` (Replicate for FLUX Inpainting)

### 2. Installation & Setup
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

### 3. Configure Environment
Copy `.env.template` to `.env` and fill in your API tokens:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
REPLICATE_API_TOKEN=your_replicate_api_token_here
PORT=8001
```

### 4. Run the Studio
```bash
python main.py
```
Open your browser and navigate to `http://127.0.0.1:8001`.

---

## 📂 Project Architecture

```text
The_Feature_Factory/
├── main.py                    # FastAPI server & video pipeline orchestrator
├── generator.py               # Gemini copywriting, inpainting & MoviePy video assembler
├── templates/
│   └── index.html             # Premium SaaS dark-mode studio dashboard
├── static/
│   ├── fonts/                 # Bundled typography (Outfit-Bold.ttf)
│   ├── music/                 # Background music tracks & notification chimes
│   └── sfx/                   # Coin clinks, whooshes, and clock audio effects
├── uploads/                   # Temporary store for uploaded product photos
├── outputs/                   # Saved campaigns, thumbnails, and compiled MP4 reels
├── content_calendar_365.md    # 365-day retail product marketing reel idea calendar
├── requirements.txt           # Dependency specifications
└── .env.template              # Environment variables template
```

---

## 📄 License
MIT License. Built for repeatable, high-converting product marketing content production.
