"""Unit tests for livestock encyclopedia image URL rewriting."""

import importlib


def _reload_livestock(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    import app.routers.livestock as livestock

    return importlib.reload(livestock)


def test_fix_image_url_uses_legacy_uploads_by_default(monkeypatch):
    livestock = _reload_livestock(
        monkeypatch,
        USE_GCS_LIVESTOCK_IMAGES="false",
        LIVESTOCK_LEGACY_UPLOADS_URL="https://livestockoftheworld.com/uploads",
    )
    assert (
        livestock._fix_image_url("205593HuacayaExample.webp")
        == "https://livestockoftheworld.com/uploads/205593HuacayaExample.webp"
    )
    assert (
        livestock._fix_image_url(
            "https://storage.googleapis.com/oatmeal-farm-network-images/Animals/205593HuacayaExample.webp"
        )
        == "https://livestockoftheworld.com/uploads/205593HuacayaExample.webp"
    )


def test_fix_image_url_can_use_gcs(monkeypatch):
    livestock = _reload_livestock(
        monkeypatch,
        USE_GCS_LIVESTOCK_IMAGES="true",
        GCS_LIVESTOCK_IMAGES_BUCKET="oatmeal-farm-network-images",
    )
    assert (
        livestock._fix_image_url("205593HuacayaExample.webp")
        == "https://storage.googleapis.com/oatmeal-farm-network-images/Animals/205593HuacayaExample.webp"
    )


def test_safe_text_strips_nuls(monkeypatch):
    livestock = _reload_livestock(monkeypatch, USE_GCS_LIVESTOCK_IMAGES="false")
    assert livestock._safe_text("abc\x00def") == "abcdef"
    assert livestock._safe_text(None) is None
