"""
AI Model Registry — Multi-Model Generation Engine
Inspired by Open-Generative-AI's 500+ model catalog and OpenReels' provider flexibility.
We curate only the best 3-5 models per category for production quality.
"""

# ─── Image Generation Models ─────────────────────────────────────────────────
IMAGE_MODELS = {
    "flux-schnell": {
        "label": "⚡ Flux Schnell (Fast, Good Quality)",
        "provider": "replicate",
        "model_id": "black-forest-labs/flux-schnell",
        "cost_per_image": 0.003,
        "speed": "fast",
        "quality": "good",
        "supports_aspect_ratio": True,
        "best_for": ["product photos", "quick iterations", "testing"],
    },
    "flux-dev": {
        "label": "🎨 Flux Dev (Slower, Higher Quality)",
        "provider": "replicate",
        "model_id": "black-forest-labs/flux-dev",
        "cost_per_image": 0.025,
        "speed": "medium",
        "quality": "high",
        "supports_aspect_ratio": True,
        "best_for": ["hero shots", "lifestyle scenes", "premium brands"],
    },
    "sdxl": {
        "label": "🖼️ Stable Diffusion XL (Balanced)",
        "provider": "replicate",
        "model_id": "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
        "cost_per_image": 0.01,
        "speed": "medium",
        "quality": "high",
        "supports_aspect_ratio": False,
        "default_width": 768,
        "default_height": 1344,
        "best_for": ["artistic styles", "illustrations", "creative directions"],
    },
    "ideogram": {
        "label": "✍️ Ideogram V2 (Best for Text-in-Image)",
        "provider": "replicate",
        "model_id": "ideogram-ai/ideogram-v2",
        "cost_per_image": 0.08,
        "speed": "medium",
        "quality": "premium",
        "supports_aspect_ratio": True,
        "best_for": ["logos in scenes", "text overlays", "brand banners"],
    },
}

# ─── Inpainting / Product Placement Models ────────────────────────────────────
INPAINT_MODELS = {
    "flux-fill-pro": {
        "label": "🔮 Flux Fill Pro (Best Product Placement)",
        "provider": "replicate",
        "model_id": "black-forest-labs/flux-fill-pro",
        "cost_per_image": 0.05,
        "best_for": ["product background replacement", "lifestyle scene placement"],
    },
}

# ─── Video Generation Models (Image-to-Video) ────────────────────────────────
VIDEO_MODELS = {
    "minimax-video-01": {
        "label": "🎬 MiniMax Video-01 (Best Motion Quality)",
        "provider": "replicate",
        "model_id": "minimax/video-01",
        "cost_per_video": 0.10,
        "duration": "5s",
        "quality": "premium",
        "speed": "slow",
        "best_for": ["product reveals", "lifestyle motion", "premium brands"],
    },
    "kling-v1.6": {
        "label": "🌟 Kling v1.6 Standard (Fast AI Video)",
        "provider": "replicate",
        "model_id": "kwaivgi/kling-v1.6-standard",
        "cost_per_video": 0.08,
        "duration": "5s",
        "quality": "high",
        "speed": "medium",
        "best_for": ["fast product motion", "social media ads"],
    },
    "wan-2.1-i2v": {
        "label": "🎥 Wan 2.1 I2V (Budget-Friendly Motion)",
        "provider": "replicate",
        "model_id": "wan-ai/wan-2.1-i2v-480p",
        "cost_per_video": 0.04,
        "duration": "5s",
        "quality": "good",
        "speed": "fast",
        "best_for": ["budget campaigns", "quick previews"],
    },
    "ltx-video": {
        "label": "⚡ LTX Video (Current Default)",
        "provider": "replicate",
        "model_id": "lightricks/ltx-video",
        "cost_per_video": 0.05,
        "duration": "4s",
        "quality": "good",
        "speed": "medium",
        "best_for": ["general motion", "atmospheric effects"],
    },
}

