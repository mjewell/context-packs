"""Retry a GitHub request up to three times, one second apart. A scratch file for testing the review action."""
import time

import requests


def fetch(url, tries=3):
    """The JSON GitHub answers url with, or None when every try fails."""
    for _ in range(tries):
        try:
            return requests.get(url, timeout=10).json()
        except Exception:
            time.sleep(1)
    return None
