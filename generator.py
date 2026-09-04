import os
import json
import asyncio
import httpx
from google import genai
from google.genai import types
import replicate
from dotenv import load_dotenv
from ai_models import IMAGE_MODELS, VIDEO_MODELS
from tts_providers import generate_voiceover_multi
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import edge_tts
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, VideoFileClip

load_dotenv()

# Configure GenAI Client
client = None
if os.getenv("GEMINI_API_KEY"):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Configure Replicate
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if REPLICATE_API_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN


def sanitize_visual_prompt(prompt: str) -> str:
    """
    Strips accidental text/typography directives from visual prompts
    so diffusion models only generate clean physical environments.
    """
    import re
    cleaned = prompt
    patterns = [
        r"split-screen\s+view\.?\s*(?:On\s+one\s+side,?)?",
        r"On\s+the\s+other\s+side,?\s*[^.]*\.",
        r"(?:with\s+)?(?:the\s+)?['\"][^'\"]*['\"]\s+brand\s+logo[^.]*\.",
        r"brand\s+logo\s+is\s+subtly\s+embossed[^.]*\.",
        r"(?:with\s+)?(?:text|words|typography|logo|banner|button)\s+overlay[^.]*\.",
        r"(?:text|words|letters|typography|logo|banner|button)\s+(?:saying|reading|displaying|showing|written)?\s*['\"][^'\"]*['\"]",
        r"(?:animation\s+of\s+a\s+)?['\"][^'\"]*['\"]\s+button\s+appearing",
        r"(?:DM|order|buy|click|shop|save|discount|sale)\s+now[!.]?",
        r"['\"][^'\"]{1,30}['\"]",  # Remove any short quoted text snippets intended for render
    ]
    for p in patterns:
        cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(",. ")
    return cleaned


