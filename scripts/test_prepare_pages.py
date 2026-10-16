"""Regression tests for GitHub Pages Unity compression handling."""

import gzip
import sys
import tempfile
import unittest
from pathlib import Path

import brotli

sys.path.insert(0, str(Path(__file__).parent))
from prepare_pages import normalize


def make_site(folder, files, configured):
    build = folder / "Build"
    build.mkdir()
    for filename, payload in files.items():
        (build / filename).write_bytes(payload)
    urls = "\n".join(f'  {key}: "Build/{filename}",' for key, filename in configured.items())
    (folder / "index.html").write_text(
        "<html><script>const config = {\n" + urls + "\n};</script></html>",
        encoding="utf-8",
    )


class PreparePagesTests(unittest.TestCase):
    def test_brotli_is_decompressed_and_urls_rewritten(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            data = b"data-file" * 100
            script = b"console.log('it works')"
            make_site(site, {
                "ArcViewer.data.br": brotli.compress(data),
                "ArcViewer.framework.js.br": brotli.compress(script),
                "ArcViewer.wasm.br": brotli.compress(b"\x00asm"),
            }, {
                "dataUrl": "ArcViewer.data.br",
                "frameworkUrl": "ArcViewer.framework.js.br",
                "codeUrl": "ArcViewer.wasm.br",
            })
            normalize(site)
            self.assertEqual((site / "Build/ArcViewer.data").read_bytes(), data)
            self.assertEqual((site / "Build/ArcViewer.framework.js").read_bytes(), script)
            self.assertEqual((site / "Build/ArcViewer.wasm").read_bytes(), b"\x00asm")
            self.assertNotIn(".br", (site / "index.html").read_text())
            self.assertFalse((site / "Build/ArcViewer.data.br").exists())

    def test_gzip_is_decompressed(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            make_site(site, {
                "ArcViewer.data.gz": gzip.compress(b"hello"),
                "ArcViewer.framework.js.gz": gzip.compress(b"console.log(1)"),
            }, {
                "dataUrl": "ArcViewer.data.gz",
                "frameworkUrl": "ArcViewer.framework.js.gz",
            })
            normalize(site)
            self.assertEqual((site / "Build/ArcViewer.data").read_bytes(), b"hello")
            self.assertFalse((site / "Build/ArcViewer.data.gz").exists())

    def test_uncompressed_build_remains_intact(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            make_site(site, {
                "ArcViewer.data": b"hello",
                "ArcViewer.framework.js": b"console.log(1)",
            }, {
                "dataUrl": "ArcViewer.data",
                "frameworkUrl": "ArcViewer.framework.js",
            })
            self.assertEqual(normalize(site), {})
            self.assertEqual((site / "Build/ArcViewer.data").read_bytes(), b"hello")

    def test_fails_for_missing_referenced_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            make_site(site, {
                "ArcViewer.data": b"hello",
            }, {
                "dataUrl": "ArcViewer.data",
                "frameworkUrl": "ArcViewer.framework.js",
            })
            with self.assertRaises(FileNotFoundError):
                normalize(site)


if __name__ == "__main__":
    unittest.main()
