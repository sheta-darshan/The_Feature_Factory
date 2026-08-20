"""
Takes the raw generated images/videos + captions and turns them into a
finished delivery folder: captioned reels, thumbnails, a captions.txt,
zipped up as delivery.zip.
"""
import shutil
import subprocess
import zipfile
from pathlib import Path


def add_caption_overlay(video_path: Path, caption: str, out_path: Path):
    """Burn a short caption line onto the bottom of a vertical video."""
    safe_caption = caption.replace("'", "\u2019").replace(":", "\u2236")[:90]
    drawtext = (
        f"drawtext=text='{safe_caption}':fontcolor=white:fontsize=42:"
        f"box=1:boxcolor=black@0.5:boxborderw=20:"
        f"x=(w-text_w)/2:y=h-th-120"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", drawtext,
            "-codec:a", "copy", str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def extract_thumbnail(video_path: Path, out_path: Path, at_seconds: float = 0.5):
    """Grab a frame from the video to use as a thumbnail image."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(at_seconds), "-i", str(video_path),
            "-frames:v", "1", str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def write_captions_file(captions: list[dict], out_path: Path):
    lines = []
    for i, c in enumerate(captions, start=1):
        lines.append(f"--- Reel {i} ---")
        lines.append(c["caption"])
        lines.append(c["hashtags"])
        lines.append("")
    out_path.write_text("\n".join(lines))


def zip_delivery(delivery_dir: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in delivery_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(delivery_dir))
