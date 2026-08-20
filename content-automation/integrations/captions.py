"""
Caption + hashtag generation using the Anthropic API.
This one is fully wired — just add ANTHROPIC_API_KEY to .env.
"""
import json

from anthropic import AsyncAnthropic

from config import ANTHROPIC_API_KEY

_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


async def generate_captions(business_name: str, business_type: str, product_name: str, count: int) -> list[dict]:
    """
    Returns a list of {caption, hashtags} dicts, one per piece of content.
    """
    if _client is None:
        return [
            {
                "caption": f"[DRY RUN] Caption {i+1} for {product_name or business_name}",
                "hashtags": "#dryrun #addyourkey",
            }
            for i in range(count)
        ]

    prompt = f"""You are writing Instagram captions for a small business's product content.

Business name: {business_name}
Business type: {business_type}
Product: {product_name or "their product"}

Write exactly {count} short, distinct Instagram captions (1-2 sentences each,
upbeat, no corporate tone, suitable for reels) and a matching set of 5-8
relevant hashtags for each. Vary the angle across captions (some
benefit-led, some emotional, some direct/CTA).

Respond with ONLY a JSON array, no other text, in this exact shape:
[{{"caption": "...", "hashtags": "#tag1 #tag2 #tag3"}}, ...]
"""

    response = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)
