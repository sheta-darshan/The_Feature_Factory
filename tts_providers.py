"""
Multi-TTS Provider Engine
Inspired by OpenReels' support for 6+ TTS providers.
Supports: Edge TTS (free), OpenAI TTS (premium), ElevenLabs (ultra-premium).
"""
import os
import json
import asyncio
import httpx
import edge_tts
from dotenv import load_dotenv

load_dotenv()


def synthesize_word_timings(text: str, audio_path: str) -> str:
    """
    Interpolates word timings across audio duration for TTS engines that do not
    provide word-level timestamps (e.g. ElevenLabs, OpenAI TTS).
    """
    json_path = os.path.splitext(audio_path)[0] + ".json"
    cleaned_words = [w.strip() for w in text.replace("**", "").replace("*", "").replace("_", "").split() if w.strip()]
    if not cleaned_words:
        return json_path
        
    total_duration = 0.0
    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(audio_path)
        total_duration = max(0.5, float(clip.duration))
        try:
            clip.close()
        except Exception:
            pass
    except Exception:
        total_duration = max(1.0, len(cleaned_words) / 2.3)
        
    start_pad = 0.05
    effective_duration = max(0.3, total_duration - 0.1)
    word_dur = effective_duration / len(cleaned_words)
    
    words_data = []
    for idx, w in enumerate(cleaned_words):
        w_start = start_pad + (idx * word_dur)
        w_end = min(total_duration, w_start + word_dur)
        words_data.append({
            "word": w,
            "start": round(w_start, 3),
            "end": round(w_end, 3)
        })
        
    try:
        with open(json_path, "w", encoding="utf-8") as fj:
            json.dump(words_data, fj, indent=2)
    except Exception as je:
        print(f"Warning: Failed saving synthesized word timings: {je}")
        
    return json_path


async def generate_voiceover_multi(text: str, output_path: str, voice: str = "en-US-GuyNeural",
                                    provider: str = "edge-tts", rate: str = "+0%", pitch: str = "+0Hz") -> str:
    """
    Unified TTS interface that routes to the correct provider.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if provider == "openai-tts":
        return await _generate_openai_tts(text, output_path, voice)
    elif provider == "elevenlabs":
        return await _generate_elevenlabs_tts(text, output_path, voice)
    else:
        # Default: Edge TTS (free)
        return await _generate_edge_tts(text, output_path, voice, rate, pitch)


async def _generate_edge_tts(text: str, output_path: str, voice: str, rate: str, pitch: str) -> str:
    """Generate voiceover using Microsoft Edge TTS (free) with word timestamps."""
    try:
        cleaned_text = text.replace("**", "").replace("*", "").replace("_", "").strip()
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
        json_path = output_path.replace(".mp3", ".json")
        with open(json_path, "w", encoding="utf-8") as fj:
            json.dump(words, fj, indent=2)
        print(f"[Edge TTS] Generated voiceover with subtitles: {output_path}")
        return output_path
    except Exception as e:
        print(f"[Edge TTS] Error: {e}")
        raise


async def _generate_openai_tts(text: str, output_path: str, voice: str = "nova") -> str:
    """Generate voiceover using OpenAI TTS API (premium quality)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[OpenAI TTS] No OPENAI_API_KEY found. Falling back to Edge TTS.")
        return await _generate_edge_tts(text, output_path, "en-US-GuyNeural", "+0%", "+0Hz")
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1-hd",
                    "input": text,
                    "voice": voice if voice in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] else "nova",
                    "response_format": "mp3",
                    "speed": 1.0,
                },
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI TTS returned {response.status_code}: {response.text}")
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            synthesize_word_timings(text, output_path)
            print(f"[OpenAI TTS] Generated voiceover with subtitles ({voice}): {output_path}")
            return output_path
    except Exception as e:
        print(f"[OpenAI TTS] Error: {e}. Falling back to Edge TTS.")
        return await _generate_edge_tts(text, output_path, "en-US-GuyNeural", "+0%", "+0Hz")


async def _generate_elevenlabs_tts(text: str, output_path: str, voice: str = "Rachel") -> str:
    """Generate voiceover using ElevenLabs API (ultra-premium quality)."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("[ElevenLabs] No ELEVENLABS_API_KEY found. Falling back to Edge TTS.")
        return await _generate_edge_tts(text, output_path, "en-US-GuyNeural", "+0%", "+0Hz")
    
    # ElevenLabs voice name to ID mapping (common voices)
    voice_ids = {
        "Rachel": "21m00Tcm4TlvDq8ikWAM",
        "Adam": "pNInz6obpgDQGcFmaJgB",
        "Bella": "EXAVITQu4vr4xnSDxMaL",
        "Antoni": "ErXwobaYiN019PkySvjV",
        "Domi": "AZnzlk1XvdvUeBnXmlld",
        "Elli": "MF3mGyEYCl7XYWbV9V6O",
    }
    
    voice_id = voice_ids.get(voice, voice_ids.get("Rachel"))
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": "eleven_monolingual_v1",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"ElevenLabs returned {response.status_code}: {response.text}")
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            synthesize_word_timings(text, output_path)
            print(f"[ElevenLabs] Generated voiceover with subtitles ({voice}): {output_path}")
            return output_path
    except Exception as e:
        print(f"[ElevenLabs] Error: {e}. Falling back to Edge TTS.")
        return await _generate_edge_tts(text, output_path, "en-US-GuyNeural", "+0%", "+0Hz")
