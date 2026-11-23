"""Layout rules for the frontend CSS and the CSS of every example app's ui.

Convention: "secondary" text is any element carrying the `secondary` class. Components render
into the light DOM, so every sizing rule lives in a .css file and is checked here.

Decision on touch targets: buttons need a minimum height of 48px, written as `min-height: 3rem`
(the root font size is never changed, so 3rem is 48px). A `min-height` in px stays forbidden like
every other px height, and buttons must inherit the page font (`font: inherit`), because browsers
default buttons to about 13px.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
BASE_FONT_PX = 18
SECONDARY_FONT_PX = 15
MIN_BUTTON_HEIGHT_REM = 3

# Each set is checked on its own: a page is only as good as its own CSS.
CSS_SETS = {
    "launcher": REPO_ROOT / "launcher" / "frontend" / "styles",
    "hello_py": REPO_ROOT / "apps" / "hello_py" / "ui",
    "hello_js": REPO_ROOT / "apps" / "hello_js" / "ui",
}
# stop-button.css is loaded by app pages too, so it counts for them as well.
SHARED_CSS = [REPO_ROOT / "launcher" / "frontend" / "styles" / "stop-button.css"]


def css_files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("*.css"))
    assert files, f"no CSS found in {directory}"
    return files


def read_css(directory: Path) -> str:
    return "\n".join(f.read_text(encoding="utf-8") for f in css_files(directory))


def rules(css: str) -> list[tuple[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(s.strip(), b) for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def font_sizes(css: str, selector_pattern: str) -> list[int]:
    sizes = []
    for selector, body in rules(css):
        if re.search(selector_pattern, selector):
            sizes += [int(v) for v in re.findall(r"font-size\s*:\s*(\d+)px", body)]
    return sizes


@pytest.fixture(params=CSS_SETS)
def css(request) -> str:
    return read_css(CSS_SETS[request.param])


def test_css_sets_exist_for_launcher_and_both_example_apps():
    assert set(CSS_SETS) == {"launcher", "hello_py", "hello_js"}
    assert len(list((REPO_ROOT / "apps").glob("*/ui"))) == 2


def test_no_max_width(css):
    assert not re.search(r"max-width", css)


def test_no_auto_margin_centring(css):
    assert not re.search(r"margin[^;{}]*:[^;{}]*\bauto\b", css)


def test_no_fixed_px_heights(css):
    assert not re.search(r"(?<![\w-])(?:min-|max-)?height\s*:\s*\d+px", css)


def test_page_fills_viewport(css):
    html_body = [b for s, b in rules(css) if "html" in s and "body" in s]
    assert html_body and "height: 100%" in html_body[0]


def test_base_font_size(css):
    assert font_sizes(css, r"\bbody\b") and min(font_sizes(css, r"\bbody\b")) >= BASE_FONT_PX


def test_secondary_font_size(css):
    sizes = font_sizes(css, r"\.secondary\b")
    assert sizes and min(sizes) >= SECONDARY_FONT_PX


def test_no_font_size_below_secondary_minimum(css):
    all_sizes = [int(v) for v in re.findall(r"font-size\s*:\s*(\d+)px", css)]
    assert all_sizes and min(all_sizes) >= SECONDARY_FONT_PX


def test_buttons_are_touch_sized_and_use_the_page_font():
    css = read_css(CSS_SETS["launcher"])
    button_rules = [(s, b) for s, b in rules(css) if re.search(r"(?<![\w-])button(?![\w-])", s)]
    assert button_rules
    for selector, body in button_rules:
        height = re.search(r"min-height\s*:\s*([\d.]+)rem", body)
        assert height and float(height.group(1)) >= MIN_BUTTON_HEIGHT_REM, selector
        assert re.search(r"font\s*:\s*inherit", body), selector


def test_shared_widget_css_follows_the_same_button_rules():
    for path in SHARED_CSS:
        for selector, body in rules(path.read_text(encoding="utf-8")):
            if re.search(r"(?<![\w-])button(?![\w-])", selector):
                assert re.search(r"min-height\s*:\s*3(\.\d+)?rem", body), selector
                assert re.search(r"font\s*:\s*inherit", body), selector
