"""
Runs one full job: N photos in -> assembled delivery.zip out.

Images and videos are generated in parallel across all photos/styles to
minimize wall-clock time. Captions are generated once as a batch. Then
everything is assembled and zipped.
"""
import asyncio
import itertools
from pathlib import Path

from config import OUTPUTS_DIR
from job_store import update_job
from integrations.image_gen import generate_image, STYLE_PROMPTS
from integrations.video_gen import generate_reel, MOTION_PROMPTS
from integrations.captions import generate_captions
from assembler import add_caption_overlay, extract_thumbnail, write_captions_file, zip_delivery


async def run_job(job_id: str, job: dict):
    try:
        update_job(job_id, status="processing", step="starting")

        photos = [Path(p) for p in job["photo_paths"]]
        business_name = job["business_name"]
        business_type = job["business_type"]
        product_name = job.get("product_name", "")
        n_images = job["n_images"]
        n_reels = job["n_reels"]

        delivery_dir = OUTPUTS_DIR / job_id / "delivery"
        images_dir = delivery_dir / "images"
        reels_dir = delivery_dir / "reels"
        thumbs_dir = delivery_dir / "thumbnails"
        for d in (images_dir, reels_dir, thumbs_dir):
            d.mkdir(parents=True, exist_ok=True)

        styles = list(itertools.islice(itertools.cycle(STYLE_PROMPTS.keys()), n_images))
        motions = list(itertools.islice(itertools.cycle(MOTION_PROMPTS.keys()), n_reels))
        photo_cycle_images = list(itertools.islice(itertools.cycle(photos), n_images))
        photo_cycle_reels = list(itertools.islice(itertools.cycle(photos), n_reels))

        # --- Run images, raw videos, and captions in parallel ---
        update_job(job_id, step="generating images, videos and captions")

        image_tasks = [
            generate_image(photo, style, images_dir / f"image_{i+1}.jpg", product_name)
            for i, (photo, style) in enumerate(zip(photo_cycle_images, styles))
        ]
        raw_video_paths = [reels_dir / f"raw_{i+1}.mp4" for i in range(n_reels)]
        video_tasks = [
            generate_reel(photo, motion, raw_path)
            for photo, motion, raw_path in zip(photo_cycle_reels, motions, raw_video_paths)
        ]
        captions_task = generate_captions(business_name, business_type, product_name, n_reels)

        await asyncio.gather(*image_tasks)
        await asyncio.gather(*video_tasks)
        captions = await captions_task

        # --- Assemble: burn captions onto reels, extract thumbnails ---
        update_job(job_id, step="assembling reels and thumbnails")
        for i, raw_path in enumerate(raw_video_paths):
            final_path = reels_dir / f"reel_{i+1}.mp4"
            caption_text = captions[i]["caption"] if i < len(captions) else ""
            add_caption_overlay(raw_path, caption_text, final_path)
            extract_thumbnail(final_path, thumbs_dir / f"thumb_{i+1}.jpg")
            raw_path.unlink(missing_ok=True)

        write_captions_file(captions, delivery_dir / "captions.txt")

        # --- Zip it up ---
        update_job(job_id, step="zipping delivery")
        zip_path = OUTPUTS_DIR / job_id / "delivery.zip"
        zip_delivery(delivery_dir, zip_path)

        update_job(job_id, status="done", step="complete", delivery_zip=str(zip_path))

    except Exception as e:
        update_job(job_id, status="failed", step="error", error=str(e))
        raise
