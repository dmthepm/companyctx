"""Unit tests for the high-confidence ``detect_tech_stack`` detector.

Scope per COX-43 / #78: bare substring mentions of a framework name in
prose, HTML comments, or unrelated third-party widget src URLs must NOT
produce a detection. Only the three high-confidence signal classes fire:

1. ``<meta name="generator">`` declarations
2. framework-owned asset hostnames / paths in ``<script src>`` /
   ``<link href>``
3. framework-specific class tokens or ``data-*`` attributes on
   ``<html>`` / ``<body>``

These tests pin the contract per tech and lock the false-positive shape
from the RC-dogfood report.
"""

from __future__ import annotations

import pytest

from companyctx.extract import detect_tech_stack


def _wrap(head: str = "", body_attrs: str = "", body_html: str = "") -> str:
    return (
        "<!DOCTYPE html>"
        f"<html><head>{head}</head>"
        f"<body{(' ' + body_attrs) if body_attrs else ''}>{body_html}</body>"
        "</html>"
    )


class TestWordPress:
    def test_generator_meta_fires(self) -> None:
        html = _wrap(head='<meta name="generator" content="WordPress 6.4">')
        assert "WordPress" in detect_tech_stack(html)

    def test_wp_content_asset_url_fires(self) -> None:
        html = _wrap(head='<link rel="stylesheet" href="/wp-content/themes/x/style.css">')
        assert "WordPress" in detect_tech_stack(html)

    def test_wp_includes_asset_url_fires(self) -> None:
        html = _wrap(head='<script src="/wp-includes/js/jquery/jquery.min.js"></script>')
        assert "WordPress" in detect_tech_stack(html)

    def test_prose_mention_does_not_fire(self) -> None:
        html = _wrap(body_html="<p>We used to run on WordPress but migrated.</p>")
        assert "WordPress" not in detect_tech_stack(html)

    def test_third_party_widget_name_does_not_fire(self) -> None:
        html = _wrap(
            head='<script src="https://cdn.thirdparty.example/wordpress-importer.js"></script>'
        )
        assert "WordPress" not in detect_tech_stack(html)

    def test_html_comment_does_not_fire(self) -> None:
        html = _wrap(head="<!-- we migrated off WordPress in 2019 -->")
        assert "WordPress" not in detect_tech_stack(html)


class TestElementor:
    def test_generator_meta_fires(self) -> None:
        html = _wrap(head='<meta name="generator" content="Elementor 3.21.0">')
        assert "Elementor" in detect_tech_stack(html)

    def test_wp_elementor_body_class_fires(self) -> None:
        html = _wrap(body_attrs='class="wp-elementor"')
        assert "Elementor" in detect_tech_stack(html)

    def test_elementor_prefix_class_fires(self) -> None:
        html = _wrap(body_attrs='class="elementor-default elementor-kit-7"')
        assert "Elementor" in detect_tech_stack(html)

    def test_plugin_asset_path_fires(self) -> None:
        href = "/wp-content/plugins/elementor/assets/css/frontend.min.css"
        html = _wrap(head=f'<link rel="stylesheet" href="{href}">')
        assert "Elementor" in detect_tech_stack(html)

    def test_substring_class_does_not_fire(self) -> None:
        html = _wrap(body_attrs='class="content-elementor-like panel"')
        assert "Elementor" not in detect_tech_stack(html)

    def test_prose_mention_does_not_fire(self) -> None:
        html = _wrap(body_html="<p>We also considered WordPress with Elementor.</p>")
        assert "Elementor" not in detect_tech_stack(html)


class TestShopify:
    def test_generator_meta_fires(self) -> None:
        html = _wrap(head='<meta name="generator" content="Shopify">')
        assert "Shopify" in detect_tech_stack(html)

    def test_shopify_cdn_asset_fires(self) -> None:
        html = _wrap(head='<script src="https://cdn.shopify.com/s/files/app.js"></script>')
        assert "Shopify" in detect_tech_stack(html)

    def test_myshopify_hostname_fires(self) -> None:
        html = _wrap(head='<link rel="canonical" href="https://store.myshopify.com/">')
        # link href is treated as an asset URL for fingerprinting purposes.
        assert "Shopify" in detect_tech_stack(html)

    def test_prose_mention_does_not_fire(self) -> None:
        html = _wrap(body_html="<p>We evaluated Shopify for e-commerce.</p>")
        assert "Shopify" not in detect_tech_stack(html)

    def test_third_party_widget_named_shopify_does_not_fire(self) -> None:
        html = _wrap(
            head='<script src="https://cdn.thirdparty.example/shopify-share-widget.js"></script>'
        )
        assert "Shopify" not in detect_tech_stack(html)

    def test_html_comment_does_not_fire(self) -> None:
        html = _wrap(head="<!-- legacy: migrated off Shopify in 2019 -->")
        assert "Shopify" not in detect_tech_stack(html)


