"""
Video generation integration (image-to-video, for reels).

Fill in `generate_reel()` once you've picked a provider. Most
image-to-video APIs (Kling, Runway, Pika) follow a two-step async
pattern: (1) submit the image + a motion prompt, get back a task id,
(2) poll until the task finishes and grab the resulting video URL.
The polling loop below is written generically — adjust field names
to match your chosen provider's actual response shape.

Until filled in, runs in DRY-RUN mode: generates a short static video
from the still image using ffmpeg (2 seconds, Ken-Burns-free) so you
can test the full pipeline before paying for real video generation.
"""
import asyncio
import subprocess
from pathlib import Path

import httpx

from config import VIDEO_API_KEY, VIDEO_API_BASE_URL

MOTION_PROMPTS = {
    "pan": "Slow smooth pan across the product, subtle camera drift, no distortion.",
    "rotate": "Gentle rotation to reveal the product from multiple angles.",
    "zoom": "Slow zoom in on product detail and texture, cinematic product-ad feel.",
}


async def generate_reel(source_image: Path, motion: str, out_path: Path, duration_sec: int = 5) -> Path:
    """
    Generate one short vertical video clip from a still product image.
    """
    prompt = MOTION_PROMPTS.get(motion, MOTION_PROMPTS["pan"])

    if not VIDEO_API_KEY:
        _dry_run_static_video(source_image, out_path, duration_sec)
        return out_path

    # --- Replace with your chosen provider's real submit+poll calls ---
    # async with httpx.AsyncClient(timeout=300) as client:
    #     with open(source_image, "rb") as f:
    #         submit = await client.post(
    #             f"{VIDEO_API_BASE_URL}/v1/image-to-video",
    #             headers={"Authorization": f"Bearer {VIDEO_API_KEY}"},
    #             files={"image": f},
    #             data={"prompt": prompt, "duration": duration_sec, "aspect_ratio": "9:16"},
    #         )
    #     submit.raise_for_status()
    #     task_id = submit.json()["task_id"]
    #
    #     for _ in range(60):  # poll up to ~5 min
    #         await asyncio.sleep(5)
    #         status = await client.get(
    #             f"{VIDEO_API_BASE_URL}/v1/tasks/{task_id}",
    #             headers={"Authorization": f"Bearer {VIDEO_API_KEY}"},
    #         )
    #         status.raise_for_status()
    #         body = status.json()
    #         if body["status"] == "succeeded":
    #             video_url = body["video_url"]
    #             video_resp = await client.get(video_url)
    #             out_path.write_bytes(video_resp.content)
    #             return out_path
    #         if body["status"] == "failed":
    #             raise RuntimeError(f"Video generation failed: {body}")
    #
    #     raise TimeoutError("Video generation did not finish in time")
    # --------------------------------------------------------------

    raise NotImplementedError(
        "Add your video API call above, or leave VIDEO_API_KEY blank to dry-run."
    )


def _dry_run_static_video(source_image: Path, out_path: Path, duration_sec: int):
    """Turn a still photo into a short vertical video via ffmpeg, no AI call."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(source_image),
            "-t", str(duration_sec),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path),
        ],
        check=True,
        capture_output=True,
    )
