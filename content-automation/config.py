import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
JOBS_DIR = BASE_DIR / "jobs"

for d in (UPLOADS_DIR, OUTPUTS_DIR, JOBS_DIR):
    d.mkdir(exist_ok=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
IMAGE_API_BASE_URL = os.getenv("IMAGE_API_BASE_URL", "")
VIDEO_API_KEY = os.getenv("VIDEO_API_KEY", "")
VIDEO_API_BASE_URL = os.getenv("VIDEO_API_BASE_URL", "")

MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))

# Package presets — edit these to match your pricing tiers
PACKAGES = {
    "starter": {"label": "Starter", "images": 5, "reels": 5},
    "business": {"label": "Business", "images": 10, "reels": 10},
    "monthly": {"label": "Monthly", "images": 15, "reels": 20},
}
