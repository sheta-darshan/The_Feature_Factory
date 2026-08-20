"""
AI Director Score Engine — Structured Scene Planning
Inspired by OpenReels' DirectorScore system that plans each scene with
narration, visual prompts, camera movements, duration, and transitions.
"""
import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


async def generate_director_score(product_name: str, brand: str = "", niche: str = "General Retail",
                                   visual_style: str = "Auto", num_slides: int = 3,
                                   price: str = "", cta: str = "", duration: int = 30) -> dict:
    """
    Uses LLM to generate a structured DirectorScore JSON — a full scene-by-scene plan
    with narration, visual prompts, camera movements, timing, and transitions.
    
    This replaces the simple 'segments' array with a rich, directed storyboard.
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    prompt = f"""You are a world-class commercial video director and product cinematographer.
    
    Create a DIRECTOR SCORE — a structured JSON storyboard for a premium {niche} product video.
    
    PRODUCT DETAILS:
    - Product: {product_name}
    - Brand: {brand}
    - Price: {price}
    - CTA: {cta}
    - Visual Style: {visual_style}
    - Target Duration: ~{duration} seconds
    - Number of Scenes: {num_slides}
    
    DIRECTOR SCORE RULES:
    1. Each scene must have a SPECIFIC camera movement (not just "zoom in")
    2. Visual prompts must reference the PREVIOUS scene's color palette for consistency
    3. Narration must be conversational, high-energy, and at a 4th-grade reading level
    4. The first scene is always the HERO REVEAL — product in a premium setting
    5. The middle scene(s) are LIFESTYLE — product in real-world use
    6. The final scene is the CTA — brand, price, and call to action
    
    Return STRICTLY as JSON with this exact structure:
    {{
        "scenes": [
            {{
                "id": 1,
                "type": "hero_reveal",
                "narration": "spoken text for voiceover",
                "visual_prompt": "extremely detailed visual description for AI image generation",
                "camera_movement": "one of: slow_zoom_in, dolly_forward, pan_left, pan_right, tilt_up, orbit_left, static_hero",
                "duration_seconds": 3.5,
                "transition_to_next": "one of: cross_dissolve, fade_black, slide_left, zoom_burst, match_cut"
            }}
        ],
        "global_style": {{
            "color_palette": ["#hex1", "#hex2", "#hex3"],
            "mood": "description of overall mood",
            "lighting": "description of lighting direction",
            "font_recommendation": "one of: modern_sans, luxury_serif, handwritten, bold_impact"
        }},
        "music_keywords": ["ambient", "upbeat", "cinematic"],
        "target_audience": "description of who this video targets"
    }}"""
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        score = json.loads(response.text)
        return score
    except Exception as e:
        print(f"Director Score generation failed: {e}. Returning default structure.")
        # Return a sensible default
        return {
            "scenes": [
                {
                    "id": 1, "type": "hero_reveal",
                    "narration": f"Meet the {product_name} by {brand}.",
                    "visual_prompt": f"Premium studio product photography of {product_name}, soft directional lighting, dark marble surface",
                    "camera_movement": "slow_zoom_in",
                    "duration_seconds": 3.5,
                    "transition_to_next": "cross_dissolve"
                },
                {
                    "id": 2, "type": "lifestyle",
                    "narration": f"Designed for those who demand the best.",
                    "visual_prompt": f"{product_name} in a luxurious lifestyle setting, warm natural light, bokeh background",
                    "camera_movement": "dolly_forward",
                    "duration_seconds": 4.0,
                    "transition_to_next": "cross_dissolve"
                },
                {
                    "id": 3, "type": "cta",
                    "narration": f"Get yours now. {cta}",
                    "visual_prompt": f"{product_name} beauty shot with brand logo, clean studio background",
                    "camera_movement": "static_hero",
                    "duration_seconds": 2.5,
                    "transition_to_next": "fade_black"
                },
            ],
            "global_style": {
                "color_palette": ["#0f172a", "#6366f1", "#f8fafc"],
                "mood": "premium, aspirational",
                "lighting": "soft directional with rim highlights",
                "font_recommendation": "modern_sans"
            },
            "music_keywords": ["ambient", "cinematic", "premium"],
            "target_audience": f"{niche} enthusiasts looking for quality products"
        }
