"""
Async Job Manager for The Feature Factory
Authoritative engine for:
- Asset Generation (execute_asset_generation)
- Video Assembly & Rendering (execute_video_render)
- Background Task Runners & Job Queueing

Both synchronous endpoints in main.py and asynchronous background jobs in job_manager.py
call the exact same shared implementation functions.
All metadata access is synchronized across processes/threads via metadata_manager (filelock).
"""
import os
import json
import time
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

import generator
import metadata_manager
from schemas import AssetRequest, RenderRequest, StoryboardSegment
from ai_models import ANIMATION_TIERS, VIDEO_MODELS

JOBS_DIR = Path("jobs")
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory registry of running asyncio Tasks
_ACTIVE_TASKS: Dict[str, asyncio.Task] = {}


def get_voice_settings_for_style(visual_style: str) -> tuple[str, str]:
    """
    Returns optimal edge-tts rate and pitch adjustments based on the chosen visual style.
    """
    settings = {
        "High-End Fashion Editorial": ("+4%", "+0Hz"),
        "Luxury Studio Showcase": ("-4%", "-1Hz"),
        "Gourmet Food Editorial": ("+3%", "+0Hz"),
    }
    return settings.get(visual_style, ("+0%", "+0Hz"))


# ---------------------------------------------------------------------------
# Job Persistence & State Management
# ---------------------------------------------------------------------------

def generate_job_id() -> str:
    """Generate a unique timestamped job ID."""
    return f"job_{int(time.time())}_{uuid.uuid4().hex[:6]}"


def job_file_path(job_id: str) -> Path:
    """Resolve the JSON file path for a job ID."""
    return JOBS_DIR / f"{job_id}.json"


