"""Get the rendered slides onto a public HTTPS URL.

Meta fetches image_url from its own servers, so the slides have to be publicly
readable before either publisher runs. Two backends:

  s3      any S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2)
  hosted  the files are already served from ASSET_BASE_URL by something else
          (a static site, a CDN you sync separately) — this just builds URLs

boto3 is imported lazily so the s3 backend costs nothing if you use hosted.
"""
from __future__ import annotations

import os
import pathlib


class UploadError(RuntimeError):
    pass


def slide_files(slides_dir: pathlib.Path) -> list[pathlib.Path]:
    """The rendered slides, in publish order, excluding review artefacts."""
    return sorted(
        p for p in pathlib.Path(slides_dir).glob("*.jpg")
        if not p.name.startswith("sheet")
    )


def upload_hosted(files: list[pathlib.Path], prefix: str) -> list[str]:
    base = os.environ.get("ASSET_BASE_URL", "").rstrip("/")
    if not base:
        raise UploadError("ASSET_BASE_URL is not set — see .env.example")
    if not base.startswith("https://"):
        raise UploadError(f"ASSET_BASE_URL must be https, got {base!r}")
    return [f"{base}/{prefix}/{f.name}" for f in files]


def upload_s3(files: list[pathlib.Path], prefix: str) -> list[str]:
    try:
        import boto3
    except ImportError as exc:
        raise UploadError("the s3 backend needs boto3: pip install boto3") from exc

    bucket = os.environ.get("ASSET_BUCKET")
    if not bucket:
        raise UploadError("ASSET_BUCKET is not set")

    session = boto3.session.Session()
    client = session.client(
        "s3",
        endpoint_url=os.environ.get("ASSET_ENDPOINT_URL") or None,  # R2/B2
        region_name=os.environ.get("ASSET_REGION") or None,
    )

    urls = []
    for f in files:
        key = f"{prefix}/{f.name}"
        client.upload_file(
            str(f), bucket, key,
            ExtraArgs={"ContentType": "image/jpeg", "CacheControl": "public, max-age=31536000"},
        )
        urls.append(f"{os.environ['ASSET_BASE_URL'].rstrip('/')}/{key}")
    return urls


def upload(files: list[pathlib.Path], prefix: str, backend: str = "s3") -> list[str]:
    if not files:
        raise UploadError("nothing to upload — has the drop been rendered?")
    if backend == "hosted":
        return upload_hosted(files, prefix)
    if backend == "s3":
        return upload_s3(files, prefix)
    raise UploadError(f"unknown backend {backend!r}; use 's3' or 'hosted'")