class TestSquarespace:
    def test_generator_meta_fires(self) -> None:
        html = _wrap(head='<meta name="generator" content="Squarespace 7.1">')
        assert "Squarespace" in detect_tech_stack(html)

    def test_squarespace_cdn_asset_fires(self) -> None:
        html = _wrap(
            head='<link rel="stylesheet" href="https://static1.squarespace.com/static/app.css">'
        )
        assert "Squarespace" in detect_tech_stack(html)

    def test_sqs_site_class_fires(self) -> None:
        html = _wrap(body_attrs='class="sqs-site"')
        assert "Squarespace" in detect_tech_stack(html)

    def test_sqs_site_prefix_class_fires(self) -> None:
        html = _wrap(body_attrs='class="sqs-site-canvas extra"')
        assert "Squarespace" in detect_tech_stack(html)

    def test_prose_mention_does_not_fire(self) -> None:
        html = _wrap(body_html="<p>Squarespace for templates was one option.</p>")
        assert "Squarespace" not in detect_tech_stack(html)


class TestWix:
    def test_generator_meta_fires(self) -> None:
        html = _wrap(head='<meta name="generator" content="Wix.com Website Builder">')
        assert "Wix" in detect_tech_stack(html)

    def test_wixstatic_asset_fires(self) -> None:
        html = _wrap(head='<script src="https://static.wixstatic.com/app.js"></script>')
        assert "Wix" in detect_tech_stack(html)

    def test_wix_site_class_fires(self) -> None:
        html = _wrap(body_attrs='class="wix-site"')
        assert "Wix" in detect_tech_stack(html)

    def test_prose_mention_does_not_fire(self) -> None:
        html = _wrap(body_html="<p>Wix for drag-and-drop was considered.</p>")
        assert "Wix" not in detect_tech_stack(html)


class TestWebflow:
    def test_generator_meta_fires(self) -> None:
        html = _wrap(head='<meta name="generator" content="Webflow">')
        assert "Webflow" in detect_tech_stack(html)

    def test_data_wf_site_attr_fires(self) -> None:
        html = '<!DOCTYPE html><html data-wf-site="abc123"><head></head><body></body></html>'
        assert "Webflow" in detect_tech_stack(html)

    def test_website_files_cdn_fires(self) -> None:
        html = _wrap(head='<link rel="stylesheet" href="https://assets.website-files.com/app.css">')
        assert "Webflow" in detect_tech_stack(html)

    def test_prose_mention_does_not_fire(self) -> None:
        html = _wrap(body_html="<p>Webflow for design control was on the list.</p>")
        assert "Webflow" not in detect_tech_stack(html)


def test_rc_dogfood_false_positive_class_returns_empty() -> None:
    """The v0.2.0 RC dogfood surfaced `[WordPress, Shopify, Squarespace]` on
    a single site. The three-way simultaneous hit is the diagnostic
    signature of substring matching. The detector must return an empty
    list on a page that only *mentions* these frameworks.
    """
    html = (
        "<!DOCTYPE html>"
        "<html><head>"
        "<!-- legacy: migrated off Shopify in 2019 -->"
        '<meta name="description" content="We reviewed WordPress, Squarespace, Wix, and Webflow.">'
        '<script src="https://cdn.thirdparty.example/shopify-share-widget.js"></script>'
        '<script src="https://cdn.thirdparty.example/wordpress-importer.js"></script>'
        '<link rel="stylesheet" href="https://cdn.thirdparty.example/squarespace-like-theme.css">'
        '</head><body class="site-root">'
        "<p>We evaluated Shopify, Squarespace, Wix, Webflow, and WordPress + Elementor.</p>"
        "</body></html>"
    )
    assert detect_tech_stack(html) == []


def test_empty_html_returns_empty() -> None:
    assert detect_tech_stack("") == []


def test_malformed_html_does_not_raise() -> None:
    # BS4 parses aggressively; detector should tolerate partials without error.
    detect_tech_stack("<html><body><p>unterminated")


@pytest.mark.parametrize(
    "body_class",
    [
        "wp-elementor",
        "elementor-default",
        "elementor",
    ],
)
def test_elementor_class_variants(body_class: str) -> None:
    html = _wrap(body_attrs=f'class="{body_class}"')
    assert "Elementor" in detect_tech_stack(html)


@pytest.mark.parametrize(
    "body_class",
    [
        "content-elementor-like",
        "pre-wix-site-2",
        "not-sqs-site",
    ],
)
def test_class_substring_traps_do_not_fire(body_class: str) -> None:
    html = _wrap(body_attrs=f'class="{body_class}"')
    assert detect_tech_stack(html) == []
