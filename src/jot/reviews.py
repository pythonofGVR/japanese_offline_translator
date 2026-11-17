"""Source-bearing review records live in local application data, never in outputs."""
import hashlib
from pathlib import Path
from .paths import user_data, read_json

def review_path(output):
    key = hashlib.sha256(str(Path(output).resolve()).casefold().encode('utf-8')).hexdigest()
    return user_data() / 'reviews' / (key + '.review.json')

def load_review(output):
    current = read_json(review_path(output), {})
    # Read legacy records without moving or deleting any user files.
    return current or read_json(Path(output).with_name(Path(output).name + '.review.json'), {})
