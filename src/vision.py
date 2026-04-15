"""Vision module for analysing listing product photos.

Uses the Moondream model (via Ollama) to generate text descriptions of
listing images, which are then fed into the scorer to catch mismatches
between what a listing claims and what the photos actually show.
"""

import os
import time
import ollama

VISION_MODEL = "moondream"
PROMPT = "What is the main product or item in this image?"


def describe_image(image_path: str) -> str:
    """Send a single image to moondream and get a product description."""
    response = ollama.chat(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": PROMPT, "images": [image_path]}],
    )
    text = response.message.content.strip()
    # Moondream sometimes hallucinated follow-up Q&A — keep only the first paragraph
    text = text.split("\n\n")[0].strip()
    return text


def describe_listing_images(image_paths: list[str]) -> list[str]:
    """Describe all images for a listing. Returns list of descriptions."""
    if not image_paths:
        return []

    print(f"  [vision] Analyzing {len(image_paths)} images with {VISION_MODEL}...")
    t0 = time.time()

    descriptions = []
    for i, path in enumerate(image_paths):
        try:
            img_t0 = time.time()
            desc = describe_image(path)
            img_elapsed = time.time() - img_t0
            descriptions.append(desc)
            print(f"  [vision] Image {i+1}: {img_elapsed:.0f}s \"{desc[:80]}\"")
        except Exception as e:
            print(f"  [vision] Image {i+1}: ERROR — {e}")

    elapsed = time.time() - t0
    print(f"  [vision] Vision analysis took {elapsed:.1f}s for {len(image_paths)} images")
    return descriptions


def cleanup_image_files(image_paths: list[str]):
    """Delete temp screenshot files."""
    for path in image_paths:
        try:
            os.unlink(path)
        except OSError:
            pass
