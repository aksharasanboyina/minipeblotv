import io
from typing import List, Tuple

from PIL import Image

ARTWORK_SPECS = {
    "poster": {"aspect_ratio": 2 / 3, "target_width": 600, "target_height": 900, "max_bytes": 200 * 1024},
    "banner": {"aspect_ratio": 16 / 9, "target_width": 1280, "target_height": 720, "max_bytes": 200 * 1024},
    "thumbnail": {"aspect_ratio": 16 / 9, "target_width": 640, "target_height": 360, "max_bytes": 200 * 1024},
}

ALLOWED_TYPES = {"poster", "banner", "thumbnail"}


def validate_artwork(file_data: bytes, artwork_type: str) -> Tuple[bool, List[str], dict]:
    errors = []
    metadata = {}

    if artwork_type not in ALLOWED_TYPES:
        return False, [f"Invalid artwork type '{artwork_type}'. Must be one of: {', '.join(ALLOWED_TYPES)}"], {}

    spec = ARTWORK_SPECS[artwork_type]

    if len(file_data) > spec["max_bytes"]:
        max_kb = spec["max_bytes"] // 1024
        actual_kb = len(file_data) // 1024
        errors.append(
            f"File size {actual_kb} KB exceeds the {max_kb} KB limit for {artwork_type}. "
            f"Please compress the image or use a smaller file."
        )

    try:
        img = Image.open(io.BytesIO(file_data))
        width, height = img.size
        metadata = {"width": width, "height": height, "file_size_bytes": len(file_data)}

        target_ratio = spec["aspect_ratio"]
        actual_ratio = width / height if height > 0 else 0

        tolerance = 0.05
        if abs(actual_ratio - target_ratio) > tolerance:
            expected_w, expected_h = spec["target_width"], spec["target_height"]
            errors.append(
                f"Aspect ratio mismatch for {artwork_type}: expected ~{expected_w}x{expected_h} "
                f"(ratio {target_ratio:.2f}), got {width}x{height} (ratio {actual_ratio:.2f}). "
                f"Please upload an image with the correct aspect ratio."
            )

        if artwork_type == "poster":
            if abs(width - spec["target_width"]) > 50 or abs(height - spec["target_height"]) > 50:
                errors.append(
                    f"Poster dimensions should be close to {spec['target_width']}x{spec['target_height']} pixels. "
                    f"Got {width}x{height}."
                )
        elif artwork_type == "banner":
            if abs(width - spec["target_width"]) > 100 or abs(height - spec["target_height"]) > 100:
                errors.append(
                    f"Banner dimensions should be close to {spec['target_width']}x{spec['target_height']} pixels. "
                    f"Got {width}x{height}."
                )
        elif artwork_type == "thumbnail":
            if abs(width - spec["target_width"]) > 60 or abs(height - spec["target_height"]) > 60:
                errors.append(
                    f"Thumbnail dimensions should be close to {spec['target_width']}x{spec['target_height']} pixels. "
                    f"Got {width}x{height}."
                )

    except Exception:
        errors.append(
            "Could not read the image file. Please upload a valid JPEG or PNG image."
        )

    return len(errors) == 0, errors, metadata
