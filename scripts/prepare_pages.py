"""Turn Unity WebGL compressed build files into plain files for GitHub Pages.

GitHub Pages does not let us set Content-Encoding: br for pre-compressed
Unity assets. Its CDN may apply transfer gzip, which does NOT decode the
Brotli bytes inside .br. Normalize files and rewrite Unity's generated
index.html URLs to the uncompressed filenames before uploading to Pages.
"""

from __future__ import annotations

import argparse
import gzip
import re
from pathlib import Path

import brotli

COMPRESSED_SUFFIXES = {".br", ".gz", ".unityweb"}
UNITY_URL = re.compile(
    r'\b(?:dataUrl|frameworkUrl|codeUrl|memoryUrl|symbolsUrl)\s*:\s*'
    r'(?P<quote>["\'])(?P<url>Build/[^"\']+)(?P=quote)'
)


def _decompress(filename: Path) -> bytes:
    packed = filename.read_bytes()
    if filename.suffix == ".gz":
        return gzip.decompress(packed)
    if filename.suffix == ".br":
        return brotli.decompress(packed)

    # Unity's decompression-fallback files may end in .unityweb. Try
    # Brotli first, then gzip, as either format can be used.
    if filename.suffix == ".unityweb":
        if packed.startswith(b"\x1f\x8b"):
            return gzip.decompress(packed)
        try:
            return brotli.decompress(packed)
        except brotli.error:
            return gzip.decompress(packed)
    raise ValueError(f"Unexpected file suffix: {filename}")


def normalize(site: Path) -> dict[str, str]:
    site = site.resolve()
    index = site / "index.html"
    build_dir = site / "Build"
    if not index.is_file() or not build_dir.is_dir():
        raise ValueError(f"Not a Unity WebGL Pages site: {site}")

    old_to_new = {}
    for compressed in sorted(build_dir.rglob("*")):
        if not compressed.is_file() or compressed.suffix not in COMPRESSED_SUFFIXES:
            continue

        uncompressed = compressed.with_suffix("")
        if uncompressed.is_file():
            # Favor already-generated uncompressed Unity assets.
            # Keep them intact and remove the unused compressed duplicate.
            compressed.unlink()
        else:
            payload = _decompress(compressed)
            if not payload:
                raise ValueError(f"Empty decompressed Unity file: {compressed}")
            uncompressed.write_bytes(payload)
            compressed.unlink()

        old_url = compressed.relative_to(site).as_posix()
        new_url = uncompressed.relative_to(site).as_posix()
        old_to_new[old_url] = new_url
        print(f"{old_url} -> {new_url}")

    html = index.read_text(encoding="utf-8")

    # Rewrite the generated Unity config only; do not rewrite compressed
    # user-supplied URLs or other unrelated HTML attributes.
    def replace_url(match: re.Match[str]) -> str:
        url = match.group("url")
        new_url = old_to_new.get(url, url)
        return match.group(0).replace(url, new_url)

    html = UNITY_URL.sub(replace_url, html)
    index.write_text(html, encoding="utf-8")

    configs = list(UNITY_URL.finditer(html))
    configured_urls = {match.group("url") for match in configs}
    if not any("framework.js" in u for u in configured_urls):
        raise ValueError("Unity WebGL frameworkUrl is missing from index.html")
    if not any(".data" in u for u in configured_urls):
        raise ValueError("Unity WebGL dataUrl is missing from index.html")

    for url in configured_urls:
        if url.endswith(tuple(COMPRESSED_SUFFIXES)):
            raise ValueError(f"Unity URL still points to compressed data: {url}")
        if not (site / url).is_file():
            raise FileNotFoundError(f"Missing Unity WebGL asset referenced in index.html: {url}")

    print(f"Checked {len(configured_urls)} Unity URLs; "
          f"normalized {len(old_to_new)} compressed files.")
    return old_to_new


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, help="Directory with WebGL index.html and Build/")
    args = parser.parse_args()
    normalize(args.site)
