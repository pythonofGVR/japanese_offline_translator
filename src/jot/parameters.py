import os

THREAD_MIN = 1
THREAD_MAX = max(1, min(32, os.cpu_count() or 1))
DEFAULT_THREADS = min(4, THREAD_MAX)
BEAM_MIN, BEAM_MAX, DEFAULT_BEAM = 1, 10, 3

def validate_integer(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{label}必须是 {low}–{high} 之间的整数')
    return value

def restored_integer(value, default, low, high):
    try:
        if isinstance(value, bool):
            return default
        return max(low, min(high, int(value)))
    except (ValueError, TypeError, OverflowError):
        return default
