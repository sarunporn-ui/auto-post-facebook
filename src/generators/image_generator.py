"""Generates an actual image from a text prompt using OpenAI's Images API.
Used by Format 2 to turn its image_prompt into a real file instead of just
descriptive text — independent of whichever LLM_PROVIDER writes the copy,
since Anthropic has no image-generation endpoint."""
from __future__ import annotations
import base64
import uuid
from pathlib import Path

import requests

from src.config import get_settings

IMAGE_MODEL = "gpt-image-1"
IMAGE_SIZE = "1024x1024"


def generate_image(prompt: str) -> str:
    """Generate an image and save it to data/generated/images/. Returns the
    local file path. Raises RuntimeError if OPENAI_API_KEY isn't configured."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured — image generation needs an OpenAI "
            "key even if your text model is Anthropic/Gemini."
        )

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.images.generate(
        model=IMAGE_MODEL, prompt=prompt, size=IMAGE_SIZE, n=1
    )
    image_data = response.data[0]

    if getattr(image_data, "b64_json", None):
        image_bytes = base64.b64decode(image_data.b64_json)
    else:
        image_bytes = requests.get(image_data.url, timeout=60).content

    output_dir = settings.data_dir / "generated" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"image_{uuid.uuid4().hex[:8]}.png"
    image_path.write_bytes(image_bytes)
    return str(image_path)
