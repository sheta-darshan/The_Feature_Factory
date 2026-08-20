"""
Stock Footage Provider — Pexels & Pixabay Integration
Inspired by OpenReels' hybrid visual strategy that mixes AI-generated
visuals with real stock footage for more authentic lifestyle scenes.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()


async def search_pexels_videos(query: str, orientation: str = "portrait",
                                per_page: int = 3, min_duration: int = 3,
                                max_duration: int = 10) -> list:
    """
    Search Pexels for stock video clips matching a scene description.
    
    Args:
        query: Search keywords (e.g. "woman drinking coffee cafe")
        orientation: portrait, landscape, or square
        per_page: Number of results to return
        min_duration/max_duration: Filter by video length
    
    Returns:
        List of dicts with 'url', 'preview_url', 'duration', 'width', 'height'
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        print("[Pexels] No PEXELS_API_KEY found. Stock footage unavailable.")
        return []
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.pexels.com/videos/search",
                params={
                    "query": query,
                    "orientation": orientation,
                    "per_page": per_page,
                    "size": "medium",
                },
                headers={"Authorization": api_key},
            )
            
            if response.status_code != 200:
                print(f"[Pexels] API error: {response.status_code}")
                return []
            
            data = response.json()
            results = []
            
            for video in data.get("videos", []):
                duration = video.get("duration", 0)
                if min_duration <= duration <= max_duration:
                    # Get the best quality video file in the right orientation
                    best_file = None
                    for vf in video.get("video_files", []):
                        if vf.get("quality") == "hd" or vf.get("quality") == "sd":
                            best_file = vf
                            break
                    if not best_file and video.get("video_files"):
                        best_file = video["video_files"][0]
                    
                    if best_file:
                        results.append({
                            "url": best_file["link"],
                            "preview_url": video.get("image", ""),
                            "duration": duration,
                            "width": best_file.get("width", 0),
                            "height": best_file.get("height", 0),
                            "source": "pexels",
                        })
            
            print(f"[Pexels] Found {len(results)} stock videos for '{query}'")
            return results
            
    except Exception as e:
        print(f"[Pexels] Search failed: {e}")
        return []


async def search_pixabay_images(query: str, orientation: str = "vertical",
                                 per_page: int = 5) -> list:
    """
    Search Pixabay for free stock images matching a scene description.
    
    Args:
        query: Search keywords
        orientation: horizontal, vertical, or all
        per_page: Number of results
    
    Returns:
        List of dicts with 'url', 'preview_url', 'width', 'height'
    """
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        print("[Pixabay] No PIXABAY_API_KEY found. Stock images unavailable.")
        return []
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://pixabay.com/api/",
                params={
                    "key": api_key,
                    "q": query,
                    "orientation": orientation,
                    "per_page": per_page,
                    "image_type": "photo",
                    "safesearch": "true",
                },
            )
            
            if response.status_code != 200:
                print(f"[Pixabay] API error: {response.status_code}")
                return []
            
            data = response.json()
            results = []
            
            for hit in data.get("hits", []):
                results.append({
                    "url": hit.get("largeImageURL", hit.get("webformatURL", "")),
                    "preview_url": hit.get("previewURL", ""),
                    "width": hit.get("imageWidth", 0),
                    "height": hit.get("imageHeight", 0),
                    "source": "pixabay",
                })
            
            print(f"[Pixabay] Found {len(results)} stock images for '{query}'")
            return results
            
    except Exception as e:
        print(f"[Pixabay] Search failed: {e}")
        return []


async def download_stock_asset(url: str, output_path: str) -> str:
    """Download a stock video or image to local path."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise RuntimeError(f"Download failed: {response.status_code}")
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            print(f"[Stock] Downloaded asset to: {output_path}")
            return output_path
    except Exception as e:
        print(f"[Stock] Download failed: {e}")
        return ""