def create_job(job_type: str, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new job record in queued state and persist to disk.
    """
    job_id = generate_job_id()
    now_iso = datetime.now(timezone.utc).isoformat()
    job_data = {
        "job_id": job_id,
        "job_type": job_type,  # 'assets' | 'render' | 'full_pipeline'
        "project_id": project_id,
        "status": "queued",     # 'queued' | 'processing' | 'completed' | 'failed'
        "step": "queued",       # Human-readable current progress step
        "progress": 0.0,        # 0.0 to 1.0
        "created_at": now_iso,
        "updated_at": now_iso,
        "payload": payload,
        "error": None,
        "result": None,
        "logs": [
            {
                "timestamp": now_iso,
                "message": f"Job {job_id} created ({job_type}) for project {project_id}"
            }
        ]
    }
    save_job(job_id, job_data)
    return job_data


def save_job(job_id: str, job_data: Dict[str, Any]):
    """Persist job dictionary to jobs/<job_id>.json atomically."""
    job_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    p = job_file_path(job_id)
    temp_p = p.with_suffix(".tmp")
    temp_p.write_text(json.dumps(job_data, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_p.replace(p)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Load a job by its ID from jobs/<job_id>.json."""
    p = job_file_path(job_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading job {job_id}: {e}")
        return None


def update_job_progress(job_id: str, status: Optional[str] = None, step: Optional[str] = None,
                        progress: Optional[float] = None, result: Optional[Dict[str, Any]] = None,
                        error: Optional[str] = None, log_message: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Update job fields, append log message, and persist atomically."""
    job = get_job(job_id)
    if job is None:
        return None

    if status is not None:
        job["status"] = status
    if step is not None:
        job["step"] = step
    if progress is not None:
        job["progress"] = min(1.0, max(0.0, round(progress, 3)))
    if result is not None:
        job["result"] = result
    if error is not None:
        job["error"] = error

    if log_message:
        job.setdefault("logs", []).append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": log_message
        })

    save_job(job_id, job)
    return job


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    """List most recent jobs."""
    jobs = []
    for p in JOBS_DIR.glob("*.json"):
        try:
            jobs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs[:limit]


# ---------------------------------------------------------------------------
# Core Shared Engine Implementations
# (Used by both Synchronous and Asynchronous Endpoints)
# ---------------------------------------------------------------------------

async def execute_asset_generation(
    project_id: str,
    req_data: Any,
    progress_callback: Optional[Callable[[str, float, str], None]] = None
) -> Dict[str, Any]:
    """
    Single authoritative implementation for generating all voiceovers and visuals.
    Can be called synchronously from /api/generate-assets or asynchronously by background jobs.
    """
    if isinstance(req_data, dict):
        req = AssetRequest(**req_data)
    elif isinstance(req_data, AssetRequest):
        req = req_data
    else:
        req = AssetRequest.model_validate(req_data)

    project_dir = f"outputs/{project_id}"
    os.makedirs(project_dir, exist_ok=True)

    def _report(step: str, progress: float, message: str):
        if progress_callback:
            progress_callback(step, progress, message)

    _report("initializing_assets", 0.05, "Initializing asset generation pipeline")

    # Read existing metadata safely under lock
    meta = metadata_manager.read_metadata(project_id)

    # Update metadata safely
    metadata_manager.update_metadata(project_id, {
        "aspectRatio": req.aspectRatio,
        "imageModel": req.imageModel,
        "status": "assets_generating"
    })

    visual_style = meta.get("visualStyle", "Clean Commercial Photography")
    resolved_voice = meta.get("voice", req.voice or "en-US-GuyNeural")

    # Resolve the voice parameter
    voice_to_use = req.voice
    if voice_to_use == "Auto" or not voice_to_use:
        voice_to_use = resolved_voice
    if voice_to_use == "Auto" or not voice_to_use:
        voice_to_use = "en-US-GuyNeural"

    rate_str, pitch_str = get_voice_settings_for_style(visual_style)

    total_segments = len(req.segments)
    updated_segments = []

    # Step 1: Voiceovers (Parallel)
    _report("generating_voiceover", 0.15, f"Synthesizing voiceover narration for {total_segments} slides")

    tts_provider = getattr(req, "ttsProvider", None) or meta.get("ttsProvider", "edge-tts")
    voice_tasks = []
    for i, seg in enumerate(req.segments):
        audio_path = f"{project_dir}/audio_{i}.mp3"
        seg_voice = getattr(seg, "voice", None) or voice_to_use
        if tts_provider == "elevenlabs":
            voice_tasks.append(
                generator.generate_voiceover_elevenlabs(seg.text_to_speak, audio_path, voice=seg_voice)
            )
        elif tts_provider == "openai-tts":
            import tts_providers
            voice_tasks.append(
                tts_providers.generate_voiceover_multi(seg.text_to_speak, audio_path, voice=seg_voice, provider="openai-tts")
            )
        else:
            voice_tasks.append(
                generator.generate_voiceover(seg.text_to_speak, audio_path, voice=seg_voice, rate=rate_str, pitch=pitch_str)
            )

    audio_paths = await asyncio.gather(*voice_tasks)
    _report("voiceovers_completed", 0.30, "Voiceovers synthesized successfully with word-level timings")

    # Step 2: Visual Generation (Sequential with rate-limit delays)
    raw_imgs = meta.get("rawProductImages", [])
    isolate_bg = meta.get("isolateBackground", True)
    img_model_to_use = "schnell" if req.imageModel == "video" else req.imageModel

    for i, seg in enumerate(req.segments):
        step_pct = 0.30 + (0.65 * (i / max(1, total_segments)))
        _report(f"generating_visual_{i+1}_of_{total_segments}", step_pct,
                f"Generating visual asset for slide {i+1}/{total_segments}")

        image_filename = f"image_{i}"
        image_path_raw = f"{project_dir}/{image_filename}.webp"

        raw_img = raw_imgs[i] if i < len(raw_imgs) else (raw_imgs[0] if raw_imgs else "")
        explicit_stock = getattr(seg, "visual_source", "auto") in ["stock_video", "stock_image"]

        # Slide 1 model integrity
        asset_type = meta.get("assetType", "standalone")
        if i == 0 and asset_type == "model_worn" and raw_img and os.path.exists(raw_img):
            import shutil
            from PIL import Image
            try:
                with Image.open(raw_img) as m_img:
                    m_img.convert("RGB").save(image_path_raw, "JPEG", quality=90)
                actual_image_path = image_path_raw
            except Exception:
                shutil.copy2(raw_img, image_path_raw)
                actual_image_path = image_path_raw
        elif raw_img and not explicit_stock:
            # Replicate flux-fill-pro inpainting
            actual_image_path = await asyncio.to_thread(
                generator.generate_product_image_replicate,
                seg.visual_prompt,
                raw_img,
                image_path_raw,
                req.aspectRatio,
                img_model_to_use,
                isolate_bg,
                meta.get("niche", "General Retail"),
                meta.get("visualStyle", "Auto")
            )
        else:
            # Stock footage fallback or text-to-image
            stock_res = None
            if (os.getenv("PEXELS_API_KEY") or os.getenv("PIXABAY_API_KEY")):
                try:
                    import stock_footage
                    orientation = "portrait" if req.aspectRatio == "9:16" else "landscape"
                    query = seg.visual_prompt.split(",")[0].strip() or f"{meta.get('niche', 'product')} lifestyle"

                    if getattr(seg, "visual_source", "auto") == "stock_video" or os.getenv("PEXELS_API_KEY"):
                        videos = await stock_footage.search_pexels_videos(query, orientation=orientation, per_page=1)
                        if videos:
                            stock_video_path = f"{project_dir}/stock_video_{i}.mp4"
                            stock_res = await stock_footage.download_stock_asset(videos[0]["url"], stock_video_path)

                    if not stock_res and os.getenv("PIXABAY_API_KEY"):
                        images = await stock_footage.search_pixabay_images(query, orientation="vertical" if req.aspectRatio == "9:16" else "horizontal", per_page=1)
                        if images:
                            stock_img_path = f"{project_dir}/stock_image_{i}.jpg"
                            stock_res = await stock_footage.download_stock_asset(images[0]["url"], stock_img_path)
                except Exception as s_err:
                    print(f"Stock footage search failed ({s_err}), falling back to Replicate text-to-image")
                    stock_res = None

            if stock_res and os.path.exists(stock_res):
                actual_image_path = stock_res
            else:
                actual_image_path = await asyncio.to_thread(
                    generator.generate_image_replicate,
                    seg.visual_prompt,
                    image_path_raw,
                    req.aspectRatio,
                    img_model_to_use
                )

        # Check Animation Tier / Generative Video Motion
        animation_tier = getattr(req, "animationTier", None) or meta.get("animationTier", "static")
        tier_cfg = ANIMATION_TIERS.get(animation_tier, ANIMATION_TIERS.get("static", {}))
        tier_slides = tier_cfg.get("animate_slides", [])

        should_animate = False
        if tier_slides == "all":
            should_animate = True
        elif isinstance(tier_slides, list) and (i in tier_slides or (i - total_segments) in tier_slides):
            should_animate = True
        elif getattr(req, "enableAiVideo", False) or req.imageModel == "video":
            should_animate = True

        if should_animate and not actual_image_path.endswith(".mp4") and os.path.exists(actual_image_path):
            _report(f"animating_slide_{i+1}", step_pct + 0.04, f"Animating slide {i+1} into dynamic video clip")
            tier_model = tier_cfg.get("video_model") or getattr(req, "videoModel", None) or meta.get("videoModel") or "kling-3.0-pro"
            video_model_info = VIDEO_MODELS.get(tier_model, {})
            provider = video_model_info.get("provider", "fal")

            animated_video_path = f"{project_dir}/animated_clip_{i}.mp4"
            motion_prompt = getattr(seg, "motion_prompt", "") or seg.visual_prompt

            try:
                if provider == "fal":
                    res_anim = await asyncio.to_thread(
                        generator.animate_image_fal,
                        actual_image_path,
                        motion_prompt,
                        animated_video_path,
                        video_model=tier_model
                    )
                else:
                    res_anim = await asyncio.to_thread(
                        generator.animate_image_replicate,
                        actual_image_path,
                        motion_prompt,
                        animated_video_path,
                        req.aspectRatio,
                        video_model=tier_model
                    )

                if res_anim and res_anim.endswith(".mp4") and os.path.exists(res_anim):
                    actual_image_path = res_anim
            except Exception as anim_err:
                print(f"Warning: Slide {i+1} animation failed ({anim_err}). Using static image.")

        seg_dict = {
            "text_to_speak": seg.text_to_speak,
            "visual_prompt": seg.visual_prompt,
            "audio_path": audio_paths[i],
            "image_path": actual_image_path,
            "camera_movement": getattr(seg, "camera_movement", "slow_zoom_in"),
            "transition_to_next": getattr(seg, "transition_to_next", "cross_dissolve"),
            "scene_type": getattr(seg, "scene_type", "lifestyle"),
            "visual_source": getattr(seg, "visual_source", "auto"),
            "motion_prompt": getattr(seg, "motion_prompt", ""),
            "beat_type": getattr(seg, "beat_type", "")
        }
        updated_segments.append(seg_dict)

        # Rate-limit delay (10s) between Replicate calls
        if i < total_segments - 1 and not (actual_image_path.endswith(".mp4") or "stock" in actual_image_path):
            await asyncio.sleep(10.0)

    # Persist updated segments to metadata under lock
    metadata_manager.update_metadata(project_id, {
        "status": "assets_generated",
        "segments": updated_segments
    })

    _report("completed", 1.0, "All assets generated successfully")

    return {
        "projectId": project_id,
        "project_id": project_id,
        "segments": updated_segments,
        "metadata_path": f"{project_dir}/metadata.json"
    }


async def execute_video_render(
    project_id: str,
    req_data: Any,
    progress_callback: Optional[Callable[[str, float, str], None]] = None
) -> Dict[str, Any]:
    """
    Single authoritative implementation for MoviePy video assembly, dynamic subtitles,
    and thumbnail creation.
    Can be called synchronously from /api/render-video or asynchronously by background jobs.
    """
    if isinstance(req_data, dict):
        req = RenderRequest(**req_data)
    elif isinstance(req_data, RenderRequest):
        req = req_data
    else:
        req = RenderRequest.model_validate(req_data)

    project_dir = f"outputs/{project_id}"
    os.makedirs(project_dir, exist_ok=True)

    def _report(step: str, progress: float, message: str):
        if progress_callback:
            progress_callback(step, progress, message)

    _report("initializing_render", 0.05, "Building MoviePy timeline and audio configuration")

    meta = metadata_manager.read_metadata(project_id)
    visual_style = meta.get("visualStyle", "Clean Commercial Photography")

    # Format segments into list of dicts
    processed_segments = []
    for s in req.segments:
        if hasattr(s, "model_dump"):
            processed_segments.append(s.model_dump())
        elif hasattr(s, "dict"):
            processed_segments.append(s.dict())
        elif isinstance(s, dict):
            processed_segments.append(s)
        else:
            processed_segments.append(dict(s))

    # Resolve Background Music Track
    bg_music_path = None
    if req.musicTrack and not req.noSound:
        if req.musicTrack in ["Auto-Select", "auto", "Auto"]:
            style_music_mapping = {
                "Cyberpunk": "synthwave_beat.mp3",
                "Retro Anime": "ambient_dream.mp3",
                "Dark Sci-Fi / Fantasy": "ambient_space.mp3",
                "Steampunk Oil Painting": "ambient_dream.mp3",
                "Cinematic Photo": "ambient_dream.mp3",
                "Storybook Sketch Art": "ambient_dream.mp3",
                "Cosmic Synthwave / Hologram": "synthwave_beat.mp3",
                "Traditional Ink Wash (Sumi-e)": "ambient_dream.mp3",
                "Claymation / Stop-Motion": "ambient_dream.mp3",
                "Comic Book Noir": "synthwave_beat.mp3"
            }
            mapped_track = style_music_mapping.get(visual_style, "ambient_dream.mp3")
            bg_music_path = f"static/music/{mapped_track}"
        else:
            bg_music_path = f"static/music/{req.musicTrack}"

    final_video_path = f"{project_dir}/final_video.mp4"
    thumbnail_path = f"{project_dir}/thumbnail.jpg"

    _report("assembling_video", 0.25, "Rendering motion, camera pans, and subtitles with MoviePy")

    # Step 1: Video Assembly
    caption_preset = req.captionPreset if req.captionPreset != "Auto" else meta.get("captionPreset", "mrbeast")
    aspect_ratio_to_use = req.aspectRatio if req.aspectRatio != "Auto" else meta.get("aspectRatio", "9:16")

    await asyncio.to_thread(
        generator.assemble_video,
        segments=processed_segments,
        output_path=final_video_path,
        aspect_ratio=aspect_ratio_to_use,
        bg_music_path=bg_music_path if not req.noSound else None,
        font_name=req.fontName,
        highlight_color=req.highlightColor,
        caption_position=req.captionPosition,
        add_watermark=req.addWatermark or bool(meta.get("brand")),
        caption_preset=caption_preset,
        no_sound=req.noSound,
        brand=meta.get("brand", ""),
        price=meta.get("price", ""),
        cta=meta.get("cta", ""),
        niche=meta.get("niche", "")
    )

    _report("rendering_thumbnail", 0.85, "Generating promotional cover thumbnail with product lock")

    # Step 2: Thumbnail Generation
    thumb_prompt = meta.get("thumbnail_prompt", "")
    thumb_text = meta.get("thumbnail_text", "")
    if not thumb_prompt:
        thumb_prompt = f"Product advertisement thumbnail for: {meta.get('product_title', meta.get('title', 'Product'))}, dramatic studio lighting"
    if not thumb_text:
        thumb_text = meta.get("cta") or meta.get("title", "BUY NOW")[:20]

    raw_imgs = meta.get("rawProductImages", [])
    raw_img_path = raw_imgs[0] if raw_imgs and os.path.exists(raw_imgs[0]) else None

    await asyncio.to_thread(
        generator.generate_thumbnail,
        project_id,
        thumb_prompt,
        thumb_text,
        req.aspectRatio,
        raw_img_path,
        meta.get("niche", "General Retail"),
        meta.get("visualStyle", "Auto")
    )

    # Duration calculation
    dur_seconds = 0.0
    try:
        from moviepy import VideoFileClip
        with VideoFileClip(final_video_path) as vf:
            dur_seconds = round(float(vf.duration), 2)
    except Exception:
        dur_seconds = 0.0

    thumbnail_url = f"outputs/{project_id}/thumbnail.jpg" if os.path.exists(thumbnail_path) else ""

    # Atomic metadata update under lock
    def _mutate_render_meta(m: dict):
        m["status"] = "rendered"
        m["videoUrl"] = f"outputs/{project_id}/final_video.mp4"
        m["thumbnailUrl"] = thumbnail_url
        logs = m.setdefault("generation_logs", [])
        logs.append({
            "step_name": "video_assembly",
            "model": "moviepy",
            "provider": "local",
            "cost_estimate": 0.0,
            "output_path": final_video_path,
            "timestamp": int(time.time()),
            "status": "completed"
        })

    metadata_manager.mutate_metadata(project_id, _mutate_render_meta)

    result_data = {
        "projectId": project_id,
        "project_id": project_id,
        "video_url": f"outputs/{project_id}/final_video.mp4",
        "video_path": final_video_path,
        "thumbnail_url": thumbnail_url,
        "duration_seconds": dur_seconds
    }

    _report("completed", 1.0, "Video render complete!")
    return result_data


# ---------------------------------------------------------------------------
# Background Task Dispatchers
# ---------------------------------------------------------------------------

async def _run_assets_job_async(job_id: str, project_id: str, payload: dict):
    """Background worker for asset generation."""
    try:
        def on_progress(step: str, progress: float, message: str):
            update_job_progress(job_id, status="processing", step=step, progress=progress, log_message=message)

        result = await execute_asset_generation(project_id, payload, progress_callback=on_progress)
        update_job_progress(job_id, status="completed", step="completed", progress=1.0,
                            result=result, log_message="Assets generation completed successfully")
    except Exception as e:
        import traceback
        err_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"[JobManager] Assets job {job_id} failed: {err_msg}")
        update_job_progress(job_id, status="failed", step="error", error=str(e),
                            log_message=f"Assets generation failed: {str(e)}")
    finally:
        _ACTIVE_TASKS.pop(job_id, None)


async def _run_render_job_async(job_id: str, project_id: str, payload: dict):
    """Background worker for video render assembly."""
    try:
        def on_progress(step: str, progress: float, message: str):
            update_job_progress(job_id, status="processing", step=step, progress=progress, log_message=message)

        result = await execute_video_render(project_id, payload, progress_callback=on_progress)
        update_job_progress(job_id, status="completed", step="completed", progress=1.0,
                            result=result, log_message="Video render completed successfully")
    except Exception as e:
        import traceback
        err_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"[JobManager] Render job {job_id} failed: {err_msg}")
        update_job_progress(job_id, status="failed", step="error", error=str(e),
                            log_message=f"Render assembly failed: {str(e)}")
    finally:
        _ACTIVE_TASKS.pop(job_id, None)


async def _run_full_pipeline_job_async(job_id: str, project_id: str, payload: dict):
    """
    Runs the complete sequence (assets generation -> video rendering) consecutively,
    scaling progress from 0.0 to 1.0 across both stages.
    """
    try:
        update_job_progress(job_id, status="processing", step="starting_full_pipeline", progress=0.02,
                            log_message="Starting full pipeline automated workflow")

        # 1. Assets Stage (progress 0.05 -> 0.50)
        def on_assets_progress(step: str, progress: float, message: str):
            scaled_p = 0.05 + (0.45 * progress)
            update_job_progress(job_id, status="processing", step=step, progress=scaled_p, log_message=message)

        assets_result = await execute_asset_generation(project_id, payload, progress_callback=on_assets_progress)

        # 2. Prepare Render Payload
        render_payload = {
            "projectId": project_id,
            "segments": assets_result.get("segments", []),
            "aspectRatio": payload.get("aspectRatio", "9:16"),
            "musicTrack": payload.get("musicTrack", "Auto-Select"),
            "fontName": payload.get("fontName", "Outfit-Bold"),
            "highlightColor": payload.get("highlightColor", "Yellow"),
            "captionPosition": payload.get("captionPosition", "Bottom"),
            "addWatermark": payload.get("addWatermark", False),
            "captionPreset": payload.get("captionPreset", "mrbeast"),
            "noSound": payload.get("noSound", False)
        }

        # 3. Render Stage (progress 0.50 -> 1.0)
        def on_render_progress(step: str, progress: float, message: str):
            scaled_p = 0.50 + (0.50 * progress)
            update_job_progress(job_id, status="processing", step=step, progress=scaled_p, log_message=message)

        render_result = await execute_video_render(project_id, render_payload, progress_callback=on_render_progress)

        update_job_progress(job_id, status="completed", step="completed", progress=1.0,
                            result=render_result, log_message="Full pipeline executed successfully!")

    except Exception as e:
        import traceback
        err_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"[JobManager] Full pipeline job {job_id} failed: {err_msg}")
        update_job_progress(job_id, status="failed", step="error", error=str(e),
                            log_message=f"Full pipeline failed: {str(e)}")
    finally:
        _ACTIVE_TASKS.pop(job_id, None)


# ---------------------------------------------------------------------------
# Public Job Dispatchers
# ---------------------------------------------------------------------------

def submit_assets_job(project_id: str, payload: dict) -> dict:
    """Submit an asynchronous asset generation job."""
    job = create_job("assets", project_id, payload)
    task = asyncio.create_task(_run_assets_job_async(job["job_id"], project_id, payload))
    _ACTIVE_TASKS[job["job_id"]] = task
    return job


def submit_render_job(project_id: str, payload: dict) -> dict:
    """Submit an asynchronous video rendering job."""
    job = create_job("render", project_id, payload)
    task = asyncio.create_task(_run_render_job_async(job["job_id"], project_id, payload))
    _ACTIVE_TASKS[job["job_id"]] = task
    return job


def submit_full_pipeline_job(project_id: str, payload: dict) -> dict:
    """Submit an asynchronous end-to-end full pipeline job."""
    job = create_job("full_pipeline", project_id, payload)
    task = asyncio.create_task(_run_full_pipeline_job_async(job["job_id"], project_id, payload))
    _ACTIVE_TASKS[job["job_id"]] = task
    return job
