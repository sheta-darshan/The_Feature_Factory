"""
Data Contract Schemas for The Feature Factory
Typed Pydantic models for scripts, assets, project metadata, product locks, and generation logs.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ProductLock(BaseModel):
    """
    Lightweight structured record derived from rembg-isolated product image
    to guide prompt conditioning and ensure exact visual fidelity.
    """
    aspect_ratio: str = "1:1"
    width: int = 0
    height: int = 0
    bounding_box: Optional[List[int]] = None  # [min_x, min_y, max_x, max_y]
    dominant_colors: List[str] = Field(default_factory=list)  # Hex colors
    lock_summary: str = ""  # Plaintext constraint reminder


class GenerationStepLog(BaseModel):
    """
    Audit log of each model invocation, cost, and asset artifact.
    """
    step_name: str
    model: str
    provider: str
    prompt: Optional[str] = None
    cost_estimate: float = 0.0
    output_path: Optional[str] = None
    timestamp: int = 0
    status: str = "completed"
    details: Optional[Dict[str, Any]] = None


class StoryboardSegment(BaseModel):
    text_to_speak: str
    visual_prompt: str
    audio_path: str = ""
    image_path: str = ""
    duration_seconds: Optional[float] = None
    word_count: Optional[int] = None


# Alias for backward compatibility with existing endpoints
Segment = StoryboardSegment


class ScriptRequest(BaseModel):
    niche: str
    product_title: str
    brand: str = ""
    price: str = ""
    cta: str = ""
    image_path: str = ""
    isolate_background: bool = True
    duration: int = 30
    visual_style: str = "Auto"
    imageModel: str = "flux-schnell"
    voice: str = "Auto"
    aspectRatio: str = "9:16"
    captionPreset: str = "Auto"
    brand_tone: str = "Luxury Prestige"
    asset_type: str = "standalone"
    enable_ai_video: bool = False
    videoModel: str = "ltx-video"
    ttsProvider: str = "edge-tts"
    ttsVoice: str = "Auto"


class AssetRequest(BaseModel):
    projectId: str
    segments: List[StoryboardSegment]
    aspectRatio: str = "9:16"
    imageModel: str = "flux-schnell"
    voice: str = "en-US-GuyNeural"
    ttsProvider: str = "edge-tts"


class RenderRequest(BaseModel):
    projectId: str
    segments: List[StoryboardSegment]
    aspectRatio: str = "9:16"
    musicTrack: str = ""
    fontName: str = "Arial Bold"
    highlightColor: str = "Yellow"
    captionPosition: str = "Bottom"
    addWatermark: bool = False
    captionPreset: str = "default"
    noSound: bool = False


class TranslateProjectRequest(BaseModel):
    projectId: str
    targetLang: str
    segments: List[StoryboardSegment]


class RegenerateSegmentRequest(BaseModel):
    projectId: str
    segmentIndex: int
    textToSpeak: str
    visualPrompt: str
    aspectRatio: str = "9:16"
    regenerateAudio: bool = True
    regenerateImage: bool = True
    imageModel: str = "flux-schnell"
    voice: str = "en-US-GuyNeural"


class YouTubeUploadRequest(BaseModel):
    projectId: str
    title: str
    description: str
    tags: str = ""


class ProjectMetadata(BaseModel):
    projectId: str
    title: str = ""
    description: str = ""
    tags: str = ""
    thumbnail_prompt: str = ""
    thumbnail_text: str = ""
    timestamp: int = 0
    status: str = "created"
    aspectRatio: str = "9:16"
    videoUrl: str = ""
    thumbnailUrl: str = ""
    niche: str = ""
    productTitle: str = ""
    brand: str = ""
    price: str = ""
    cta: str = ""
    brandTone: str = "Luxury Prestige"
    assetType: str = "standalone"
    enableAiVideo: bool = False
    rawProductImages: List[str] = Field(default_factory=list)
    isolateBackground: bool = True
    alternativeHooks: List[str] = Field(default_factory=list)
    instagramCaption: str = ""
    shortsTitle: str = ""
    shortsDescription: str = ""
    whatsappStatusText: str = ""
    duration: int = 30
    visualStyle: str = "Clean Commercial Photography"
    imageModel: str = "flux-schnell"
    voice: str = "en-US-GuyNeural"
    captionPreset: str = "tiktok"
    segments: List[StoryboardSegment] = Field(default_factory=list)
    product_lock: Optional[ProductLock] = None
    generation_logs: List[GenerationStepLog] = Field(default_factory=list)
