"""Entry-point smoke test for provider discovery."""

from __future__ import annotations

from importlib.metadata import entry_points

from companyctx.providers import ENTRY_POINT_GROUP, discover


def test_site_text_trafilatura_is_registered_via_entry_point() -> None:
    found = {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}
    assert found["site_text_trafilatura"] == "companyctx.providers.site_text_trafilatura:Provider"
    assert "site_text_trafilatura" in discover()


def test_reviews_google_places_is_registered_via_entry_point() -> None:
    found = {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}
    assert found["reviews_google_places"] == "companyctx.providers.reviews_google_places:Provider"
    assert "reviews_google_places" in discover()
