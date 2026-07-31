"""Unit tests for marketplace photo URL helpers (animal detail 500 regression)."""

from app.routers.marketplace import _photo_url, _fix_animal_url, _GCS_ANIMALS


def test_photo_url_none_and_empty():
    assert _photo_url(None) is None
    assert _photo_url("") is None
    assert _photo_url("0") is None
    assert _photo_url("ab") is None


def test_photo_url_bare_filename():
    url = _photo_url("HolsteinCow.webp")
    assert url == f"{_GCS_ANIMALS}/HolsteinCow.webp"


def test_photo_url_already_gcs():
    full = f"{_GCS_ANIMALS}/already.webp"
    assert _photo_url(full) == full


def test_photo_url_matches_fix_animal_url():
    assert _photo_url("subdir/animal.webp") == _fix_animal_url("subdir/animal.webp")


def test_photo_url_does_not_raise_on_gcs_prefix():
    """Regression: old _photo_url referenced undefined _GCS_PREFIX (NameError → 500)."""
    url = _photo_url("c089b87339b04719b01defc742a0ff65.webp")
    assert url is not None
    assert url.startswith("https://storage.googleapis.com/")