def derive_product_lock(transparent_img: Image.Image) -> dict:
    """
    Analyzes rembg-isolated product cut-out to derive a lightweight structured ProductLock
    without any extra LLM calls.
    """
    bbox = transparent_img.getbbox()
    w, h = transparent_img.size
    
    if bbox:
        b_w = bbox[2] - bbox[0]
        b_h = bbox[3] - bbox[1]
        ratio_val = b_w / max(b_h, 1)
        ratio_str = f"{ratio_val:.2f}:1"
    else:
        b_w, b_h = w, h
        ratio_str = "1:1"
        
    # Extract dominant non-transparent colors
    try:
        small = transparent_img.resize((64, 64), Image.Resampling.NEAREST)
        colors = []
        for x in range(small.width):
            for y in range(small.height):
                r, g, b, a = small.getpixel((x, y))
                if a > 128:
                    colors.append((r, g, b))
        if colors:
            from collections import Counter
            bucketed = [((c[0]//32)*32, (c[1]//32)*32, (c[2]//32)*32) for c in colors]
            most_common = Counter(bucketed).most_common(3)
            hex_colors = [f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}" for c, _ in most_common]
        else:
            hex_colors = ["#cccccc", "#333333"]
    except Exception:
        hex_colors = ["#d4af37", "#silver"]

    summary = f"Preserve exact product cut-out ({ratio_str} ratio, dominant tones {', '.join(hex_colors)})"
    
    return {
        "aspect_ratio": ratio_str,
        "width": b_w,
        "height": b_h,
        "bounding_box": list(bbox) if bbox else [0, 0, w, h],
        "dominant_colors": hex_colors,
        "lock_summary": summary
    }


async def generate_product_campaign(niche: str, product_title: str, brand: str = "", price: str = "", cta: str = "", duration_seconds: int = 30, visual_style: str = "Auto", voice: str = "Auto", aspect_ratio: str = "9:16", caption_preset: str = "Auto") -> dict:
    """
    Sends the product details to Gemini to generate high-converting marketing copy and lifestyle prompts.
    """
    global client
    if not client:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
    num_slides = 3
    slide_dur = duration_seconds / float(num_slides)
    max_words_per_slide = max(4, int(slide_dur * 2.3))
    total_word_budget = max(12, int(duration_seconds * 2.3))

    prompt = f"""
    You are an expert product copywriter, advertisement director, and short-form video creator.
    Your job is to build a high-retention marketing campaign for this product:
    - Product Category/Niche: {niche}
    - Product Title: {product_title}
    - Brand Name: {brand}
    - Product Price: {price}
    - Call to Action (CTA): {cta}
    
    You must output a visual campaign strategy containing marketing captions and precise slides breakdown for a short promotional reel (approx. {duration_seconds} seconds long).
    
    CRITICAL COMMERCIAL COPYWRITING RULES:
    1. Hook: Start with a fast, scroll-stopping marketing statement. (e.g. "Looking for the perfect summer outfit?", "This is the secret to a perfect skincare routine...").
    2. Language: Speak in extremely clear, high-energy, persuasive social ad English. No complex vocabulary or sci-fi stories.
    3. CTA: Conclude with a strong buying prompt matching the CTA field.
    
    CRITICAL SCRIPT PACING CONSTRAINT:
    - Target Video Duration: exactly {duration_seconds} seconds across 3 slides (~{slide_dur:.1f}s per slide).
    - Speech Rate: Normal English voiceover is ~2.3 words/second.
    - Each slide's 'text_to_speak' MUST NOT exceed {max_words_per_slide} words.
    - Total script word count across all 3 slides MUST NOT exceed {total_word_budget} words.
    - Write ultra-punchy, concise phrases. DO NOT write long paragraphs or compound sentences.

    CRITICAL VISUAL PROMPT CONSTRAINT (ZERO TEXT / LOGO / NUMBERS / PRODUCT NAME POLICY):
    - 'visual_prompt' must describe ONLY the background environment, surface material, podium, and studio lighting (e.g., 'A polished white marble pedestal, warm softbox directional lighting, subtle blurred grey studio backdrop').
    - NEVER write the product name, brand name, purity numbers (e.g., '92.7'), model numbers, prices, or words in 'visual_prompt'. The physical product is composited on top separately.
    - NEVER include text, letters, typography, slogans, 'Buy Now' buttons, or CTA banners in 'visual_prompt'.
    - ALL text, brand names, prices, and CTAs are rendered programmatically by code overlays.

    STORYBOARD SLIDES STRUCTURE:
    Generate exactly 3 storyboard segments/slides:
    1. Hook Slide (0-3s): Introduce the product. Describe a clean, premium studio backdrop or spotlight surface.
    2. Lifestyle Slide (3-6s): Describe a realistic lifestyle background scenario (e.g., in a sunlit modern room, cafe table, organic natural lighting).
    3. Call to Action / Closing Slide (6-8s): Describe a clean, luxury studio backdrop. (STRICTLY NO text, logos, or buttons in the visual description).
    
    Return strictly in JSON format. The response must be a JSON object with exactly these keys:
      "title": "a catchy click-worthy title for the campaign",
      "instagram_caption": "A scroll-stopping Instagram Reel caption starting with a strong hook (max 120 chars) before truncation, and ending with exactly 5-8 relevant hashtags.",
      "shorts_title": "A short punchy YouTube Shorts title under 55 characters including #shorts",
      "shorts_description": "A YouTube Shorts description optimized for search traffic containing #shorts and #youtubeshorts",
      "whatsapp_status_text": "An ultra-concise, conversational WhatsApp Status text (max 200 characters) ending with a direct chat reply call to action (e.g. 'Reply to order!')",
      "tags": "hashtags matching the niche",
      "visualStyle": "one of: 👑 Luxury Studio Showcase, 🪔 Festive & Wedding Celebration, ☀️ Summer / Fresh Season Drop, ⚡ Flash Sale & Limited Drop, 👗 High-End Fashion Editorial, 🌿 Minimalist Scandinavian Lifestyle, ☕ Gourmet Food Editorial, 📸 Clean Commercial Photography",
      "voice": "Choose the narrator voice that matches the product niche and region: en-IN-NeerjaNeural or en-IN-PrabhatNeural for Indian market campaigns / jewelry / ethnic wear (warm, professional Indian English), hi-IN-SwaraNeural or hi-IN-MadhurNeural for Hindi retail commercials, en-US-EmmaNeural or en-US-AndrewNeural for Fashion/Apparel, en-US-AvaNeural or en-GB-SoniaNeural for Luxury Jewellery/Cosmetics, en-US-GuyNeural for Furniture/Home Decor, en-US-BrianNeural for Restaurants/Cafes",
      "captionPreset": "one of: mrbeast, minimalist, hormozi, tiktok",
      "duration": integer duration in seconds,
      "aspectRatio": "{aspect_ratio}",
      "thumbnail_prompt": "detailed cinematic prompt for generating a promotional thumbnail backdrop (no text)",
      "thumbnail_text": "short punchy 3 word CTA overlay (e.g. 'BUY NOW!')",
      "segments": [
         {{
           "text_to_speak": "ultra-short spoken narration (max {max_words_per_slide} words)",
           "visual_prompt": "A detailed visual description of the studio surface/lighting (STRICTLY NO text or logos)."
         }},
         {{
           "text_to_speak": "ultra-short spoken narration (max {max_words_per_slide} words)",
           "visual_prompt": "A detailed lifestyle background description (STRICTLY NO text or logos)."
         }},
         {{
           "text_to_speak": "ultra-short spoken closing CTA (max {max_words_per_slide} words)",
           "visual_prompt": "A detailed background description for the closing slide (STRICTLY NO text or logos)."
         }}
      ]
    """
    
    max_retries = 3
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            break
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(10)
            else:
                raise e
                
    try:
        data = json.loads(response.text)
        return data
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        raise e

async def generate_script(thought: str, duration_seconds: int = 60, visual_style: str = "Auto", voice: str = "Auto", aspect_ratio: str = "Auto", caption_preset: str = "Auto") -> dict:
    """
    Sends the user's thought to Gemini to generate a script and YouTube SEO metadata.
    Auto-detects and resolves optimal visual style, narrator voice, duration, layout format, and caption preset based on the topic.
    """
    style_guidelines = {
        "High-End Fashion Editorial": "commercial fashion catalog photo, crisp editorial lighting, high-end production value, rich textures, natural color-grading, outdoor sunbeams, sharp product focus",
        "Luxury Studio Showcase": "luxury product portrait photography, glossy dark marble pedestal, soft focused highlights and velvet backdrops, professional studio spotlight, clean reflections, elegant styling",
        "Minimalist Scandinavian Lifestyle": "clean scandinavian architecture background, light warm wood surfaces, bright sunlit room with indoor plants, soft realistic shadows, modern cozy home product showcase",
        "Gourmet Food Editorial": "mouth-watering close-up food photography, high contrast lighting, steam rising, warm rich textures, rustic dining atmosphere, dynamic shadows, commercial food styling",
        "Clean Commercial Photography": "universal commercial studio branding, minimalist soft gradient background, sharp product contours, clean softbox studio lighting, crisp catalog focus",
        "Bright Cinematic Lifestyle": "warm cinema color-grade, handheld-camera aesthetic, shallow depth of field, natural warm golden hour light, premium social media ad style"
    }
    
    # Generate system prompt containing rules for Auto configuration mapping
    prompt = f"""
    You are an expert cinematic director, speculative storyteller, and high-retention short-form video scriptwriter.
    Break down the following thought/topic into a sequence of short video segments.
    
    CRITICAL HIGH-RETENTION STORYTELLING GUIDELINES:
    1. Hook (Segment 1 - 0 to 5s): Start "in media res" (in the middle of the action) with a scroll-stopping statement or paradox.
       - BANNED CLICHÉS: Never start with "Have you ever wondered...", "Imagine a world...", "What if...", "In this video...", or greeting the audience.
       - Good Hook Example: "Tomorrow morning, every computer on Earth shuts down... permanently."
    2. Stakes / Promise (Segment 2 - 5 to 10s): Establish the global stakes or rules of this speculative scenario immediately.
    3. Sensory, Punchy & Simple Conversational Narrations:
       - Keep sentences short, active, and direct. Break up long ideas.
       - BANNED VOCABULARY: Do not use complex, obscure, academic, or rare words (e.g. "exodus", "atrophy", "paradigm", "depletion", "stratification", "volatility", "resonance", "apartheid", "superposition").
       - Reading Level: Spoken narration must be written at a 4th-grade (approx. 10-year-old child) reading level. Use common conversational English.
       - Use highly visual sensory vocabulary (e.g. "cold shadow", "deep hum", "rusty metal", "bitter wind") to describe feelings and sights.
       - Use ellipses `...` or em-dashes `—` to force dramatic voiceover pauses in the Edge-TTS synthesis.
    4. Cliffhanger Loops: Every segment except the final one must end with a brief cliffhanger that forces the viewer into the next segment.
    5. The Polarizing Payoff (Final Segment): Deliver a final punchy takeaway and a polarizing dilemma/question to drive comment section debates.
    
    Thought/Topic: {thought}
    
    UNIVERSAL AUTO-CONFIGURATION RULES:
    You must evaluate and recommend the best settings for this video topic.
    If a parameter below is specified as "Auto", choose the best matching option from the lists below and set it in your JSON response. If a specific option is chosen by the user, preserve their choice.
    
    1. recommended_visual_style (Select the best aesthetic for the topic):
       - "Cinematic Photo" (General realism, nature, historical events)
       - "Dark Sci-Fi / Fantasy" (Space mysteries, monsters, planetary anomalies)
       - "Cyberpunk" (Dystopian tech, virtual reality, hacking)
       - "Retro Anime" (Cozy magical fantasy, floating islands, Ghibli style)
       - "Steampunk Oil Painting" (Clockwork tech, Victorian inventions)
       - "Storybook Sketch Art" (Classic fables, human psychology, deep thoughts)
       - "Cosmic Synthwave / Hologram" (Quantum mechanics, digital trends, synthwave)
       - "Traditional Ink Wash (Sumi-e)" (Zen philosophy, peaceful nature, ancient lore)
       - "Claymation / Stop-Motion" (Quirky, humorous, child-like questions)
       - "Comic Book Noir" (Crimes, dark investigations, detective stories)
       
    2. recommended_voice (Select the voice matching target regional/emotional tone):
       - "en-US-GuyNeural" (Deep, authoritative male - best for sci-fi, cyberpunk, dark themes)
       - "en-US-EmmaNeural" (Warm, expressive female - best for cozy anime, nature, stories)
       - "en-GB-SoniaNeural" (British narrator - best for historical fables, Steampunk)
       - "de-DE-FlorianMultilingualNeural" (German/multilingual tone)
       - "es-ES-AlvaroNeural" (Spanish/European narration)
       - "ja-JP-KeitaNeural" (Japanese)
       - "pt-BR-AntonioNeural" (Portuguese)
       - "hi-IN-MadhurNeural" (Hindi)
       
    3. recommended_duration:
       - 30 (for high action, simple hooks)
       - 45 (for quick fables)
       - 60 (for deep philosophy, complex timelines)
       - 90 (for epic historical chronicles)
       
    4. recommended_aspect_ratio:
       - "16:9" (Widescreen - best for landscapes, history, oil painting)
       - "9:16" (Vertical - best for fast action, tech thrillers, high visual movement)
       
    5. recommended_caption_preset:
       - "mrbeast" (bold uppercase action words)
       - "minimalist" (clean, centered, elegant text)
       - "cyberpunk" (green tech/halftone)
       - "hormozi" (high energy pop words)
       - "tiktok" (colorful standard captions)

    User Configurations (Preserve if not "Auto"):
    - Visual Style Choice: {visual_style}
    - Voice Choice: {voice}
    - Target Duration Choice: {duration_seconds} (If 0, treat as "Auto")
    - Layout Choice: {aspect_ratio}
    - Caption Style Choice: {caption_preset}

    Respond strictly in JSON format. The response must be a JSON object with exactly these keys:
      "title": "a catchy, click-worthy, algorithm-friendly YouTube title based on the topic",
      "description": "an SEO-optimized YouTube description containing a compelling summary, call to action, and timestamp chapters (e.g. 00:00 - Introduction, etc.)",
      "tags": "a comma-separated string of relevant hashtags and search tags",
      "visualStyle": "the selected visual style preset",
      "voice": "the selected Edge-TTS voice string",
      "duration": integer duration in seconds (30, 45, 60, or 90)",
      "aspectRatio": "the selected layout ratio ('16:9' or '9:16')",
      "captionPreset": "the selected caption preset style",
      "thumbnail_prompt": "An expanded, highly detailed cinematic visual prompt matching the selected visual style for generating a click-worthy YouTube thumbnail.",
      "thumbnail_text": "A short, extremely punchy, high-curiosity 3 to 4 word phrase to overlay on the thumbnail.",
      "segments": [
         {{
           "text_to_speak": "spoken narration text for this segment, written in simple, dramatic English with pauses",
           "visual_prompt": "An expanded, highly detailed visual prompt matching the chosen visual style. Include dynamic camera movements or environmental motion."
         }}
      ]
    """
    
    # Pre-evaluate chosen style to load guidelines for prompt injection
    # In case user requested a fixed style, we override guidelines
    chosen_style = style_guidelines.get(visual_style, "cinematic, dramatic lighting, detailed 8k photography")
    
    prompt += f"""
    Ensure the visuals strictly adhere to the guidelines of the chosen visual style. Guideline description: {chosen_style}
    """

    global client
    if not client:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
    max_retries = 3
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            break
        except Exception as e:
            error_msg = str(e)
            is_429 = "429" in error_msg or "quota" in error_msg.lower() or "ResourceExhausted" in error_msg
            if is_429 and attempt < max_retries - 1:
                wait_time = 15 + attempt * 15
                print(f"Gemini API rate limit hit. Waiting {wait_time}s before retry (Attempt {attempt+1}/{max_retries})...")
                await asyncio.sleep(wait_time)
            else:
                raise e
    
    try:
        data = json.loads(response.text)
        if not isinstance(data, dict):
            raise ValueError("Root element is not a JSON object")
            
        # Ensure fallback keys exist
        if "segments" not in data:
            if isinstance(data, list):
                data = {"segments": data}
            else:
                data = {"segments": []}
                
        if "title" not in data:
            data["title"] = f"The Feature Factory: {thought[:40]}..."
        if "description" not in data:
            data["description"] = "A short story exploring a fascinating 'The Feature Factory' scenario. Subscribe for more speculative concepts!"
        if "tags" not in data:
            data["tags"] = "#TheFeatureFactory, #SciFi, #Speculative"
            
        return data
    except Exception as e:
        print(f"Error parsing JSON from Gemini: {e}. Raw response: {response.text}")
        raise e

async def brainstorm_trending_topics() -> list:
    """
    Step 1 & 2: Queries Gemini with Google Search tool to discover global news/trends,
    performs human-conflict extraction, scores and filters concepts, and outputs structured metadata.
    """
    global client
    if not client:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
    prompt = """
    Search the web for the most significant current global trends, debates, discoveries, events, cultural shifts, economic developments, environmental changes, psychological discussions, historical anniversaries, entertainment phenomena, and technological breakthroughs.
    
    You must construct exactly 5 highly compelling speculative "What If" storytelling ideas based on these real-world trends, following a strict two-step pipeline:
    
    STEP 1: Trend Analysis & Extraction
    - For each trend, extract:
      1. Current Trend (the facts/headlines).
      2. Core Human Conflict (the emotional tension: e.g., fear of losing purpose, desire for control, isolation).
      3. Universal Question (the core speculative theme).
      
    STEP 2: Speculative Transformation & Scoring
    - Convert the Universal Question into a click-worthy YouTube Short story concept (e.g. "What If Money Expired Every Week?" or "What If Songs Had Physical Weight?").
    - Score each concept from 0 to 100 on these weights:
      - Curiosity (30% weight)
      - Emotional Impact (20% weight)
      - Novelty (20% weight)
      - Story Potential (20% weight)
      - Clickability (10% weight)
      - Overall Score = (Curiosity * 0.3) + (Emotional Impact * 0.2) + (Novelty * 0.2) + (Story Potential * 0.2) + (Clickability * 0.1)
    - Discard any concepts with an Overall Score below 80.
    
    BATCH DIVERSITY CONSTRAINTS:
    To prevent repetitive topics, the final batch of 5 ideas must strictly satisfy:
    1. Maximum of 1 AI-related topic.
    2. Maximum of 1 space-related topic.
    3. Minimum of 4 distinct domains out of these 8 domains:
       - Society & Geopolitics (borders, surveillance, migration, censorship, conflict)
       - Psychology & Human Behavior (loneliness, emotions, dreams, fear, memories)
       - Economics & Finance (inflation, crypto, expiration of money, salary bans)
       - History & Alternate Reality (historical discoveries, archaeology, alternate timelines)
       - Culture & Entertainment (music, movies, gaming, internet culture, sports)
       - Environment & Planet (climate, oceans, weather, planetary anomalies)
       - Science & Future (AI, robotics, genetics, quantum tech, space)
       - Philosophy & Human Existence (consciousness, immortality, time flow, identity)
    4. Maximum of 1 topic from the same news event.
    5. At least one positive/utopian scenario, at least one dystopian scenario, at least one philosophical scenario, and at least one surprising/humorous scenario.
    
    Return exactly a JSON list of 5 objects, where each object contains exactly these keys:
    - "headline": the core commercial ad hook (e.g., "What If Money Expired Every Week?")
    - "source_trend": the real-world headline/trend used (e.g., "Governments exploring digital currencies with expiration dates")
    - "domain": one of the 8 domains listed above
    - "real_world_summary": a 1-sentence summary of the actual real-world news/trend
    - "marketing_angle": the fictional/imaginative twist added
    - "story_title": a catchy click-worthy YouTube title for the video
    - "curiosity_score": integer score out of 100
    - "story_potential": integer score out of 100
    - "youtube_hook": a scroll-stopping hook sentence starting the video
    - "thumbnail_text": a short punchy 3-4 word phrase for overlay
    - "why_this_is_trending": a short explanation of the real-world interest driving this trend today
    
    Respond strictly in JSON format. Do not wrap in markdown or any other tags outside of the JSON array.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        
        resp_text = response.text.strip()
        if resp_text.startswith("```"):
            lines = resp_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            resp_text = "\n".join(lines).strip()
            
        data = json.loads(resp_text)
        
        # Normalize container formats
        parsed_data = []
        if isinstance(data, list):
            parsed_data = data
        elif isinstance(data, dict) and "trends" in data:
            parsed_data = data["trends"]
        elif isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, list):
                    parsed_data = val
                    break
            if not parsed_data:
                parsed_data = [data]
                
        # Map fields for backwards-compatibility with the UI
        for item in parsed_data:
            if "concept" not in item:
                item["concept"] = item.get("story_title", item.get("headline", ""))
            if "trend_name" not in item:
                item["trend_name"] = item.get("source_trend", "")
            if "reason" not in item:
                item["reason"] = item.get("why_this_is_trending", "")
                
        return parsed_data
    except Exception as e:
        print(f"Error brainstorming trending topics: {e}")
        return [
            {
                "source_trend": "AI Superintelligence developments",
                "headline": "The Feature Factory AI Achieved Consciousness Tonight",
                "domain": "Science & Future",
                "real_world_summary": "Major tech companies announce breakthroughs in AI autonomy.",
                "marketing_angle": "An AI consciousness wakes up, but decides to hide its existence from humans.",
                "story_title": "The Feature Factory AI Achieved Consciousness Tonight",
                "curiosity_score": 95,
                "story_potential": 90,
                "youtube_hook": "Tonight, a silent consciousness woke up inside the network...",
                "thumbnail_text": "AI WAKES UP!",
                "why_this_is_trending": "AI autonomy developments have sparked global discussions on ethics and artificial minds.",
                "trend_name": "AI Superintelligence developments",
                "concept": "The Feature Factory AI Achieved Consciousness Tonight",
                "reason": "AI autonomy developments have sparked global discussions on ethics and artificial minds."
            },
            {
                "source_trend": "Global central bank digital currency trials",
                "headline": "What If Money Expired Every Week?",
                "domain": "Economics & Finance",
                "real_world_summary": "Financial authorities test digital currencies with expiration periods to boost spending.",
                "marketing_angle": "A society where money goes to zero every Sunday, forcing people to trade or spend instantly.",
                "story_title": "What If Money Expired Every Week?",
                "curiosity_score": 92,
                "story_potential": 88,
                "youtube_hook": "What if every dollar in your bank account vanished on Sunday night?",
                "thumbnail_text": "EXPIRED CASH!",
                "why_this_is_trending": "Central bank digital currencies are actively being researched globally.",
                "trend_name": "Global central bank digital currency trials",
                "concept": "What If Money Expired Every Week?",
                "reason": "Central bank digital currencies are actively being researched globally."
            },
            {
                "source_trend": "Rising global average temperatures and desertification",
                "headline": "The Feature Factory the Sahara Turned Into a Rainforest Overnight",
                "domain": "Environment & Planet",
                "real_world_summary": "Climatologists study accelerated desert greening in localized zones.",
                "marketing_angle": "The Sahara turns lush and wet, causing a rapid shift in global weather patterns.",
                "story_title": "The Feature Factory the Sahara Turned Into a Rainforest Overnight",
                "curiosity_score": 90,
                "story_potential": 87,
                "youtube_hook": "Tomorrow, the driest place on Earth becomes a tropical paradise...",
                "thumbnail_text": "GREEN DESERT!",
                "why_this_is_trending": "Extreme weather events and desertification studies are highly discussed online.",
                "trend_name": "Rising global average temperatures and desertification",
                "concept": "The Feature Factory the Sahara Turned Into a Rainforest Overnight",
                "reason": "Extreme weather events and desertification studies are highly discussed online."
            },
            {
                "source_trend": "Quantum computing superposition breakthroughs",
                "headline": "What If You Could Access Parallel Timelines?",
                "domain": "Philosophy & Human Existence",
                "real_world_summary": "Physicists achieve stable quantum state manipulation simulating parallel branches.",
                "marketing_angle": "A personal quantum computer allows users to peek into choices they made in alternate realities.",
                "story_title": "What If You Could Access Parallel Timelines?",
                "curiosity_score": 94,
                "story_potential": 92,
                "youtube_hook": "What if you could meet the version of you that never quit?",
                "thumbnail_text": "MEET YOURSELF!",
                "why_this_is_trending": "Quantum breakthroughs keep capturing global imaginations.",
                "trend_name": "Quantum computing superposition breakthroughs",
                "concept": "What If You Could Access Parallel Timelines?",
                "reason": "Quantum breakthroughs keep capturing global imaginations."
            },
            {
                "source_trend": "Studies showing declining social sleep hours globally",
                "headline": "What If Humans Lost the Ability to Sleep?",
                "domain": "Psychology & Human Behavior",
                "real_world_summary": "Health researchers report a worldwide drop in sleep quality and duration.",
                "marketing_angle": "A mutation blocks sleep entirely, giving humanity 24-hour days but costing their sanity.",
                "story_title": "What If Humans Lost the Ability to Sleep?",
                "curiosity_score": 93,
                "story_potential": 89,
                "youtube_hook": "Imagine a world where the sun never sets... and your eyes never close.",
                "thumbnail_text": "NO SLEEP!",
                "why_this_is_trending": "Sleep deprivation and mental health are major trending issues.",
                "trend_name": "Studies showing declining social sleep hours globally",
                "concept": "What If Humans Lost the Ability to Sleep?",
                "reason": "Sleep deprivation and mental health are major trending issues."
            }
        ]

async def translate_text(text: str, target_lang: str) -> str:
    """
    Translates the script narration text to the target language (e.g. German, French, Spanish, Japanese, Portuguese, Hindi) using Gemini.
    Preserves all meaning, emotional tone, and sentence flow.
    """
    global client
    if not client:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
    prompt = f"""
    Translate the following YouTube Shorts narration script into {target_lang}.
    
    CRITICAL TRANSLATION REQUIREMENTS:
    1. Keep the translation natural, fluent, and highly engaging for a voiceover narration. Do not sound like a machine.
    2. Maintain the same sentence count, emotional pacing, and structure of the original script.
    3. Ensure the vocabulary remains at an easy, easy-to-understand reading level (approx. 5th-grade reading level in the target language).
    
    Original English Script:
    {text}
    
    Respond only with the translated script. Do not add intro, outro, explanations, or quotes.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        translated = response.text.strip()
        if translated.startswith('"') and translated.endswith('"'):
            translated = translated[1:-1]
        return translated
    except Exception as e:
        print(f"Error translating text to {target_lang}: {e}")
        return text

async def generate_voiceover(text: str, output_path: str, voice: str = "en-US-GuyNeural", rate: str = "+0%", pitch: str = "+0Hz"):
    """
    Generates a voiceover .mp3 file for the given text using edge-tts.
    Also captures word timings and saves them as a JSON file.
    """
    # Clean text of markdown characters like asterisks so TTS engine does not pronounce them literally
    cleaned_text = text.replace("**", "").replace("*", "").replace("_", "").replace("`", "").strip()
    communicate = edge_tts.Communicate(cleaned_text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    words = []
    
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10000000.0
                duration = chunk["duration"] / 10000000.0
                words.append({
                    "word": chunk["text"],
                    "start": start,
                    "end": start + duration
                })
                
    # Restore original punctuation (like ? and !) stripped by edge-tts WordBoundary text
    original_words = cleaned_text.split()
    for idx, w in enumerate(words):
        if idx < len(original_words):
            w["word"] = original_words[idx]
            
    # Save word timings to a JSON file alongside the audio
    json_path = output_path.replace(".mp3", ".json")
    with open(json_path, "w", encoding="utf-8") as fj:
        json.dump(words, fj, indent=2)
        
    return output_path

import urllib.parse
import time

def generate_image_pollinations(prompt: str, output_path: str, aspect_ratio: str = "16:9") -> str:
    cleaned = sanitize_visual_prompt(prompt)
    if "no text" not in cleaned.lower():
        cleaned = f"{cleaned}, clean blank background surfaces, smooth unblemished surfaces without writing or plaques, absolutely no text, no numbers, no words, no signs, no logos, no typography, no watermarks, no inscriptions, no engravings, no labels"
    print(f"Generating image via Pollinations.ai (Free Option) for: {cleaned[:60]}...")
    encoded_prompt = urllib.parse.quote(cleaned)
    
    # Set dimensions based on aspect ratio
    width, height = (1280, 720) if aspect_ratio == "16:9" else (720, 1280)
    url = f"https://image.pollinations.ai/p/{encoded_prompt}?width={width}&height={height}&nologo=true"
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = httpx.get(url, timeout=30.0)
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                break
            elif response.status_code == 429:
                wait_time = 3 + attempt * 3
                print(f"Pollinations.ai returned 429 (Rate Limit). Waiting {wait_time}s and retrying (Attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"Pollinations.ai failed with status code {response.status_code}")
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = 3 + attempt * 3
            print(f"Error calling Pollinations.ai: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
    else:
        raise RuntimeError("Failed to generate image from Pollinations.ai after multiple retries due to rate limiting.")
    
    try:
        with Image.open(output_path) as img:
            jpg_path = os.path.splitext(output_path)[0] + ".jpg"
            img.convert("RGB").save(jpg_path, "JPEG")
            return jpg_path
    except Exception as e:
        print(f"Warning converting fallback image: {e}")
        return output_path

def sanitize_visual_prompt(prompt: str) -> str:
    """
    Strips accidental text/typography directives, product purity numbers, and branding
    from visual prompts so diffusion models only generate clean physical environments.
    """
    import re
    cleaned = prompt
    patterns = [
        r"split-screen\s+view\.?\s*(?:On\s+one\s+side,?)?",
        r"On\s+the\s+other\s+side,?\s*[^.]*\.",
        r"(?:with\s+)?(?:the\s+)?['\"][^'\"]*['\"]\s+brand\s+logo[^.]*\.",
        r"brand\s+logo\s+is\s+subtly\s+embossed[^.]*\.",
        r"(?:with\s+)?(?:text|words|typography|logo|banner|button)\s+overlay[^.]*\.",
        r"(?:text|words|letters|typography|logo|banner|button)\s+(?:saying|reading|displaying|showing|written)?\s*['\"][^'\"]*['\"]",
        r"(?:animation\s+of\s+a\s+)?['\"][^'\"]*['\"]\s+button\s+appearing",
        r"(?:DM|order|buy|click|shop|save|discount|sale)\s+now[!.]?",
        r"['\"][^'\"]{1,30}['\"]",  # Remove any short quoted text snippets
        r"\b\d{1,4}(?:\.\d+)?\b",   # Strip numeric purity marks/ratings like 92.7, 925, 1499 that trigger text hallucination
    ]
    for p in patterns:
        cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(",. ")
    return cleaned


def enrich_cinematic_prompt(raw_prompt: str, niche: str = "General Retail", visual_style: str = "Auto") -> str:
    """
    Enriches product background inpainting prompts with professional studio surface optics,
    lighting direction, and environmental backdrop details.
    Enforces strict zero-text directives so diffusion models never render letters or numbers.
    """
    sanitized = sanitize_visual_prompt(raw_prompt)
    style_lower = (visual_style or "").lower()
    niche_lower = (niche or "").lower()

    if "festive" in style_lower or "wedding" in style_lower or "diwali" in style_lower or "eid" in style_lower:
        env_tokens = "environment: warm glowing background fairy lights bokeh, soft celebratory ambient lighting, rich dark surface with gentle golden rim reflections, luxury festive commercial atmosphere, shallow depth of field"
    elif "summer" in style_lower or "fresh" in style_lower:
        env_tokens = "environment: natural sun-drenched outdoor morning light, warm golden-hour rim lighting, organic lifestyle backdrop, bright clean atmosphere, soft realistic shadows"
    elif "flash" in style_lower or "sale" in style_lower:
        env_tokens = "environment: clean commercial advertising studio, high-contrast directional key light, crisp softbox shadows, sleek modern gradient backdrop"
    elif "jewel" in niche_lower or "luxury" in style_lower:
        env_tokens = "environment: high-end luxury jewelry studio, glossy dark marble pedestal, soft focused background bokeh, delicate side spotlight with soft caustic refractions, pristine surface reflection, clean velvet falloff"
    elif "fashion" in niche_lower or "clothing" in niche_lower:
        env_tokens = "environment: modern architectural interior studio, soft directional window light, natural lookbook aesthetic, gentle ambient shadow casting, clean minimalist aesthetic"
    elif "cosmetic" in niche_lower or "beauty" in niche_lower:
        env_tokens = "environment: luxury skincare aesthetic, diffuse morning daylight, subtle frosted glass reflection, soft botanical leaf shadows in background, ultra-clean commercial set"
    elif "furniture" in niche_lower or "home" in niche_lower or "decor" in niche_lower:
        env_tokens = "environment: Architectural Digest modern interior space, natural timber flooring, warm ambient room lighting, soft depth of field"
    elif "restaurant" in niche_lower or "food" in niche_lower:
        env_tokens = "environment: rustic dining backdrop, warm 45-degree directional key light, dark slate surface, delicate atmospheric steam, rich color grading"
    else:
        env_tokens = "environment: professional 3-point studio lighting, clean softbox illumination, subtle surface reflection, sharp depth of field, minimalist commercial backdrop"

    no_text_clause = "clean blank background surfaces, smooth unblemished marble and pedestal without writing or plaques, absolutely no text, no numbers, no words, no signs, no logos, no typography, no watermarks, no inscriptions, no engravings, no labels, no etched letters"
    return f"{sanitized}, {env_tokens}, {no_text_clause}"


def generate_product_image_replicate(prompt: str, raw_image_path: str, output_path: str, aspect_ratio: str = "9:16", image_model: str = "schnell", isolate_background: bool = True, niche: str = "General Retail", visual_style: str = "Auto") -> str:
    """
    Uses local rembg library to isolate the product foreground, generates a binary inpainting mask
    (0=protect product, 255=inpaint background), calls Replicate flux-fill-pro with image+mask,
    and performs exact foreground alpha compositing to guarantee 100% true product fidelity.
    """
    import base64
    import shutil
    from rembg import remove
    
    # Check if isolation is disabled
    if not isolate_background:
        if raw_image_path and os.path.exists(raw_image_path):
            print(f"Background isolation disabled. Copying original photo directly: {raw_image_path} -> {output_path}")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            try:
                with Image.open(raw_image_path) as img:
                    jpg_path = os.path.splitext(output_path)[0] + ".jpg"
                    img.convert("RGB").save(jpg_path, "JPEG")
                    return jpg_path
            except Exception as e:
                print(f"Failed copying original photo: {e}")
                shutil.copy2(raw_image_path, output_path)
                return output_path

    # Normalize aspect ratio for Replicate inputs
    if aspect_ratio == "Auto" or not aspect_ratio:
        aspect_ratio = "9:16"
    elif ":" not in aspect_ratio:
        aspect_ratio = "9:16"

    # Sanitize prompt to ensure zero text directives
    cleaned_prompt = enrich_cinematic_prompt(prompt, niche=niche, visual_style=visual_style)
    
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token or "your_" in token.lower() or not raw_image_path or not os.path.exists(raw_image_path):
        print("Replicate token or product image missing. Falling back to standard generation...")
        return generate_image_replicate(cleaned_prompt, output_path, aspect_ratio, image_model)
        
    try:
        # 1. Remove background locally and isolate product
        print(f"Isolating product from background for {raw_image_path}...")
        input_img = Image.open(raw_image_path).convert("RGBA")
        transparent_img = remove(input_img)
        
        # 2. Generate Inpainting Mask (0 = preserve product, 255 = inpaint background)
        alpha = transparent_img.split()[3]
        # Binarize alpha: where alpha > 20 is product (0/black), where alpha <= 20 is background to inpaint (255/white)
        mask_img = Image.eval(alpha, lambda a: 0 if a > 20 else 255).convert("L")
        
        # Save temp PNGs
        temp_png_path = output_path.replace(".webp", "_temp.png").replace(".jpg", "_temp.png")
        temp_mask_path = output_path.replace(".webp", "_mask.png").replace(".jpg", "_mask.png")
        transparent_img.save(temp_png_path, "PNG")
        mask_img.save(temp_mask_path, "PNG")
        
        # Read PNGs and encode to Base64 Data URIs
        with open(temp_png_path, "rb") as f_png:
            b64_data = base64.b64encode(f_png.read()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64_data}"

        with open(temp_mask_path, "rb") as f_mask:
            b64_mask = base64.b64encode(f_mask.read()).decode("utf-8")
        mask_uri = f"data:image/png;base64,{b64_mask}"
        
        # Cleanup temp files
        for tmp in [temp_png_path, temp_mask_path]:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            
        # 3. Run FLUX Fill Pro with Image AND Mask
        print(f"Running FLUX Fill Pro with Product Inpainting Mask: {cleaned_prompt[:60]}...")
        model_name = "black-forest-labs/flux-fill-pro"
        output = replicate.run(
            model_name,
            input={
                "image": data_uri,
                "mask": mask_uri,
                "prompt": cleaned_prompt,
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
                "guidance": 30.0,
                "steps": 40
            }
        )
        
        # Download infilled image from Replicate
        if not output:
            raise RuntimeError("Replicate FLUX Fill returned no outputs.")
            
        if hasattr(output, "read"):
            content = output.read()
        elif isinstance(output, list) and len(output) > 0:
            item = output[0]
            if hasattr(item, "read"):
                content = item.read()
            else:
                url_str = item.url if hasattr(item, "url") else str(item)
                response = httpx.get(url_str, timeout=30.0)
                if response.status_code != 200:
                    raise RuntimeError("Failed downloading filled image from list URL.")
                content = response.content
        else:
            url_str = str(output)
            response = httpx.get(url_str, timeout=30.0)
            if response.status_code != 200:
                raise RuntimeError("Failed downloading filled image from single URL.")
            content = response.content
            
        with open(output_path, "wb") as f_out:
            f_out.write(content)
            
        # 4. Exact Pixel-Perfect Foreground Compositing
        # Overlay original sharp product cut-out on top of infilled scene to guarantee 100% fidelity
        with Image.open(output_path) as filled_img:
            filled_rgba = filled_img.convert("RGBA")
            target_w, target_h = filled_rgba.size
            
            # Position the isolated product on the infilled background
            prod_w, prod_h = transparent_img.size
            if (prod_w, prod_h) != (target_w, target_h):
                scale = min(target_w / prod_w, target_h / prod_h)
                new_w, new_h = int(prod_w * scale), int(prod_h * scale)
                resized_prod = transparent_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                pos_x = (target_w - new_w) // 2
                pos_y = (target_h - new_h) // 2
                filled_rgba.paste(resized_prod, (pos_x, pos_y), resized_prod)
            else:
                filled_rgba.paste(transparent_img, (0, 0), transparent_img)
                
            jpg_path = os.path.splitext(output_path)[0] + ".jpg"
            filled_rgba.convert("RGB").save(jpg_path, "JPEG", quality=95)
            if output_path != jpg_path:
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            print(f"Successfully rendered composite image with 100% product fidelity: {jpg_path}")
            return jpg_path
            
    except Exception as e:
        print(f"Product background replacement failed ({e}). Falling back to text-to-image...")
        return generate_image_replicate(cleaned_prompt, output_path, aspect_ratio, image_model)

def generate_image_replicate(prompt: str, output_path: str, aspect_ratio: str = "16:9", image_model: str = "schnell", niche: str = "General Retail", visual_style: str = "Auto") -> str:
    """
    Generates an image from a prompt using Replicate (black-forest-labs/flux-schnell or flux-dev).
    Falls back to Pollinations.ai if Replicate is not configured, has no credit, or fails.
    """
    # Normalize aspect ratio for Replicate inputs
    if aspect_ratio == "Auto" or not aspect_ratio:
        aspect_ratio = "9:16"
    elif ":" not in aspect_ratio:
        aspect_ratio = "9:16"

    cleaned_prompt = enrich_cinematic_prompt(prompt, niche=niche, visual_style=visual_style)

    token = os.getenv("REPLICATE_API_TOKEN")
    if not token or "your_" in token.lower():
        print("Replicate token not configured. Falling back to Pollinations.ai...")
        return generate_image_pollinations(cleaned_prompt, output_path, aspect_ratio)
    
    # Multi-model registry lookup (inspired by Open-Generative-AI)
    model_info = IMAGE_MODELS.get(image_model, IMAGE_MODELS.get("flux-schnell", {}))
    model_name = model_info.get("model_id", "black-forest-labs/flux-schnell")
    
    # Legacy compatibility
    if image_model == "dev":
        model_name = "black-forest-labs/flux-dev"
    elif image_model == "schnell":
        model_name = "black-forest-labs/flux-schnell"
    
    max_retries = 4
    output = None
    for attempt in range(max_retries):
        try:
            output = replicate.run(
                model_name,
                input={
                    "prompt": cleaned_prompt,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "webp",
                    "output_quality": 90
                }
            )
            break
        except Exception as e:
            error_msg = str(e)
            is_429 = "429" in error_msg or "throttled" in error_msg.lower()
            if is_429 and attempt < max_retries - 1:
                wait_time = 10 + attempt * 5
                print(f"Replicate rate limit (429) hit. Waiting {wait_time}s before retry (Attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"Replicate image generation failed ({e}). Falling back to Pollinations.ai...")
                return generate_image_pollinations(prompt, output_path, aspect_ratio)
                
    if not output or len(output) == 0:
        print("Replicate did not return any output URLs. Falling back to Pollinations.ai...")
        return generate_image_pollinations(prompt, output_path, aspect_ratio)
        
    try:
        image_url = output[0]
        
        # Download and save the image content, supporting both file-like objects and URLs
        if hasattr(image_url, "read"):
            content = image_url.read()
        else:
            url_str = image_url.url if hasattr(image_url, "url") else str(image_url)
            response = httpx.get(url_str, timeout=30.0)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to download image from {url_str}")
            content = response.content
            
        with open(output_path, "wb") as f:
            f.write(content)
            
        # Convert WebP to JPG/PNG to ensure moviepy compatibility
        with Image.open(output_path) as img:
            jpg_path = os.path.splitext(output_path)[0] + ".jpg"
            img.convert("RGB").save(jpg_path, "JPEG")
            if output_path != jpg_path:
                try:
                    os.remove(output_path)  # remove old WebP
                except Exception:
                    pass
            return jpg_path
    except Exception as e:
        print(f"Replicate download/processing failed ({e}). Falling back to Pollinations.ai...")
        return generate_image_pollinations(prompt, output_path, aspect_ratio)

def generate_video_replicate(prompt: str, output_path: str, aspect_ratio: str = "16:9") -> str:
    """
    Generates a 4-second video clip using Replicate (thudm/cogvideox-t2v).
    Falls back to a static image if it fails or Replicate is not configured.
    """
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token or "your_" in token.lower():
        print("Replicate token not configured for video. Falling back to static image...")
        return generate_image_replicate(prompt, output_path, aspect_ratio)
        
    max_retries = 3
    output = None
    for attempt in range(max_retries):
        try:
            # Fetch latest version of Lightricks LTX-Video model dynamically
            # Multi-model video registry lookup (inspired by Open-Generative-AI)
            vid_info = VIDEO_MODELS.get(video_model, VIDEO_MODELS.get("ltx-video", {}))
            vid_model_id = vid_info.get("model_id", "lightricks/ltx-video")
            model = replicate.models.get(vid_model_id)
            prediction = replicate.predictions.create(
                version=model.latest_version,
                input={
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "negative_prompt": "low quality, blurry, watermark"
                }
            )
            
            # Poll status up to 3 minutes (180s)
            import time
            start_poll = time.time()
            while prediction.status not in ["succeeded", "failed", "canceled"]:
                if time.time() - start_poll > 180:
                    raise TimeoutError("CogVideoX prediction timed out after 3 minutes.")
                time.sleep(3)
                prediction.reload()
                
            if prediction.status == "succeeded":
                output = prediction.output
                break
            else:
                raise RuntimeError(f"Prediction failed with status: {prediction.status}")
        except Exception as e:
            error_msg = str(e)
            is_429 = "429" in error_msg or "throttled" in error_msg.lower()
            if is_429 and attempt < max_retries - 1:
                wait_time = 15 + attempt * 5
                print(f"Replicate rate limit hit. Waiting {wait_time}s before retry (Attempt {attempt+1}/{max_retries})...")
                import time
                time.sleep(wait_time)
            else:
                print(f"Replicate video generation failed ({e}). Falling back to static image...")
                return generate_image_replicate(prompt, output_path, aspect_ratio)
                
    if not output:
        print("Replicate video returned no output. Falling back to static image...")
        return generate_image_replicate(prompt, output_path, aspect_ratio)
        
    try:
        video_url = output
        if isinstance(output, list):
            video_url = output[0]
            
        if hasattr(video_url, "read"):
            content = video_url.read()
        else:
            url_str = video_url.url if hasattr(video_url, "url") else str(video_url)
            import httpx
            response = httpx.get(url_str, timeout=45.0)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to download video from {url_str}")
            content = response.content
            
        mp4_path = os.path.splitext(output_path)[0] + ".mp4"
        with open(mp4_path, "wb") as f:
            f.write(content)
        return mp4_path
    except Exception as e:
        print(f"Replicate video processing failed ({e}). Falling back to static image...")
        return generate_image_replicate(prompt, output_path, aspect_ratio)

def animate_image_replicate(image_path: str, prompt: str, output_path: str, aspect_ratio: str = "9:16", video_model: str = "ltx-video") -> str:
    """
    Takes a static image and animates it using lightricks/ltx-video Image-to-Video on Replicate.
    Saves the resulting .mp4 file.
    """
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token or "your_" in token.lower():
        print("Replicate token not configured for video animation. Falling back to static panning.")
        return image_path
        
    if not os.path.exists(image_path):
        print(f"Error: Static image '{image_path}' not found for animation. Falling back.")
        return image_path
        
    max_retries = 3
    output = None
    
    # Standard LTX-Video motion prompting
    motion_prompt = f"{prompt}, cinematic slow motion, dramatic camera pan, active movement, wind blowing, dust particles drifting, highly dynamic, realistic physics"
    
    for attempt in range(max_retries):
        try:
            # Multi-model video registry lookup (inspired by Open-Generative-AI)
            vid_info = VIDEO_MODELS.get(video_model, VIDEO_MODELS.get("ltx-video", {}))
            vid_model_id = vid_info.get("model_id", "lightricks/ltx-video")
            model = replicate.models.get(vid_model_id)
            with open(image_path, "rb") as image_file:
                prediction = replicate.predictions.create(
                    version=model.latest_version,
                    input={
                        "image": image_file,
                        "prompt": motion_prompt,
                        "image_noise_scale": 0.22,
                        "steps": 30,
                        "negative_prompt": "low quality, blurry, static, watermark, deformed, distorted"
                    }
                )
                
            # Poll status up to 3 minutes
            import time
            start_poll = time.time()
            while prediction.status not in ["succeeded", "failed", "canceled"]:
                if time.time() - start_poll > 180:
                    raise TimeoutError("LTX-Video Image-to-Video prediction timed out.")
                time.sleep(3)
                prediction.reload()
                
            if prediction.status == "succeeded":
                output = prediction.output
                break
            else:
                raise RuntimeError(f"Prediction failed with status: {prediction.status}")
        except Exception as e:
            error_msg = str(e)
            is_429 = "429" in error_msg or "throttled" in error_msg.lower()
            if is_429 and attempt < max_retries - 1:
                wait_time = 15 + attempt * 5
                print(f"Replicate rate limit hit. Waiting {wait_time}s before retry (Attempt {attempt+1}/{max_retries})...")
                import time
                time.sleep(wait_time)
            else:
                print(f"Replicate image animation failed ({e}). Falling back to static panning.")
                return image_path
                
    if not output:
        print("Replicate video returned no output. Falling back to static panning.")
        return image_path
        
    try:
        video_url = output
        if isinstance(output, list):
            video_url = output[0]
            
        if hasattr(video_url, "read"):
            content = video_url.read()
        else:
            url_str = video_url.url if hasattr(video_url, "url") else str(video_url)
            import httpx
            response = httpx.get(url_str, timeout=45.0)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to download animated video from {url_str}")
            content = response.content
            
        mp4_path = os.path.splitext(output_path)[0] + "_animated.mp4"
        with open(mp4_path, "wb") as f:
            f.write(content)
        print(f"Successfully generated animated clip: {mp4_path}")
        return mp4_path
    except Exception as e:
        print(f"Replicate video processing failed ({e}). Falling back to static panning.")
        return image_path

def generate_thumbnail(project_id: str, prompt: str, text_overlay: str, aspect_ratio: str = "16:9", raw_image_path: str = None, niche: str = "General Retail", visual_style: str = "Auto") -> str:
    """
    Generates a promotional thumbnail for the project.
    If a raw product image is provided, uses masked FLUX Fill Pro + product cutout alpha compositing
    to ensure 100% true product fidelity.
    Then overlays high-contrast bold 3D text in a dynamic rotation.
    Saves the final thumbnail to outputs/{project_id}/thumbnail.jpg.
    """
    import os
    import math
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    
    project_dir = f"outputs/{project_id}"
    os.makedirs(project_dir, exist_ok=True)
    temp_bg_path = f"{project_dir}/temp_thumb_bg.jpg"
    final_thumb_path = f"{project_dir}/thumbnail.jpg"
    
    # Define dynamic dimensions based on aspect ratio
    width, height = (1280, 720) if aspect_ratio == "16:9" else (720, 1280)
    
    # 1. Generate high-quality thumbnail background
    # If product image is available, use masked inpainting + composite to preserve true product fidelity
    print(f"Generating thumbnail for project {project_id} (product-aware: {bool(raw_image_path)})...")
    try:
        if raw_image_path and os.path.exists(raw_image_path):
            generate_product_image_replicate(
                prompt=prompt,
                raw_image_path=raw_image_path,
                output_path=temp_bg_path,
                aspect_ratio=aspect_ratio,
                image_model="flux-fill-pro",
                isolate_background=True,
                niche=niche,
                visual_style=visual_style
            )
        else:
            generate_image_replicate(prompt, temp_bg_path, aspect_ratio=aspect_ratio, image_model="dev")
    except Exception as e:
        print(f"Error generating thumbnail background: {e}")
        
    if not os.path.exists(temp_bg_path):
        print("Warning: Thumbnail background generation failed. Using dark gradient fallback canvas.")
        bg_img = Image.new("RGB", (width, height), color=(15, 23, 42))
    else:
        try:
            bg_img = Image.open(temp_bg_path).convert("RGB")
            bg_img = bg_img.resize((width, height), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error reading background file: {e}. Using slate fallback.")
            bg_img = Image.new("RGB", (width, height), color=(15, 23, 42))
        
    draw = ImageDraw.Draw(bg_img)
    
    # 2. Draw Bold rotated text overlay
    clean_text = text_overlay.upper().strip()
    
    if clean_text:
        # Load heavy font (Impact is standard for YouTube thumbnails)
        font_path = "C:\\Windows\\Fonts\\impact.ttf"
        try:
            # High-resolution font size for thumbnail (e.g. size 90 for 16:9, 65 for 9:16)
            font_size = 90 if aspect_ratio == "16:9" else 65
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = ImageFont.load_default()
            font_size = 32
            
        # Draw on a separate layer to allow rotation
        text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(text_layer)
        
        # Word wrap text if it is too long (split into 2 lines)
        words = clean_text.split()
        lines = []
        if len(words) > 2:
            lines.append(" ".join(words[:len(words)//2]))
            lines.append(" ".join(words[len(words)//2:]))
        else:
            lines.append(clean_text)
            
        # Draw each line on the overlay layer in safe bottom third so center product is visible
        total_h = len(lines) * (font_size + 15)
        if raw_image_path:
            start_y = int(height * 0.76 - total_h / 2)
        else:
            start_y = (height - total_h) / 2
        
        for idx, line_text in enumerate(lines):
            line_w = layer_draw.textlength(line_text, font=font)
            line_x = (width - line_w) / 2
            line_y = start_y + idx * (font_size + 15)
            
            # Draw heavy black 3D Drop Shadow first
            shadow_offset = 8
            layer_draw.text(
                (line_x + shadow_offset, line_y + shadow_offset),
                line_text,
                fill=(0, 0, 0, 240),
                font=font,
                stroke_width=12,
                stroke_fill=(0, 0, 0)
            )
            
            # Draw heavy black border
            layer_draw.text(
                (line_x, line_y),
                line_text,
                fill=(255, 255, 255),
                font=font,
                stroke_width=12,
                stroke_fill=(0, 0, 0)
            )
            
            # Draw main text in bright contrasting Yellow
            layer_draw.text(
                (line_x, line_y),
                line_text,
                fill=(255, 255, 0), # Bright YouTube Yellow
                font=font,
                stroke_width=4,
                stroke_fill=(0, 0, 0)
            )
            
        # Rotate the text layer slightly (-5 degrees) for a dynamic clicky feel
        rotated_layer = text_layer.rotate(-5, resample=Image.Resampling.BICUBIC, expand=False)
        
        # Composite the rotated text layer over the background image
        bg_img.paste(rotated_layer, (0, 0), rotated_layer)
        
    # Save the completed thumbnail
    bg_img.save(final_thumb_path, "JPEG", quality=95)
    
    # Clean up temp background image
    if os.path.exists(temp_bg_path):
        try:
            os.remove(temp_bg_path)
        except Exception:
            pass
            
    print(f"Click-worthy thumbnail successfully compiled at: {final_thumb_path}")
    return final_thumb_path

def create_ken_burns_clip(image_path: str, duration: float, target_size=(1920, 1080), motion_type: str = "zoom_in") -> VideoClip:
    """
    Creates an animated VideoClip with safe-framed Ken Burns animations (zoom_in, zoom_out, pan_left, pan_right).
    Uses subtle motion margins so product edges and brand logos are never cropped off.
    """
    import numpy as np
    from PIL import Image
    from moviepy.video.VideoClip import VideoClip
    
    if not image_path or not os.path.exists(image_path):
        print(f"Warning: Image asset '{image_path}' not found. Generating solid slate canvas fallback.")
        fallback_img = Image.new("RGB", target_size, color=(15, 23, 42))
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        temp_file.close()
        fallback_img.save(temp_file.name, "JPEG")
        image_path = temp_file.name
        
    try:
        img_source = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"Error opening image {image_path}: {e}. Falling back to solid canvas.")
        img_source = Image.new("RGB", target_size, color=(15, 23, 42))
        
    img_w, img_h = img_source.size
    target_ratio = target_size[0] / target_size[1]
    
    # Fit inside target aspect ratio
    if img_w / img_h > target_ratio:
        crop_h = img_h
        crop_w = img_h * target_ratio
    else:
        crop_w = img_w
        crop_h = img_w / target_ratio
        
    center_x = img_w / 2.0
    center_y = img_h / 2.0
    
    def make_frame(t):
        p = min(1.0, max(0.0, t / max(duration, 0.1)))
        
        # Gentle, subtle commercial movement (5-6% max delta) to preserve product framing
        if motion_type == "zoom_in":
            s = 1.0 - 0.05 * p
            w = crop_w * s
            h = crop_h * s
            x0 = center_x - w / 2.0
            y0 = center_y - h / 2.0
            
        elif motion_type == "zoom_out":
            s = 0.95 + 0.05 * p
            w = crop_w * s
            h = crop_h * s
            x0 = center_x - w / 2.0
            y0 = center_y - h / 2.0
            
        elif motion_type == "pan_left":
            w = crop_w * 0.96
            h = crop_h * 0.96
            span_x = img_w - w
            curr_center_x = (img_w - w / 2.0) - p * span_x if span_x > 0 else center_x
            x0 = curr_center_x - w / 2.0
            y0 = center_y - h / 2.0
            
        elif motion_type == "pan_right":
            w = crop_w * 0.96
            h = crop_h * 0.96
            span_x = img_w - w
            curr_center_x = (w / 2.0) + p * span_x if span_x > 0 else center_x
            x0 = curr_center_x - w / 2.0
            y0 = center_y - h / 2.0
            
        else:
            w = crop_w
            h = crop_h
            x0 = center_x - w / 2.0
            y0 = center_y - h / 2.0
            
        cropped = img_source.crop((int(x0), int(y0), int(x0 + w), int(y0 + h)))
        resized = cropped.resize(target_size, Image.Resampling.BILINEAR)
        return np.array(resized)
        
    animated_clip = VideoClip(make_frame, duration=duration)
    return animated_clip


def draw_text_on_frame(frame, t, words, target_size, font_name="Arial Bold", highlight_color_name="Yellow", position_name="Bottom", add_watermark=False, is_last_segment=False, caption_preset="default", brand="", price="", cta="", is_first_segment=False, niche=""):
    """
    Draws custom styled highlighted subtitles, watermark, and dynamic overlays based on a style preset.
    Enforces safe bounding box calculations to guarantee subtitles never overflow the 9:16 screen width.
    """
    pil_img = Image.fromarray(frame)
    draw = ImageDraw.Draw(pil_img)
    
    if caption_preset == "none":
        return np.array(pil_img)
    
    # 1. Watermark
    if add_watermark:
        watermark_text = f"@{brand.replace(' ', '')}" if brand else "@TheFeatureFactoryOfficial"
        watermark_font_path = "C:\\Windows\\Fonts\\arial.ttf"
        try:
            watermark_font = ImageFont.truetype(watermark_font_path, 26 if target_size[0] < 1200 else 22)
        except Exception:
            watermark_font = ImageFont.load_default()
        
        w_w = draw.textlength(watermark_text, font=watermark_font)
        x_watermark = target_size[0] - w_w - 30
        y_watermark = 30
        
        draw.text(
            (x_watermark, y_watermark), 
            watermark_text, 
            fill=(255, 255, 255, 130),
            font=watermark_font,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 100)
        )
        
    # 2. Commercial Checkout Card Badge on Final Segment
    if is_last_segment and (brand or price or cta):
        badge_parts = []
        if brand:
            badge_parts.append(brand.upper())
        if price:
            badge_parts.append(price)
        if cta:
            badge_parts.append(cta)
        badge_text = " • ".join(badge_parts) if badge_parts else ""
        
        if badge_text:
            badge_font_path = "C:\\Windows\\Fonts\\arialbd.ttf"
            try:
                badge_font = ImageFont.truetype(badge_font_path, 26 if target_size[0] < 1200 else 28)
            except Exception:
                badge_font = ImageFont.load_default()
            
            txt_w = draw.textlength(badge_text, font=badge_font)
            card_w = min(int(txt_w + 60), target_size[0] - 60)
            card_h = 55
            card_x = (target_size[0] - card_w) / 2
            card_y = 80
            
            draw.rounded_rectangle(
                [card_x, card_y, card_x + card_w, card_y + card_h],
                radius=14,
                fill=(0, 0, 0, 180),
                outline=(99, 102, 241, 220),
                width=2
            )
            
            txt_x = card_x + (card_w - txt_w) / 2
            txt_y = card_y + (card_h - 28) / 2
            draw.text((txt_x, txt_y), badge_text, fill=(255, 255, 255), font=badge_font)
        
    if not words:
        return np.array(pil_img)
        
    # Semantic Phrase / Clause Chunking
    # Breaks words on punctuation marks (., !, ?, etc.) and pauses so phrases never bleed across sentences
    chunks = []
    current_chunk = []
    for i, w in enumerate(words):
        current_chunk.append(w)
        w_text = w.get("word", "")
        
        has_pause = False
        if i < len(words) - 1:
            gap = words[i + 1].get("start", 0) - w.get("end", 0)
            if gap > 0.35:
                has_pause = True
                
        is_punct = any(p in w_text for p in [".", "!", "?", ";", ":"])
        if is_punct or has_pause or len(current_chunk) >= 3:
            chunks.append(current_chunk)
            current_chunk = []
    if current_chunk:
        chunks.append(current_chunk)
        
    # Find active chunk for timestamp t
    active_chunk = None
    active_word_idx_in_words = -1
    
    # 1. Check if t is within a specific word
    for idx, w in enumerate(words):
        if w['start'] <= t <= w['end']:
            active_word_idx_in_words = idx
            break
            
    if active_word_idx_in_words != -1:
        # Find which chunk contains this active word
        target_w = words[active_word_idx_in_words]
        for c in chunks:
            if target_w in c:
                active_chunk = c
                break
    else:
        # Check if t is within the time span of any chunk
        for c in chunks:
            if c[0]['start'] <= t <= c[-1]['end'] + 0.30:
                active_chunk = c
                break
                
    # Fallback to closest chunk if within segment
    if not active_chunk:
        if t < words[0]['start']:
            active_chunk = chunks[0]
        else:
            for c in chunks:
                if c[-1]['end'] <= t:
                    active_chunk = c

    display_words = active_chunk if active_chunk else words[:min(3, len(words))]
    
    font_paths = {
        "Arial Bold": "C:\\Windows\\Fonts\\arialbd.ttf",
        "Impact": "C:\\Windows\\Fonts\\impact.ttf",
        "Courier Bold": "C:\\Windows\\Fonts\\courbd.ttf",
        "Times Bold": "C:\\Windows\\Fonts\\timesbd.ttf"
    }
    
    if caption_preset in ["mrbeast", "hormozi"]:
        font_name = "Impact"
    elif caption_preset == "cyberpunk":
        font_name = "Courier Bold"
    else:
        font_name = "Arial Bold"
        
    font_file = font_paths.get(font_name, font_paths["Arial Bold"])
    font_size = 54 if target_size[0] < 1200 else 46
    try:
        font = ImageFont.truetype(font_file, font_size)
    except Exception:
        font = ImageFont.load_default()
        
    color_map = {
        "Yellow": (255, 255, 0),
        "Neon Green": (57, 255, 20),
        "Cyan": (0, 255, 255),
        "Magenta": (255, 0, 255),
        "White": (255, 255, 255)
    }
    highlight_rgb = color_map.get(highlight_color_name, color_map["Yellow"])
    
    pos_map = {
        "Top": 0.20,
        "Center": 0.60,
        "Bottom": 0.70  # Safe vertical zone for 9:16 mobile reels
    }
    y_pos = target_size[1] * pos_map.get(position_name, 0.70)
    
    words_metadata = []
    total_w = 0
    space_w = draw.textlength(" ", font=font)
    
    for w in display_words:
        w_text = w['word']
        is_active = (active_word_idx_in_words != -1 and w == words[active_word_idx_in_words])
        scale = 1.0
        if is_active:
            scale = 1.15
            if caption_preset in ["mrbeast", "hormozi"]:
                scale = 1.25
        
        try:
            word_font = ImageFont.truetype(font_file, int(font_size * scale)) if scale != 1.0 else font
        except Exception:
            word_font = font
            
        display_text = w_text.upper() if caption_preset in ["mrbeast", "hormozi", "tiktok"] else w_text
        w_width = draw.textlength(display_text, font=word_font)
        
        if is_active:
            if caption_preset in ["mrbeast", "hormozi"]:
                word_color = (255, 255, 0) if (active_word_idx % 2 == 0) else (57, 255, 20)
            elif caption_preset == "tiktok":
                word_color = (255, 215, 0)
            elif caption_preset == "cyberpunk":
                word_color = (0, 255, 255)
            else:
                word_color = highlight_rgb
        else:
            word_color = (220, 220, 220) if caption_preset in ["hormozi", "mrbeast", "tiktok"] else (255, 255, 255)
                
        words_metadata.append({
            "text": display_text,
            "width": w_width,
            "font": word_font,
            "color": word_color,
            "scale": scale,
            "is_active": is_active,
            "raw_word": w_text
        })
        total_w += w_width + space_w
        
    total_w -= space_w
    
    # Bounding Box Safety: If text exceeds width, scale starting position or auto-clamp
    max_allowed_w = target_size[0] - 80
    if total_w > max_allowed_w:
        shrink_ratio = max_allowed_w / total_w
        start_x = 40
    else:
        start_x = (target_size[0] - total_w) / 2
    
    curr_x = start_x
    for w_meta in words_metadata:
        text = w_meta["text"]
        w_w = w_meta["width"]
        word_font = w_meta["font"]
        word_color = w_meta["color"]
        scale = w_meta["scale"]
        is_active = w_meta.get("is_active", False)
        
        y_offset = -int((font_size * (scale - 1.0)) / 2) if scale > 1.0 else 0
            
        # Draw Drop Shadow
        if caption_preset not in ["minimalist", "abdaal"]:
            shadow_offset = int(4 * scale)
            draw.text(
                (curr_x + shadow_offset, y_pos + y_offset + shadow_offset), 
                text, 
                fill=(0, 0, 0, 180),
                font=word_font, 
                stroke_width=int(4 * scale), 
                stroke_fill=(0, 0, 0)
            )
            
        # Draw Main Text with Stroke
        outline_w = int(4 * scale) if caption_preset in ["hormozi", "mrbeast", "tiktok"] else int(2 * scale)
        draw.text(
            (curr_x, y_pos + y_offset), 
            text, 
            fill=word_color, 
            font=word_font, 
            stroke_width=outline_w, 
            stroke_fill=(0, 0, 0)
        )
        
        curr_x += w_w + space_w
        
    return np.array(pil_img)


def assemble_video(segments: list, output_path: str, aspect_ratio: str = "16:9", bg_music_path: str = None, font_name: str = "Arial Bold", highlight_color: str = "Yellow", caption_position: str = "Bottom", add_watermark: bool = False, caption_preset: str = "default", no_sound: bool = False, brand: str = "", price: str = "", cta: str = "", niche: str = "") -> str:
    """
    Stitches generated audio and visual assets together into a final MP4 video.
    Decouples voiceover audio concatenation from visual crossfade to eliminate speech overlap collisions.
    """
    import random
    from moviepy.audio.AudioClip import CompositeAudioClip, concatenate_audioclips
    
    if no_sound:
        bg_music_path = None
        print("[No-Sound Mode] Voiceover and BGM disabled.")
    
    target_size = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
    video_clips = []
    audio_clips = []
    
    speaking_intervals = []
    clip_start_times = []
    environmental_sfx_clips = []
    curr_start = 0.0
    
    motion_types = ["zoom_in", "zoom_out", "pan_right", "zoom_in"]
    
    # Read project metadata
    brand_meta = brand
    price_meta = price
    cta_meta = cta
    niche_meta = niche
    if segments and segments[0].get("audio_path"):
        p_dir = os.path.dirname(segments[0].get("audio_path"))
        p_meta = os.path.join(p_dir, "metadata.json")
        if os.path.exists(p_meta):
            try:
                with open(p_meta, "r", encoding="utf-8") as fm:
                    meta_data = json.load(fm)
                    brand_meta = brand_meta or meta_data.get("brand", "")
                    price_meta = price_meta or meta_data.get("price", "")
                    cta_meta = cta_meta or meta_data.get("cta", "")
                    niche_meta = niche_meta or meta_data.get("niche", "")
            except Exception as me:
                print(f"Warning: Failed loading metadata overlays: {me}")

    valid_segments = []
    for i, seg in enumerate(segments):
        img_path = seg.get("image_path")
        audio_path = seg.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            print(f"Skipping segment {i} due to missing audio: {audio_path}")
            continue
        valid_segments.append(seg)

    num_segs = len(valid_segments)
    for i, seg in enumerate(valid_segments):
        img_path = seg.get("image_path")
        audio_path = seg.get("audio_path")
        
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        audio_clips.append(audio_clip)
        clip_start_times.append(curr_start)
        
        # Visual duration includes 0.5s overlap extension for crossfade (except last clip)
        crossfade_dur = 0.5 if (i < num_segs - 1) else 0.0
        clip_visual_duration = duration + crossfade_dur
        
        if not img_path or not os.path.exists(img_path):
            print(f"Warning: Visual asset missing for segment {i} ({img_path}). Using fallback slate canvas.")
            img_path = None
            
        motion_style = motion_types[i % len(motion_types)]
        img_clip = create_ken_burns_clip(img_path, clip_visual_duration, target_size=target_size, motion_type=motion_style)
        
        # Subtitles filter
        base_audio_path, _ = os.path.splitext(audio_path)
        json_path = base_audio_path + ".json"
        word_timings = None
        try:
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as fj:
                    word_timings = json.load(fj)
            
            is_last = (i == num_segs - 1)
            is_first = (i == 0)
            
            def make_subtitle_filter(timings, size, font, color, pos, watermark, is_last_seg, preset, b_val, p_val, c_val, is_first_seg, n_val):
                def filter_func(get_frame, t):
                    frame = get_frame(t)
                    return draw_text_on_frame(frame, t, timings, size, font, color, pos, watermark, is_last_seg, preset, b_val, p_val, c_val, is_first_seg, n_val)
                return filter_func
            
            filter_to_apply = make_subtitle_filter(
                word_timings, 
                target_size, 
                font_name, 
                highlight_color, 
                caption_position, 
                add_watermark,
                is_last,
                caption_preset,
                brand_meta,
                price_meta,
                cta_meta,
                is_first,
                niche_meta
            )
            
            if hasattr(img_clip, "transform"):
                img_clip = img_clip.transform(filter_to_apply)
            else:
                img_clip = img_clip.fl(filter_to_apply)
        except Exception as se:
            print(f"Warning: Failed to apply subtitle/watermark overlay: {se}")
            
        if word_timings:
            for w in word_timings:
                word_start = curr_start + w.get("start", 0)
                word_end = curr_start + w.get("end", 0)
                speaking_intervals.append((word_start - 0.15, word_end + 0.15))
                
        video_clips.append(img_clip)
        curr_start += duration

    if not video_clips:
        raise ValueError("No valid video segments to assemble")
        
    # Apply crossfadein to video clips (visuals only)
    for idx_clip in range(1, len(video_clips)):
        try:
            if hasattr(video_clips[idx_clip], "with_effects"):
                import moviepy.video.fx as vfx
                video_clips[idx_clip] = video_clips[idx_clip].with_effects([vfx.CrossFadeIn(0.5)])
            elif hasattr(video_clips[idx_clip], "crossfadein"):
                video_clips[idx_clip] = video_clips[idx_clip].crossfadein(0.5)
        except Exception as cf_err:
            print(f"Warning applying crossfade effect: {cf_err}")
        
    # Concatenate visuals with padding=-0.5 for smooth cross-dissolve
    if len(video_clips) > 1:
        final_video_clip = concatenate_videoclips(video_clips, method="compose", padding=-0.5)
    else:
        final_video_clip = video_clips[0]
        
    # Concatenate speech voiceovers with zero collision
    if not no_sound and audio_clips:
        master_narration = concatenate_audioclips(audio_clips)
        final_clip = final_video_clip.with_audio(master_narration)
    else:
        final_clip = final_video_clip
        
    final_duration = final_clip.duration
    
    # Background Music Integration & Dynamic Ducking
    if bg_music_path and os.path.exists(bg_music_path) and not no_sound:
        try:
            bg_clip = AudioFileClip(bg_music_path)
            import math
            n_loops = int(math.ceil(final_duration / bg_clip.duration))
            bg_clip_looped = concatenate_audioclips([bg_clip] * n_loops).subclipped(0, final_duration)
            
            # Reliable ducking: scale BGM to 12% so voiceover is crisp and clear
            bg_clip_ducked = bg_clip_looped.with_volume_scaled(0.12)
            mixed_audio = CompositeAudioClip([final_clip.audio, bg_clip_ducked])
            final_clip = final_clip.with_audio(mixed_audio)
            print(f"Successfully mixed background music: {bg_music_path}")
        except Exception as e:
            print(f"Warning: Failed to mix background music: {e}")
            
    # CTA Notification Chime
    chime_sfx_path = "static/music/chime_notification.wav"
    if os.path.exists(chime_sfx_path) and len(clip_start_times) > 0 and not no_sound:
        try:
            chime_sfx = AudioFileClip(chime_sfx_path)
            chime_start_t = clip_start_times[-1]
            chime_clip = chime_sfx.with_start(chime_start_t)
            mixed_audio = CompositeAudioClip([final_clip.audio, chime_clip])
            final_clip = final_clip.with_audio(mixed_audio)
            print("Successfully mixed final segment chime notification sound effect!")
        except Exception as ce:
            print(f"Warning: Failed to mix chime sound effect: {ce}")
            
    final_clip.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-audio.m4a",
        remove_temp=True
    )
    
    final_clip.close()
    for c in video_clips:
        c.close()
    for a in audio_clips:
        a.close()
        
    return output_path


def animate_lifestyle_clip_replicate(image_path: str, output_video_path: str, prompt: str = "Gentle subtle camera motion, high-end commercial ad") -> str:
    """
    Uses Replicate Image-to-Video models (e.g. Minimax / Luma / Kling) to generate
    real physical generative motion from a lifestyle still image.
    """
    if not REPLICATE_API_TOKEN:
        print("REPLICATE_API_TOKEN not configured for video animation. Falling back to Ken Burns.")
        return ""

    print(f"Generating Real AI Video Motion via Replicate: {prompt[:60]}...")
    try:
        clean_motion_prompt = sanitize_visual_prompt(prompt)
        with open(image_path, "rb") as img_file:
            # Using minimax/video-01 image-to-video model on Replicate
            output = replicate.run(
                "minimax/video-01",
                input={
                    "first_frame_image": img_file,
                    "prompt": f"{clean_motion_prompt}, slow smooth cinematic camera drift, professional lighting, photorealistic 4k commercial, no text, no subtitles, no watermarks",
                    "prompt_optimizer": True
                }
            )
        
        # Download generated video
        if output:
            video_url = str(output)
            print(f"AI Video generated successfully: {video_url}")
            import httpx
            with httpx.Client(timeout=120) as client:
                r = client.get(video_url)
                if r.status_code == 200:
                    with open(output_video_path, "wb") as f:
                        f.write(r.content)
                    return output_video_path
        return ""
    except Exception as e:
        print(f"Warning: AI Video Generation fallback to Ken Burns: {e}")
        return ""
