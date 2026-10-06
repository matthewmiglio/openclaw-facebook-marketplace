"""Vision module for analysing listing product photos.

Uses the Moondream model (via Ollama) to generate text descriptions of
listing images, which are then fed into the scorer to catch mismatches
between what a listing claims and what the photos actually show.
"""

import os
import threading
import time
import llm
import colors as c

VISION_MODEL = "moondream"
PROMPT = "What is the main product or item in this image?"


def describe_image(image_path: str, model: str = VISION_MODEL) -> str:
    """Send a single image to the vision model and get a product description."""
    # Claude defaults to markdown; ask for one plain sentence so the paragraph trim below keeps the content
    system = "Answer in one or two plain sentences. No markdown, no headings." if llm.is_claude(model) else ""
    response = llm.chat(model, system, PROMPT, images=[image_path])
    text = response["message"]["content"].strip()
    # Moondream sometimes hallucinated follow-up Q&A — keep only the first paragraph
    text = text.split("\n\n")[0].strip()
    return text


def describe_listing_images(image_paths: list[str], model: str = VISION_MODEL) -> list[str]:
    """Describe all images for a listing. Returns list of descriptions.

    Claude models handle images themselves; any Ollama text model falls back to moondream.
    """
    if not image_paths:
        return []
    if not llm.is_claude(model):
        model = VISION_MODEL

    c.vision(f"Analyzing {len(image_paths)} images with {model}...")
    t0 = time.time()

    descriptions = []
    for i, path in enumerate(image_paths):
        try:
            img_t0 = time.time()
            result_holder = {}

            def _analyze(p=path):
                result_holder["desc"] = describe_image(p, model)

            thread = threading.Thread(target=_analyze)
            thread.start()
            while thread.is_alive():
                elapsed = int(time.time() - img_t0)
                print(f"  {c.PURPLE}[vision]{c.RESET} Analyzing image {i+1} {elapsed}s...", end="\r")
                thread.join(timeout=1)

            desc = result_holder["desc"]
            img_elapsed = time.time() - img_t0
            descriptions.append(desc)
            truncated = c._safe(desc[:80]) + ("..." if len(desc) > 80 else "")
            print(f"  {c.PURPLE}[vision]{c.RESET} Image {i+1}: {img_elapsed:.0f}s \"{truncated}\"" + " " * 20)
        except Exception as e:
            print(f"  {c.PURPLE}[vision]{c.RESET} Image {i+1}: ERROR — {e}" + " " * 20)

    elapsed = time.time() - t0
    c.vision(f"Vision analysis took {elapsed:.1f}s for {len(image_paths)} images")
    return descriptions


def cleanup_image_files(image_paths: list[str]):
    """Delete temp screenshot files."""
    for path in image_paths:
        try:
            os.unlink(path)
        except OSError:
            pass
