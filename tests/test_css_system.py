import re
import unittest
from pathlib import Path


class CssSystemTests(unittest.TestCase):
    def test_raw_color_literals_live_only_in_tokens(self):
        css_dir = Path(__file__).resolve().parents[1] / "app" / "static" / "css"
        offenders = {}
        for path in css_dir.glob("*.css"):
            if path.name == "tokens.css":
                continue
            matches = re.findall(
                r"#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])|(?<!var\()\b(?:rgba?|hsla?)\(",
                path.read_text(encoding="utf-8-sig"),
                flags=re.IGNORECASE,
            )
            if matches:
                offenders[path.name] = matches
        self.assertEqual(offenders, {})

    def test_every_custom_property_reference_is_defined(self):
        css_dir = Path(__file__).resolve().parents[1] / "app" / "static" / "css"
        contents = "\n".join(
            path.read_text(encoding="utf-8-sig") for path in css_dir.glob("*.css")
        )
        defined = set(re.findall(r"(--[\w-]+)\s*:", contents))
        referenced = set(re.findall(r"var\(\s*(--[\w-]+)", contents))
        # These three are intentionally supplied inline by the map renderers.
        runtime_properties = {"--marker-size", "--marker-color", "--chapter-color"}
        self.assertEqual(referenced - defined - runtime_properties, set())

    def test_retired_theme_is_not_reintroduced(self):
        static_dir = Path(__file__).resolve().parents[1] / "app" / "static"
        self.assertFalse((static_dir / "css" / "theme.css").exists())
        base = (Path(__file__).resolve().parents[1] / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("css/tokens.css", base)
        self.assertNotIn("css/theme.css", base)

    def test_header_geometry_has_one_source_of_truth(self):
        css_dir = Path(__file__).resolve().parents[1] / "app" / "static" / "css"
        page_css = "\n".join(
            path.read_text(encoding="utf-8-sig")
            for path in css_dir.glob("*.css")
            if path.name not in {"tokens.css", "components.css"}
        )
        self.assertNotRegex(page_css, r"(?:padding-top|margin-top|top|inset|height)[^;{}]*(?:104|108|132|156)px")

    def test_component_layer_declares_no_raw_values(self):
        """components.css loads last, so a raw value there silently wins
        sitewide. Tokens only - this is rule 1 of its documented contract."""
        css = (Path(__file__).resolve().parents[1]
               / "app" / "static" / "css" / "components.css").read_text(encoding="utf-8-sig")
        body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        raw_colour = re.findall(r"#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])|rgba?\(\s*\d|hsla?\(\s*\d", body)
        self.assertEqual(raw_colour, [], "components.css must use tokens, not raw colours")
        self.assertNotIn("!important", body)

    def test_no_stylesheet_uses_important(self):
        """The override-by-force pattern that theme.css needed must not return."""
        css_dir = Path(__file__).resolve().parents[1] / "app" / "static" / "css"
        offenders = []
        for path in css_dir.glob("*.css"):
            body = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8-sig"), flags=re.S)
            if "!important" in body:
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_no_full_width_rule_pinned_across_content(self):
        """A pseudo-element line pinned at a fixed top offset and stretched
        left-to-right strikes through whatever happens to sit at that height.
        This shipped twice: the homepage timeline axis and the map chapter
        controls (BUILD_STATUS.md:177). Decorative tree connectors are exempt -
        they are short segments, not full-width rules."""
        css_dir = Path(__file__).resolve().parents[1] / "app" / "static" / "css"
        offenders = []
        for path in css_dir.glob("*.css"):
            body = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8-sig"), flags=re.S)
            for m in re.finditer(r"([^{}]*:(?:before|after)[^{}]*)\{([^}]*)\}", body):
                rule = m.group(2)
                if "position:absolute" not in rule.replace(" ", ""):
                    continue
                flat = rule.replace(" ", "")
                spans = "left:0" in flat and "right:0" in flat
                pinned = re.search(r"top:(\d+px|\d+%)", flat)
                if spans and pinned and "border-top" in flat:
                    offenders.append(f"{path.name}: {m.group(1).strip()[:48]}")
        self.assertEqual(offenders, [])
