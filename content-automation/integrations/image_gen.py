"""
Image generation integration.

Fill in `generate_image()` with a real call once you've picked a provider
(Nano Banana Pro, Flux Kontext, Ideogram, etc). Every one of these APIs
takes roughly the same shape: a reference image + a text prompt, and
returns a new image. Swap the implementation here; nothing else in the
project needs to change.

Until you fill this in, it runs in DRY-RUN mode: it just copies the
source photo to the output path so you can test the full pipeline
end-to-end before spending on real API calls.
"""
import shutil
from pathlib import Path

import httpx

from config import IMAGE_API_KEY, IMAGE_API_BASE_URL

STYLE_PROMPTS = {
    "studio": "Clean white studio background, soft even lighting, product centered, e-commerce style.",
    "lifestyle": "Natural lifestyle setting matching the product category, soft natural light, in-use context.",
    "festival": "Festive promotional background with tasteful seasonal decor, warm inviting lighting.",
    "premium": "Premium advertising look, dramatic lighting, high-end editorial feel.",
}


async def generate_image(source_photo: Path, style: str, out_path: Path, product_name: str = "") -> Path:
    """
    Generate one styled product image from a source photo.

    source_photo: path to the client's uploaded photo
    style: one of STYLE_PROMPTS keys (studio / lifestyle / festival / premium)
    out_path: where to write the resulting image
    product_name: optional product name for prompt context
    """
    prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["studio"])
    if product_name:
        prompt = f"{prompt} Product: {product_name}."

    if not IMAGE_API_KEY:
        # DRY RUN: no key configured yet, just pass the photo through
        # so the rest of the pipeline can be tested end-to-end.
        shutil.copy(source_photo, out_path)
        return out_path

    # --- Replace this block with your chosen provider's real call ---
    # Example shape (adjust to your provider's actual API):
    #
    # async with httpx.AsyncClient(timeout=120) as client:
    #     with open(source_photo, "rb") as f:
    #         resp = await client.post(
    #             f"{IMAGE_API_BASE_URL}/v1/edit",
    #             headers={"Authorization": f"Bearer {IMAGE_API_KEY}"},
    #             files={"image": f},
    #             data={"prompt": prompt},
    #         )
    #     resp.raise_for_status()
    #     out_path.write_bytes(resp.content)
    # return out_path
    # -------------------------------------------------------------

    raise NotImplementedError(
        "Add your image API call above, or leave IMAGE_API_KEY blank to dry-run."
    )
