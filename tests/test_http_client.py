import pytest

from steam_scraper.config import Config, HttpConfig
from steam_scraper.utils.http_client import AsyncHttpClient


@pytest.mark.asyncio
async def test_async_client_rejects_negative_retry_count() -> None:
    client = AsyncHttpClient(Config(http=HttpConfig(max_retries=-1)))

    try:
        with pytest.raises(ValueError, match="不能小于 0"):
            await client.get("https://example.invalid", delay=False)
    finally:
        await client.close()