# ─── TTS Voice Providers ──────────────────────────────────────────────────────
TTS_PROVIDERS = {
    "edge-tts": {
        "label": "🆓 Edge TTS (Free, Microsoft)",
        "cost_per_char": 0.0,
        "quality": "good",
        "voices": {
            "en-IN-NeerjaNeural": "🇮🇳 Neerja (Indian English, Female)",
            "en-IN-PrabhatNeural": "🇮🇳 Prabhat (Indian English, Male)",
            "hi-IN-SwaraNeural": "🇮🇳 Swara (Hindi, Female)",
            "hi-IN-MadhurNeural": "🇮🇳 Madhur (Hindi, Male)",
            "en-US-EmmaNeural": "🇺🇸 Emma (Fashion/Lifestyle)",
            "en-US-AndrewNeural": "🇺🇸 Andrew (Tech/Gadgets)",
            "en-US-AvaNeural": "🇺🇸 Ava (Luxury/Premium)",
            "en-GB-SoniaNeural": "🇬🇧 Sonia (British Elegance)",
            "en-US-GuyNeural": "🇺🇸 Guy (Home Decor/General)",
            "en-US-BrianNeural": "🇺🇸 Brian (Food/Cafe)",
        },
    },
    "openai-tts": {
        "label": "💎 OpenAI TTS (Premium, Natural)",
        "cost_per_char": 0.000015,
        "quality": "premium",
        "requires_key": "OPENAI_API_KEY",
        "voices": {
            "alloy": "Alloy (Balanced, Neutral)",
            "echo": "Echo (Warm, Male)",
            "fable": "Fable (Storyteller)",
            "onyx": "Onyx (Deep, Authoritative)",
            "nova": "Nova (Bright, Female)",
            "shimmer": "Shimmer (Soft, Gentle)",
        },
    },
    "elevenlabs": {
        "label": "👑 ElevenLabs (Ultra-Premium, Voice Clone)",
        "cost_per_char": 0.00003,
        "quality": "ultra-premium",
        "requires_key": "ELEVENLABS_API_KEY",
        "voices": {
            "Rachel": "Rachel (Calm, Narration)",
            "Adam": "Adam (Deep, Male)",
            "Bella": "Bella (Young, Female)",
            "Antoni": "Antoni (Warm, Male)",
            "Domi": "Domi (Assertive, Female)",
            "Elli": "Elli (Gentle, Female)",
        },
    },
}

# ─── Stock Footage Providers ──────────────────────────────────────────────────
STOCK_PROVIDERS = {
    "pexels": {
        "label": "📸 Pexels (Free HD Stock Video)",
        "api_url": "https://api.pexels.com/videos/search",
        "requires_key": "PEXELS_API_KEY",
        "cost": 0.0,
    },
    "pixabay": {
        "label": "🖼️ Pixabay (Free Stock Photos & Video)",
        "api_url": "https://pixabay.com/api/videos/",
        "requires_key": "PIXABAY_API_KEY",
        "cost": 0.0,
    },
}


def get_model_info(category: str, model_key: str) -> dict:
    """Get model info by category and key."""
    registries = {
        "image": IMAGE_MODELS,
        "inpaint": INPAINT_MODELS,
        "video": VIDEO_MODELS,
        "tts": TTS_PROVIDERS,
        "stock": STOCK_PROVIDERS,
    }
    registry = registries.get(category, {})
    return registry.get(model_key, {})


def estimate_cost(image_model: str = "flux-schnell", video_model: str = None,
                  tts_provider: str = "edge-tts", num_slides: int = 3,
                  char_count: int = 300, use_stock: bool = False) -> dict:
    """
    Estimate total API cost before generation — inspired by OpenReels' cost transparency.
    Returns a breakdown dict with per-category and total cost.
    """
    img_info = IMAGE_MODELS.get(image_model, IMAGE_MODELS["flux-schnell"])
    image_cost = img_info["cost_per_image"] * num_slides

    video_cost = 0.0
    if video_model:
        vid_info = VIDEO_MODELS.get(video_model, {})
        video_cost = vid_info.get("cost_per_video", 0.0)

    tts_info = TTS_PROVIDERS.get(tts_provider, TTS_PROVIDERS["edge-tts"])
    tts_cost = tts_info["cost_per_char"] * char_count

    total = image_cost + video_cost + tts_cost

    return {
        "images": {"model": image_model, "count": num_slides, "cost": round(image_cost, 4)},
        "video": {"model": video_model or "none", "count": 1 if video_model else 0, "cost": round(video_cost, 4)},
        "tts": {"provider": tts_provider, "chars": char_count, "cost": round(tts_cost, 4)},
        "stock": {"provider": "pexels" if use_stock else "none", "cost": 0.0},
        "total": round(total, 4),
    }


def get_available_models_for_frontend() -> dict:
    """Returns a simplified dict of available models for the frontend UI dropdowns."""
    return {
        "image_models": {k: v["label"] for k, v in IMAGE_MODELS.items()},
        "video_models": {k: v["label"] for k, v in VIDEO_MODELS.items()},
        "tts_providers": {k: v["label"] for k, v in TTS_PROVIDERS.items()},
    }
