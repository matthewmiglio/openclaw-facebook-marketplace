"""Benchmark script for Moondream vision model via Ollama.

Downloads a sample shoe image and measures inference time.
"""

import os
import time
import urllib.request

import ollama

IMAGE_URL = "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=640"
VISION_MODEL = "moondream"
PROMPT = "What is the main product or item in this image?"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.join(SCRIPT_DIR, "test-images")


def main():
    # Download image
    os.makedirs(IMAGE_DIR, exist_ok=True)
    image_path = os.path.join(IMAGE_DIR, "shoes.jpg")
    print(f"Downloading image...")
    urllib.request.urlretrieve(IMAGE_URL, image_path)
    print(f"Saved to {image_path}")

    # Run inference
    print(f"\nRunning {VISION_MODEL} inference...")
    t0 = time.time()
    response = ollama.chat(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": PROMPT, "images": [image_path]}],
    )
    elapsed = time.time() - t0

    description = response.message.content.strip().split("\n\n")[0].strip()

    print(f"\n--- Results ---")
    print(f"Description: {description}")
    print(f"Inference time: {elapsed:.2f}s")

    # Cleanup
    os.unlink(image_path)


if __name__ == "__main__":
    main()
