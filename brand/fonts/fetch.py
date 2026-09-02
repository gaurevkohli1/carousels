"""Vendor the brand webfonts locally so rendering is deterministic and offline.

Run once after cloning:  python3 brand/fonts/fetch.py
The .ttf files are gitignored; this script is the reproducible way to get them.
Both families are SIL Open Font License 1.1.
"""
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).parent
API = "https://fonts.googleapis.com/css2"
UA = {"User-Agent": "Mozilla/5.0"}  # Google serves woff2 only to modern UAs

FAMILIES = {
    "BricolageGrotesque": "family=Bricolage+Grotesque:wght@700;800",
    "Archivo": "family=Archivo:wght@400;500;600;700",
}


def fetch(name: str, query: str) -> None:
    css = urllib.request.urlopen(
        urllib.request.Request(f"{API}?{query}&display=swap", headers=UA)
    ).read().decode()

    for weight, url in re.findall(
        r"font-weight:\s*(\d+);.*?src:\s*url\((https://[^)]+)\)", css, re.S
    ):
        dest = HERE / f"{name}-{weight}.ttf"
        if dest.exists():
            print(f"  have {dest.name}")
            continue
        dest.write_bytes(urllib.request.urlopen(
            urllib.request.Request(url, headers=UA)).read())
        print(f"  got  {dest.name} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    for name, query in FAMILIES.items():
        print(name)
        try:
            fetch(name, query)
        except Exception as exc:
            sys.exit(f"could not fetch {name}: {exc}")
    print("\nFonts ready. Slides will now render identically on any machine.")
