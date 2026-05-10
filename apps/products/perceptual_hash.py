"""
Perceptual image hash (dHash) — dependency-free except for Pillow.

dHash is a 64-bit fingerprint of an image's *visual content*. Two photos
of the same product (even from different angles, with different
backgrounds, slight crops, JPEG compression) tend to have hashes within
a small Hamming distance of each other.

Algorithm
---------
1. Convert to grayscale.
2. Resize to 9 × 8 (one extra column so we can compare adjacent pixels).
3. For each row, compare pixel[i] > pixel[i+1] → 0 or 1.
4. Pack the 64 bits into an integer; hex-encode for storage.

What this is NOT
----------------
* Not a cryptographic hash — collisions are intentional (visually
  similar = numerically close).
* Not great at catching VERY different photos of the same product
  (different angle, different lighting). For that you need actual
  feature embeddings (CLIP). dHash is the cheap "is this literally the
  same photo, possibly compressed differently?" detector — exactly the
  fork-prevention we want when sellers reuse manufacturer images.
"""
from __future__ import annotations

from typing import Optional


HASH_HEX_LEN = 16   # 64 bits → 16 hex chars


def _open_image(image_or_file):
    """Coerce file-like / path / Pillow Image into a Pillow Image."""
    from PIL import Image

    if image_or_file is None:
        return None
    if isinstance(image_or_file, Image.Image):
        return image_or_file
    return Image.open(image_or_file)


def compute_dhash(image_or_file) -> Optional[str]:
    """Return the 16-character hex dHash of the image, or None on failure."""
    from PIL import Image

    try:
        img = _open_image(image_or_file)
        if img is None:
            return None
        # Pillow rewinds the file pointer if the source is a Django file
        # object; we explicitly reopen via Image.open so this is safe.
        img = img.convert('L').resize((9, 8), Image.LANCZOS)
        pixels = img.load()

        bits = 0
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | (1 if pixels[x, y] > pixels[x + 1, y] else 0)

        # 64-bit value → 16 hex chars (zero-padded)
        return f'{bits:016x}'
    except Exception:
        return None


def hamming_distance(a: str, b: str) -> int:
    """Number of differing bits between two hex-encoded dHashes.

    0 = identical, 64 = inverted. <=5 is a good "same image" threshold;
    <=10 catches lightly-modified copies.
    """
    if not a or not b or len(a) != len(b):
        return 64
    try:
        return bin(int(a, 16) ^ int(b, 16)).count('1')
    except Exception:
        return 64


def is_visually_similar(a: str, b: str, threshold: int = 5) -> bool:
    return hamming_distance(a, b) <= threshold
