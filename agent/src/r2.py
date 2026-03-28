"""R2 存储客户端 — Cloudflare R2 (S3-compatible)"""

import os
import httpx
import boto3
from urllib.parse import urlparse
from botocore.config import Config

# ── boto3 客户端单例 ────────────────────────────────────────────────

_r2_client = None
_r2_client_config = None


def get_r2_client():
    """获取 R2 客户端 (单例模式, 线程安全)"""
    global _r2_client, _r2_client_config

    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY")
    secret_key = os.getenv("R2_SECRET_KEY")
    if not (account_id and access_key and secret_key):
        return None

    # 配置指纹，配置变更时重建客户端
    config_sig = (account_id, access_key, secret_key)
    if _r2_client is not None and _r2_client_config == config_sig:
        return _r2_client

    config = Config(
        connect_timeout=30,
        read_timeout=300,
        retries={"max_attempts": 3, "mode": "adaptive"},
        max_pool_connections=50,
    )

    _r2_client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=config,
    )
    _r2_client_config = config_sig
    return _r2_client


async def upload_url_to_r2(url: str, key: str, bucket: str = None) -> str:
    bucket = bucket or os.getenv("R2_BUCKET", "video")
    r2 = get_r2_client()
    if not r2:
        return url
    content: bytes
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(url)
            r.raise_for_status()
            content = r.content
    elif parsed.scheme == "file":
        path = parsed.path
        with open(path, "rb") as f:
            content = f.read()
    else:
        try:
            with open(url, "rb") as f:
                content = f.read()
        except Exception:
            return url
    r2.put_object(Bucket=bucket, Key=key, Body=content, ContentType="video/mp4")
    public_base = os.getenv("R2_PUBLIC_BASE")
    if public_base:
        return f"{public_base.rstrip('/')}/{key}"
    account_id = os.getenv("R2_ACCOUNT_ID")
    return f"https://pub-{account_id}.r2.dev/{key}"


def presign_put_url(
    key: str,
    bucket: str = None,
    content_type: str = "application/octet-stream",
    expires: int = 3600,
) -> dict:
    """生成 Cloudflare R2 的预签名 PUT URL，用于浏览器直传大文件。"""
    bucket = bucket or os.getenv("R2_BUCKET", "video")
    r2 = get_r2_client()
    if not r2:
        raise RuntimeError("R2 is not configured")
    url = r2.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )
    public_base = os.getenv("R2_PUBLIC_BASE")
    if public_base:
        public_url = f"{public_base.rstrip('/')}/{key}"
    else:
        account_id = os.getenv("R2_ACCOUNT_ID")
        public_url = f"https://pub-{account_id}.r2.dev/{key}"
    return {
        "upload_url": url,
        "key": key,
        "bucket": bucket,
        "headers": {"Content-Type": content_type},
        "public_url": public_url,
    }


async def upload_bytes_to_r2(
    data: bytes,
    key: str,
    content_type: str = "application/octet-stream",
    bucket: str = None,
) -> str:
    """上传字节数据到 R2，返回公网 CDN URL"""
    bucket = bucket or os.getenv("R2_BUCKET", "video")
    r2 = get_r2_client()
    if not r2:
        raise RuntimeError("R2 is not configured")
    r2.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    public_base = os.getenv("R2_PUBLIC_BASE")
    if public_base:
        return f"{public_base.rstrip('/')}/{key}"
    account_id = os.getenv("R2_ACCOUNT_ID")
    return f"https://pub-{account_id}.r2.dev/{key}"
