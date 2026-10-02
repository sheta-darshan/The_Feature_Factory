import os
import json
import time
import shutil
import asyncio
from typing import List
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
from ai_models import get_available_models_for_frontend, estimate_cost, IMAGE_MODELS, VIDEO_MODELS, TTS_PROVIDERS, ANIMATION_TIERS, match_ambient_sfx

# Import our generator engine, metadata manager and job manager
import generator
import metadata_manager
import job_manager
from job_manager import get_voice_settings_for_style

load_dotenv()

app = FastAPI(title="The Feature Factory - AI Product Content Studio")

# Ensure required directories exist
os.makedirs("outputs", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("static/music", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Mount outputs for static file serving
# Ensure static directories exist before mounting to prevent Starlette RuntimeError
os.makedirs("outputs", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

templates = Jinja2Templates(directory="templates")

from schemas import (
    ScriptRequest,
    StoryboardSegment,
    Segment,
    AssetRequest,
    RenderRequest,
    TranslateProjectRequest,
    RegenerateSegmentRequest,
    YouTubeUploadRequest,
    ProjectMetadata,
    ProductLock,
    GenerationStepLog
)

@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    return templates.TemplateResponse(request, "index.html", {})

@app.get("/api/list-music")
async def api_list_music():
    """
    List available background music files in static/music/
    """
    music_dir = "static/music"
    files = [f for f in os.listdir(music_dir) if f.lower().endswith(('.mp3', '.wav', '.m4a'))]
    return files

@app.get("/api/list-projects")
async def api_list_projects():
    """
    List all generated projects by reading metadata.json from outputs/ subdirectories.
    """
    projects = []
    outputs_dir = "outputs"
    if not os.path.exists(outputs_dir):
        return []
        
    for item in os.listdir(outputs_dir):
        item_path = os.path.join(outputs_dir, item)
        if os.path.isdir(item_path):
            meta = metadata_manager.read_metadata(item)
            if meta:
                projects.append(meta)
                    
    projects.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return projects

@app.get("/api/daily-topic")
async def api_daily_topic():
    """
    Scans content_calendar_365.md and pulls a random speculative topic not marked as Done.
    """
    calendar_path = "content_calendar_365.md"
    if not os.path.exists(calendar_path):
        return {"topic": "Imagine if human cities were built inside giant trees."}
        
    try:
        import re
        import random
        unused_topics = []
        with open(calendar_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Matches Day headings: **Day X:** Imagine if...
                match = re.search(r"\*\*Day \d+:\*\*\s*(.*)", line)
                if match:
                    topic_text = match.group(1).strip()
                    if not topic_text.endswith("-Done"):
                        unused_topics.append(topic_text)
                        
        if unused_topics:
            selected = random.choice(unused_topics)
            return {"topic": selected}
        else:
            return {"topic": "Imagine if gravity on Earth randomly turned off for five seconds every day."}
    except Exception as e:
        print(f"Error parsing calendar: {e}")
        return {"topic": "Imagine if space travel was as cheap as buying a bus ticket."}

@app.get("/api/random-product-demo")
async def api_random_product_demo():
    """
    Returns sample/demo product data for rapid testing and one-click frontend demo population.
    """
    demo_products = [
        {
            "niche": "Jewellery",
            "product_title": "18K Solid Gold Peacock Pendant",
            "brand": "Aura Fine Jewels",
            "price": "$189",
            "cta": "Shop 20% Off Today",
            "visual_style": "Cinematic Photo"
        },
        {
            "niche": "Clothing/Fashion",
            "product_title": "Italian Linen Oversized Summer Shirt",
            "brand": "Sartoria Studio",
            "price": "$79",
            "cta": "Order Before Stock Runs Out",
            "visual_style": "Cinematic Photo"
        },
        {
            "niche": "Cosmetics",
            "product_title": "Hydra-Glow Botanical Facial Serum",
            "brand": "Lumina Botanicals",
            "price": "$45",
            "cta": "Get Free Express Shipping",
            "visual_style": "Cinematic Photo"
        },
        {
            "niche": "Furniture/Home Decor",
            "product_title": "Nordic Walnut Minimalist Desk Lamp",
            "brand": "Klar Modern Living",
            "price": "$129",
            "cta": "Claim Your Design Discount",
            "visual_style": "Cinematic Photo"
        },
        {
            "niche": "Restaurants",
            "product_title": "Artisanal Truffle Butter Brioche Burger",
            "brand": "The Velvet Grill",
            "price": "$22",
            "cta": "Book Your Table Now",
            "visual_style": "Cinematic Photo"
        }
    ]
    import random
    return random.choice(demo_products)

@app.get("/api/trending-topics")
async def api_trending_topics():
    """
    Step 1.5: Brainstorms trending topics using live Google Search grounding.
    """
    try:
        topics = await generator.brainstorm_trending_topics()
        return {"status": "success", "topics": topics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/translate-project")
async def api_translate_project(req: TranslateProjectRequest):
    """
    Translates all storyboard segment narrations to the target language,
    updates the project metadata voice selection, and returns the translated storyboard.
    """
    project_id = req.projectId
    project_dir = f"outputs/{project_id}"
    meta_path = f"{project_dir}/metadata.json"
    
    lang_voice_map = {
        "German": "de-DE-FlorianMultilingualNeural",
        "French": "fr-FR-HenriNeural",
        "Spanish": "es-ES-AlvaroNeural",
        "Japanese": "ja-JP-KeitaNeural",
        "Portuguese": "pt-BR-AntonioNeural",
        "Hindi": "hi-IN-MadhurNeural"
    }
    target_voice = lang_voice_map.get(req.targetLang, "en-US-GuyNeural")
    
    async def translate_segment(seg: Segment):
        translated_text = await generator.translate_text(seg.text_to_speak, req.targetLang)
        return Segment(
            text_to_speak=translated_text,
            visual_prompt=seg.visual_prompt,  # Visual prompt stays in English for Replicate
            audio_path=seg.audio_path,
            image_path=seg.image_path
        )
        
    try:
        tasks = [translate_segment(seg) for seg in req.segments]
        translated_segments = await asyncio.gather(*tasks)
        
        # Update metadata if it exists
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["voice"] = target_voice
            # Translate SEO Title and Description
            meta["title"] = await generator.translate_text(meta.get("title", ""), req.targetLang)
            meta["description"] = await generator.translate_text(meta.get("description", ""), req.targetLang)
            if meta.get("thumbnail_text"):
                meta["thumbnail_text"] = await generator.translate_text(meta["thumbnail_text"], req.targetLang)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
                
        return {
            "status": "success",
            "voice": target_voice,
            "segments": [
                {
                    "text_to_speak": seg.text_to_speak,
                    "visual_prompt": seg.visual_prompt,
                    "audio_path": seg.audio_path,
                    "image_path": seg.image_path
                }
                for seg in translated_segments
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@app.delete("/api/delete-project/{projectId}")
async def api_delete_project(projectId: str):
    """
    Delete a project folder and all its assets from outputs/
    """
    project_dir = f"outputs/{projectId}"
    if not os.path.exists(project_dir):
        raise HTTPException(status_code=404, detail="Project not found")
        
    try:
        shutil.rmtree(project_dir)
        return {"status": "success", "message": f"Project {projectId} deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


@app.post("/api/upload-product-image")
async def api_upload_product_image(file: UploadFile = File(...)):
    os.makedirs("uploads", exist_ok=True)
    import shutil
    filePath = f"uploads/{int(time.time())}_{file.filename}"
    with open(filePath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filePath": filePath}

@app.post("/api/upload-product-images")
async def api_upload_product_images(files: List[UploadFile] = File(...)):
    os.makedirs("uploads", exist_ok=True)
    from PIL import Image
    saved_paths = []
    for file in files:
        filePath = f"uploads/{int(time.time())}_{os.path.splitext(file.filename)[0]}.jpg"
        try:
            # Load file in PIL to compress/scale
            with Image.open(file.file) as img:
                # Max dimension 1536px safeguard
                max_dim = 1536
                w, h = img.size
                if w > max_dim or h > max_dim:
                    scale = max_dim / max(w, h)
                    img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                
                # Save as compressed JPEG
                img.convert("RGB").save(filePath, "JPEG", quality=85)
                print(f"Compressed and saved upload: {filePath} ({img.size})")
        except Exception as e:
            print(f"Failed optimizing upload {file.filename} ({e}), falling back to direct copy.")
            file.file.seek(0)
            with open(filePath, "wb") as buffer:
                import shutil
                shutil.copyfileobj(file.file, buffer)
        saved_paths.append(filePath)
    return {"filePaths": saved_paths}

@app.post("/api/generate-script")
async def api_generate_script(req: ScriptRequest):
    """
    Step 1: Generate JSON script and SEO metadata from a thought.
    """
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured in .env")
    try:
        data = await generator.generate_product_campaign(
            niche=req.niche,
            product_title=req.product_title,
            brand=req.brand,
            price=req.price,
            cta=req.cta,
            duration_seconds=req.duration, 
            visual_style=req.visual_style,
            voice=req.voice,
            aspect_ratio=req.aspectRatio,
            caption_preset=req.captionPreset,
            use_director_score=req.use_director_score
        )
        project_id = f"project_{int(time.time())}"
        # Ensure project output directory exists
        os.makedirs(f"outputs/{project_id}", exist_ok=True)
        
        # Save project metadata
        metadata = {
            "projectId": project_id,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "tags": data.get("tags", ""),
            "thumbnail_prompt": data.get("thumbnail_prompt", ""),
            "thumbnail_text": data.get("thumbnail_text", ""),
            "timestamp": int(time.time()),
            "status": "script_generated",
            "aspectRatio": data.get("aspectRatio", "9:16"),
            "videoUrl": "",
            "niche": req.niche,
            "productTitle": req.product_title,
            "brand": req.brand,
            "price": req.price,
            "cta": req.cta,
            "brandTone": req.brand_tone,
            "assetType": req.asset_type,
            "enableAiVideo": req.enable_ai_video,
            "animationTier": req.animationTier,
            "rawProductImages": [x.strip() for x in req.image_path.split(",") if x.strip()],
            "isolateBackground": req.isolate_background,
            "alternativeHooks": data.get("alternative_hooks", []),
            "instagramCaption": data.get("instagram_caption", ""),
            "shortsTitle": data.get("shorts_title", ""),
            "shortsDescription": data.get("shorts_description", ""),
            "whatsappStatusText": data.get("whatsapp_status_text", ""),
            "duration": data.get("duration", req.duration if req.duration > 0 else 30),
            "visualStyle": data.get("visualStyle", req.visual_style),
            "imageModel": req.imageModel,
            "voice": data.get("voice", req.voice),
            "captionPreset": data.get("captionPreset", req.captionPreset),
            "segments": data.get("segments", []),
            "director_score": data.get("director_score"),
            "product_lock": None,
            "generation_logs": [
                {
                    "step_name": "script_generation",
                    "model": "gemini-2.5-flash",
                    "provider": "google",
                    "prompt": f"{req.niche}: {req.product_title} (Brand: {req.brand})",
                    "cost_estimate": 0.0005,
                    "output_path": f"outputs/{project_id}/metadata.json",
                    "timestamp": int(time.time()),
                    "status": "completed"
                }
            ]
        }
        metadata_manager.write_metadata(project_id, metadata)
            
        return {
            "projectId": project_id,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "tags": data.get("tags", ""),
            "visualStyle": metadata["visualStyle"],
            "voice": metadata["voice"],
            "duration": metadata["duration"],
            "aspectRatio": metadata["aspectRatio"],
            "captionPreset": metadata.get("captionPreset", "mrbeast"),
            "alternativeHooks": metadata.get("alternativeHooks", []),
            "instagramCaption": metadata.get("instagramCaption", ""),
            "shortsTitle": metadata.get("shortsTitle", ""),
            "shortsDescription": metadata.get("shortsDescription", ""),
            "whatsappStatusText": metadata.get("whatsappStatusText", ""),
            "segments": data.get("segments", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_voice_settings_for_style(visual_style: str):
    """
    Returns optimal edge-tts rate and pitch adjustments based on the chosen visual style.
    """
    settings = {
        "High-End Fashion Editorial": ("+4%", "+0Hz"),
        "Luxury Studio Showcase": ("-4%", "-1Hz"),
        "Gourmet Food Editorial": ("+3%", "+0Hz"),
    }
    return settings.get(visual_style, ("+0%", "+0Hz"))

@app.post("/api/generate-assets")
async def api_generate_assets(req: AssetRequest):
    """
    Step 2 (Synchronous): Generate all audio (edge-tts) and images (Replicate/Flux) concurrently.
    Calls shared engine implementation in job_manager.execute_asset_generation.
    """
    try:
        return await job_manager.execute_asset_generation(req.projectId, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Asset generation failed: {str(e)}")

@app.post("/api/regenerate-segment")
async def api_regenerate_segment(req: RegenerateSegmentRequest):
    """
    Regenerates only a single segment's voiceover and/or image.
    """
    project_id = req.projectId
    project_dir = f"outputs/{project_id}"
    os.makedirs(project_dir, exist_ok=True)
    
    audio_filename = f"audio_{req.segmentIndex}.mp3"
    audio_path = f"{project_dir}/{audio_filename}"
    
    image_filename = f"image_{req.segmentIndex}" # extension added later
    image_path_raw = f"{project_dir}/{image_filename}.webp"
    
    # Load metadata and visual style for pitch/rate adjustments
    visual_style = "Cinematic Photo"
    resolved_voice = "en-US-GuyNeural"
    meta = metadata_manager.read_metadata(project_id)
    if meta:
        meta["imageModel"] = req.imageModel
        visual_style = meta.get("visualStyle", "Clean Commercial Photography")
        resolved_voice = meta.get("voice", "en-US-GuyNeural")
        metadata_manager.update_metadata(project_id, {"imageModel": req.imageModel})
            
    # Resolve the voice parameter
    voice_to_use = req.voice
    if voice_to_use == "Auto" or not voice_to_use:
        voice_to_use = resolved_voice
    if voice_to_use == "Auto" or not voice_to_use:
        voice_to_use = "en-US-GuyNeural"
        
    rate_str, pitch_str = get_voice_settings_for_style(visual_style)
    
    try:
        tasks = []
        
        # 1. Regenerate voiceover if requested
        if req.regenerateAudio:
            tts_provider = meta.get("ttsProvider", "edge-tts") if meta else "edge-tts"
            if tts_provider == "elevenlabs":
                tasks.append(generator.generate_voiceover_elevenlabs(req.textToSpeak, audio_path, voice=voice_to_use))
            elif tts_provider == "openai-tts":
                import tts_providers
                tasks.append(tts_providers.generate_voiceover_multi(req.textToSpeak, audio_path, voice=voice_to_use, provider="openai-tts"))
            else:
                tasks.append(generator.generate_voiceover(req.textToSpeak, audio_path, voice=voice_to_use, rate=rate_str, pitch=pitch_str))
        else:
            # Dummy awaitable to match unpack count
            async def dummy_voice():
                return audio_path
            tasks.append(dummy_voice())
            
        # 2. Regenerate visual asset if requested
        if req.regenerateImage:
            async def run_image():
                raw_imgs = meta.get("rawProductImages", [])
                isolate_bg = meta.get("isolateBackground", True)
                img_model_to_use = "schnell" if req.imageModel == "video" else req.imageModel
                
                raw_img = ""
                if raw_imgs and len(raw_imgs) > 0:
                    raw_img = raw_imgs[req.segmentIndex] if req.segmentIndex < len(raw_imgs) else raw_imgs[0]
                
                if raw_img:
                    return await asyncio.to_thread(
                        generator.generate_product_image_replicate,
                        req.visualPrompt,
                        raw_img,
                        image_path_raw,
                        req.aspectRatio,
                        img_model_to_use,
                        isolate_bg
                    )
                else:
                    return await asyncio.to_thread(
                        generator.generate_image_replicate,
                        req.visualPrompt,
                        image_path_raw,
                        req.aspectRatio,
                        img_model_to_use
                    )
            tasks.append(run_image())
        else:
            async def dummy_image():
                # Search for existing file with mp4 or jpg extension
                for ext in [".mp4", ".jpg"]:
                    test_file = f"{project_dir}/image_{req.segmentIndex}{ext}"
                    if os.path.exists(test_file):
                        return test_file
                return f"{project_dir}/image_{req.segmentIndex}.jpg"
            tasks.append(dummy_image())
            
        res_audio, res_image = await asyncio.gather(*tasks)
        
        if req.regenerateAudio:
            actual_audio_path = f"outputs/{project_id}/{os.path.basename(res_audio)}"
        else:
            actual_audio_path = f"outputs/{project_id}/{audio_filename}"
            
        actual_image_path = f"outputs/{project_id}/{os.path.basename(res_image)}"
            
        return {
            "text_to_speak": req.textToSpeak,
            "visual_prompt": req.visualPrompt,
            "audio_path": actual_audio_path,
            "image_path": actual_image_path
        }
    except Exception as e:
        print(f"Error regenerating segment {req.segmentIndex}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/render-video")
async def api_render_video(req: RenderRequest):
    """
    Step 3 (Synchronous): Assemble video with MoviePy, burn subtitles, generate thumbnail.
    Calls shared engine implementation in job_manager.execute_video_render.
    """
    try:
        return await job_manager.execute_video_render(req.projectId, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render video: {str(e)}")

@app.post("/api/youtube-upload")
async def api_youtube_upload(req: YouTubeUploadRequest):
    """
    Endpoint to publish the rendered video to YouTube.
    """
    project_id = req.projectId
    video_path = f"outputs/{project_id}/final_video.mp4"
    if not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail="Rendered video not found. Please render the video first.")
        
    try:
        import youtube_uploader
        # Run upload in background thread to avoid blocking FastAPI event loop
        video_id = await asyncio.to_thread(
            youtube_uploader.upload_video_to_youtube,
            video_path,
            req.title,
            req.description,
            req.tags
        )
        return {"status": "success", "videoId": video_id}
    except FileNotFoundError as fnf:
        # Precondition failed (no client_secrets.json)
        raise HTTPException(status_code=412, detail=str(fnf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube Upload Failed: {str(e)}")

@app.get("/api/youtube-check-auth")
async def api_youtube_check_auth():
    """
    Helper to check if YouTube API client secrets and cached tokens exist.
    """
    secrets_exists = os.path.exists("client_secrets.json")
    token_exists = os.path.exists("client_token.json")
    return {
        "secretsConfigured": secrets_exists,
        "authenticated": token_exists
    }




@app.get("/api/download-campaign-bundle/{project_id}")
async def download_campaign_bundle(project_id: str):
    """
    Bundles all project marketing assets (Final Video, Cover Thumbnail, 
    HD Still Lifestyle Photos, and Formatted Social Captions) into a single 
    client-ready ZIP file.
    """
    import zipfile
    import io
    
    project_dir = f"outputs/{project_id}"
    if not os.path.exists(project_dir):
        raise HTTPException(status_code=404, detail="Project not found")
        
    meta = metadata_manager.read_metadata(project_id)

    brand = meta.get("brand", "").replace(" ", "_") or "Brand"
    product_title = meta.get("productTitle", "").replace(" ", "_") or "Product"
    zip_filename = f"{brand}_{product_title}_Campaign_Kit.zip"
    zip_path = os.path.join(project_dir, zip_filename)
    
    # Create the zip archive
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # 1. Add final compiled video
        video_path = os.path.join(project_dir, "final_video.mp4")
        if os.path.exists(video_path):
            zipf.write(video_path, arcname="01_Ad_Video_9x16.mp4")
            
        # 2. Add thumbnail
        thumb_path = os.path.join(project_dir, "thumbnail.jpg")
        if os.path.exists(thumb_path):
            zipf.write(thumb_path, arcname="02_Cover_Thumbnail.jpg")
            
        # 3. Add generated slide images
        for i in range(10):
            img_path = os.path.join(project_dir, f"image_{i}.jpg")
            if os.path.exists(img_path):
                zipf.write(img_path, arcname=f"03_Still_Image_Slide_{i+1}.jpg")
            img_png = os.path.join(project_dir, f"image_{i}.png")
            if os.path.exists(img_png):
                zipf.write(img_png, arcname=f"03_Still_Image_Slide_{i+1}.png")
                
        # 4. Generate and add formatted social_captions.txt
        captions_content = f"""=====================================================
🏭 THE FEATURE FACTORY - SOCIAL MEDIA MARKETING KIT
=====================================================

Product: {meta.get('productTitle', '')}
Brand: {meta.get('brand', '')}
Price / Offer: {meta.get('price', '')} | CTA: {meta.get('cta', '')}
Category: {meta.get('niche', '')}
Campaign Title: {meta.get('title', '')}

-----------------------------------------------------
📊 DYNAMIC A/B HOOK OPTIONS (Test on your reels):
-----------------------------------------------------
"""
        for idx, hook in enumerate(meta.get("alternativeHooks", [])):
            captions_content += f"Hook {idx+1}: \"{hook}\"\n"
            
        captions_content += f"""
-----------------------------------------------------
📸 INSTAGRAM REEL COPY & HASHTAGS:
-----------------------------------------------------
{meta.get('instagramCaption', meta.get('description', ''))}

-----------------------------------------------------
🎥 YOUTUBE SHORTS METADATA:
-----------------------------------------------------
TITLE:
{meta.get('shortsTitle', meta.get('title', ''))}

DESCRIPTION:
{meta.get('shortsDescription', meta.get('description', ''))}

-----------------------------------------------------
💬 WHATSAPP STATUS / CHAT TEXT:
-----------------------------------------------------
{meta.get('whatsappStatusText', '')}

=====================================================
Generated with The Feature Factory AI Product Content Studio
=====================================================
"""
        zipf.writestr("04_Social_Media_Captions.txt", captions_content)
        
    return FileResponse(zip_path, media_type="application/zip", filename=zip_filename)


@app.get("/api/models")
async def api_get_models():
    """Returns available AI models for frontend dropdowns."""
    return get_available_models_for_frontend()


@app.post("/api/estimate-cost")
async def api_estimate_cost(req: dict):
    """Returns estimated API cost before generation — inspired by OpenReels' cost transparency."""
    return estimate_cost(
        image_model=req.get("imageModel", "flux-schnell"),
        video_model=req.get("videoModel") if req.get("enableAiVideo") else None,
        tts_provider=req.get("ttsProvider", "edge-tts"),
        num_slides=req.get("numSlides", 3),
        char_count=req.get("charCount", 300),
    )


# ---------------------------------------------------------------------------
# Asynchronous Job Queue Endpoints (Task C Part 2)
# ---------------------------------------------------------------------------
import job_manager

@app.post("/api/jobs/assets", status_code=202)
async def api_jobs_assets(req: AssetRequest):
    """
    Submits an asynchronous background job for generating voiceovers and visual assets.
    Returns immediately with a job_id for status polling.
    """
    job = job_manager.submit_assets_job(req.projectId, req.model_dump())
    return job


@app.post("/api/jobs/render", status_code=202)
async def api_jobs_render(req: RenderRequest):
    """
    Submits an asynchronous background job for assembling the video and rendering thumbnail.
    Returns immediately with a job_id for status polling.
    """
    job = job_manager.submit_render_job(req.projectId, req.model_dump())
    return job


@app.post("/api/jobs/full-pipeline", status_code=202)
async def api_jobs_full_pipeline(req: dict):
    """
    Submits an asynchronous background job to run the complete pipeline (assets -> render).
    """
    project_id = req.get("projectId") or req.get("project_id")
    if not project_id:
        raise HTTPException(status_code=400, detail="projectId is required")
    job = job_manager.submit_full_pipeline_job(project_id, req)
    return job


@app.get("/api/jobs/{job_id}/status")
async def api_jobs_status(job_id: str):
    """
    Polls the progress and result of an asynchronous job.
    """
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs")
async def api_list_jobs(limit: int = 50):
    """
    Lists recent asynchronous background jobs.
    """
    return {"jobs": job_manager.list_jobs(limit=limit)}




@app.get("/api/animation-tiers")
async def api_animation_tiers():
    """Returns available animation quality tiers for the frontend."""
    return {k: {"label": v["label"], "description": v["description"]} for k, v in ANIMATION_TIERS.items()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
