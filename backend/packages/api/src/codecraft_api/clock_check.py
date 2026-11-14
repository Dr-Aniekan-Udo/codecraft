"""Fail-safe startup check for a badly skewed system clock.

The public endpoint returns no body; its HTTP Date header is the time source.
A missing or unusable answer is not an error: the API starts normally and says
the check was skipped.
"""

import asyncio
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

_TIME_SOURCE_URL = "https://www.google.com/generate_204"
_TIMEOUT_SECONDS = 5.0
_MAX_SKEW_SECONDS = 60.0


async def check_clock(client: httpx.AsyncClient | None = None) -> None:
    """Compare local time with a public HTTP Date header; never raise."""
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)

    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            response = await client.get(_TIME_SOURCE_URL)
        date_header = response.headers.get("date")
        if date_header is None:
            raise ValueError("missing Date header")
        remote_time = parsedate_to_datetime(date_header)
        if remote_time.tzinfo is None:
            remote_time = remote_time.replace(tzinfo=UTC)
        difference = abs((datetime.now(UTC) - remote_time).total_seconds())
        if difference > _MAX_SKEW_SECONDS:
            logger.warning(
                "Clock differs from %s by %.0f seconds; "
                "tokens may be rejected because of the clock.",
                _TIME_SOURCE_URL,
                difference,
            )
    except Exception:
        # This check is advisory. It must not prevent the API from starting.
        logger.info("Clock check skipped: time source could not be reached.")
    finally:
        if owns_client:
            await client.aclose()
