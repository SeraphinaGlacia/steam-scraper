import ssl

import pytest

from steam_scraper.utils.http_client import AsyncHttpClient


@pytest.mark.asyncio
async def test_http_client_requires_trusted_certificate_and_hostname(app_config):
    wrapper = AsyncHttpClient(app_config)
    try:
        client = await wrapper._get_client()
        context = client._transport._pool._ssl_context
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
    finally:
        await wrapper.close()


@pytest.mark.asyncio
async def test_http_client_uses_standard_ca_environment(
    app_config, monkeypatch, tmp_path
):
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing-ca.pem"))
    wrapper = AsyncHttpClient(app_config)
    try:
        # CA 配置错误必须可见，不能因跳过验证而被静默忽略。
        with pytest.raises(FileNotFoundError):
            await wrapper._get_client()
    finally:
        await wrapper.close()
