"""Minimal User-Agent parsing for device/session display.

Not exhaustive — this is for showing a human a recognisable "Chrome on
Windows" label in login history / device lists, not for browser sniffing
decisions. Deliberately regex-based rather than a new dependency.
"""
import re

_BROWSER_PATTERNS = [
    ("Edge", r"Edg/"),
    ("Opera", r"OPR/"),
    ("Chrome", r"Chrome/"),
    ("Firefox", r"Firefox/"),
    ("Safari", r"Version/.*Safari/"),
    ("Internet Explorer", r"MSIE |Trident/"),
]

_OS_PATTERNS = [
    ("Windows", r"Windows NT"),
    ("macOS", r"Mac OS X"),
    ("iOS", r"iPhone|iPad|iPod"),
    ("Android", r"Android"),
    ("Linux", r"Linux"),
]


def parse_user_agent(user_agent: str | None) -> dict:
    """Return {"browser", "os", "device_name"} best-effort labels from a raw UA string."""
    ua = user_agent or ""
    browser = next((name for name, pat in _BROWSER_PATTERNS if re.search(pat, ua)), "Unknown browser")
    os_name = next((name for name, pat in _OS_PATTERNS if re.search(pat, ua)), "Unknown OS")
    mobile = bool(re.search(r"Mobile|Android|iPhone|iPad", ua))
    device_name = f"{browser} on {os_name}" + (" (mobile)" if mobile else "")
    return {"browser": browser, "os": os_name, "device_name": device_name}
