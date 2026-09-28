"""Synthetic print-image dataset generator (PIL only).

Real print-defect photo datasets are not distributed with this repo (none were supplied), so
this module procedurally generates images with the *visual signatures* of five classes and
prints/report an honest disclaimer wherever accuracy is shown. If real photos are available,
point train_defect_model.py at a folder instead (see its --data-dir flag) and this generator
is skipped entirely.

Classes and their visual signature (loosely modelled on real FDM print defects):
  NORMAL       - regular horizontal layer lines, low noise
  WARPING      - corners lifted/curled: brighter, distorted corner regions
  STRINGING    - thin random filament strands across the print
  LAYER_SHIFT  - a horizontal discontinuity: layers above a Y are shifted sideways
  CLOGGING     - patchy under-extrusion: gaps/holes in an otherwise filled region
"""
import io
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

CLASSES = ["NORMAL", "WARPING", "STRINGING", "LAYER_SHIFT", "CLOGGING"]
IMAGE_SIZE = 128  # square; matches hardware.ml_image_size default order of magnitude


def _base_layers(rng: random.Random, size: int) -> Image.Image:
    """A grey square print body ruled with horizontal layer lines."""
    image = Image.new("L", (size, size), color=170)
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.rectangle([margin, margin, size - margin, size - margin], fill=190)
    step = max(2, size // 40)
    for y in range(margin, size - margin, step):
        shade = 175 + rng.randint(-4, 4)
        draw.line([(margin, y), (size - margin, y)], fill=shade, width=1)
    return image


def _add_noise(image: Image.Image, rng: random.Random, sigma: float = 4.0) -> Image.Image:
    arr = np.asarray(image, dtype=np.float32)
    arr += np.asarray([rng.gauss(0, sigma) for _ in range(arr.size)]).reshape(arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _render(label: str, rng: random.Random, size: int = IMAGE_SIZE) -> Image.Image:
    image = _base_layers(rng, size)
    draw = ImageDraw.Draw(image)
    margin = size // 8

    if label == "WARPING":
        for cx, cy in [(margin, margin), (size - margin, margin),
                       (margin, size - margin), (size - margin, size - margin)]:
            r = size // 10
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=230)
        image = image.rotate(rng.uniform(-2, 2), resample=Image.BILINEAR, fillcolor=170)

    elif label == "STRINGING":
        for _ in range(rng.randint(15, 30)):
            x1, y1 = rng.randint(margin, size - margin), rng.randint(margin, size - margin)
            x2 = x1 + rng.randint(-size // 3, size // 3)
            y2 = y1 + rng.randint(-size // 3, size // 3)
            draw.line([(x1, y1), (x2, y2)], fill=60, width=1)

    elif label == "LAYER_SHIFT":
        split = rng.randint(size // 3, 2 * size // 3)
        shift = rng.randint(size // 12, size // 6) * rng.choice([-1, 1])
        arr = np.asarray(image).copy()
        top = arr[:split].copy()
        shifted = np.roll(top, shift, axis=1)
        if shift > 0:
            shifted[:, :shift] = 170
        elif shift < 0:
            shifted[:, shift:] = 170
        arr[:split] = shifted
        image = Image.fromarray(arr)
        draw = ImageDraw.Draw(image)
        draw.line([(0, split), (size, split)], fill=90, width=1)

    elif label == "CLOGGING":
        for _ in range(rng.randint(6, 14)):
            r = rng.randint(size // 20, size // 8)
            cx, cy = rng.randint(margin, size - margin), rng.randint(margin, size - margin)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=60)

    image = _add_noise(image, rng, sigma=3.0 if label == "NORMAL" else 5.0)
    return image.filter(ImageFilter.GaussianBlur(radius=0.4))


def generate_image(label: str, seed: int, size: int = IMAGE_SIZE) -> bytes:
    """PNG bytes for one synthetic image of the given class. Deterministic given the seed."""
    if label not in CLASSES:
        raise ValueError(f"Unknown class: {label}")
    # Deterministic synthetic-data generation, not a security context; secrets does not
    # support seeding, which reproducibility here requires.
    rng = random.Random(seed)  # noqa: S311  # nosec B311
    buffer = io.BytesIO()
    _render(label, rng, size).convert("L").save(buffer, format="PNG")
    return buffer.getvalue()


def generate_dataset(samples_per_class: int, seed: int = 0, size: int = IMAGE_SIZE):
    """Yield (label, png_bytes) for samples_per_class images of each class, deterministically."""
    counter = seed * 1_000_003
    for label in CLASSES:
        for _ in range(samples_per_class):
            counter += 1
            yield label, generate_image(label, counter, size)
