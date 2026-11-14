"""Branding: curated colour slots, upload validation and safe asset serving."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.api.endpoints import customization
from app.main import app


@pytest.mark.parametrize("brand", [
    {"action_color": "#312d2a", "mark_color": "#c74634"},  # Design.md defaults
    {"action_color": None},                                 # cleared slot
    {},
])
def test_accessible_brand_colours_pass(brand):
    customization.validate_brand_settings({"brand": brand, "other": 1})


@pytest.mark.parametrize("brand, message", [
    ({"action_color": "#7fb3ff"}, "too light"),     # white button text would fail AA
    ({"mark_color": "#ffd166"}, "too light"),
    ({"action_color": "blue"}, "must be a colour"),
    ({"action_color": "#12345"}, "must be a colour"),
    ({"accent": "#000000"}, "Unknown brand setting"),
])
def test_inaccessible_or_malformed_brand_colours_are_refused(brand, message):
    with pytest.raises(HTTPException) as exc:
        customization.validate_brand_settings({"brand": brand})
    assert exc.value.status_code == 422 and message in exc.value.detail


def test_contrast_maths_matches_wcag():
    assert customization.contrast_with_white("#000000") == pytest.approx(21.0)
    assert customization.contrast_with_white("#ffffff") == pytest.approx(1.0)
    assert customization.contrast_with_white("#767676") == pytest.approx(4.54, abs=0.01)


def _upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(file=BytesIO(data), filename=name, headers=Headers({}))


@pytest.mark.parametrize("name, data", [
    ("logo.png", b"\x89PNG\r\n\x1a\n" + b"\0" * 32),
    ("logo.jpg", b"\xff\xd8\xff\xe0" + b"\0" * 32),
    ("logo.svg", b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
    ("logo.webp", b"RIFF\0\0\0\0WEBPVP8 " + b"\0" * 16),
    ("favicon.ico", b"\x00\x00\x01\x00" + b"\0" * 16),
])
def test_real_images_are_accepted(name, data):
    customization.validate_image_file(_upload(name, data))


@pytest.mark.parametrize("name, data", [
    ("logo.png", b"<html><script>alert(1)</script></html>"),  # renamed HTML
    ("logo.svg", b"<html><svg></svg></html>"),
    ("logo.gif", b"GIF89a"),
])
def test_disguised_or_unsupported_files_are_refused(name, data):
    with pytest.raises(HTTPException) as exc:
        customization.validate_image_file(_upload(name, data))
    assert exc.value.status_code == 400


async def test_uploaded_name_cannot_escape_the_branding_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(customization, "UPLOAD_DIR", tmp_path)
    url = await customization.save_uploaded_file(_upload("x.png", b"\x89PNG\r\n\x1a\n"), uuid4(), "light")
    saved = list(tmp_path.iterdir())
    assert len(saved) == 1 and url == f"/uploads/branding/{saved[0].name}"
    assert "/" not in saved[0].name and ".." not in saved[0].name


async def test_branding_assets_are_served_sandboxed():
    folder = Path(customization.UPLOAD_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    asset = folder / f"test-{uuid4().hex}.svg"
    asset.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            response = await client.get(f"/uploads/branding/{asset.name}")
        assert response.status_code == 200
        assert "sandbox" in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"
    finally:
        asset.unlink(missing_ok=True)
