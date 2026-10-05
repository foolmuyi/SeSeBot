import json
import logging
import time
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def fetch_response(
    request_func,
    *,
    url,
    attempts=4,
    timeout=None,
    error_message="Request failed",
    retry_delay=0,
    **kwargs,
):
    last_exc = None
    for attempt in range(1, attempts + 1):
        response = None
        try:
            logger.info("Fetching %s (attempt %s/%s)", url, attempt, attempts)
            if timeout is not None:
                response = request_func(url=url, timeout=timeout, **kwargs)
            else:
                response = request_func(url=url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                logger.warning(
                    "Request failed for %s on attempt %s/%s: %s",
                    url,
                    attempt,
                    attempts,
                    exc,
                )
                if retry_delay > 0:
                    delay = retry_delay * (2 ** (attempt - 1))
                    if response is not None and response.status_code in (429, 503):
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                server_delay = float(retry_after)
                            except ValueError:
                                try:
                                    server_delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
                                except (TypeError, ValueError, OverflowError):
                                    server_delay = 0
                            delay = max(delay, server_delay)
                    logger.info("Retrying %s in %.1f seconds", url, delay)
                    time.sleep(delay)
            else:
                logger.exception("Request failed for %s after %s attempts", url, attempts)
    raise ValueError(f"{error_message}: {last_exc}") from last_exc


def fetch_json(
    request_func,
    *,
    url,
    attempts=4,
    timeout=None,
    error_message="Request failed",
    **kwargs,
):
    response = fetch_response(
        request_func,
        url=url,
        attempts=attempts,
        timeout=timeout,
        error_message=error_message,
        **kwargs,
    )
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ValueError(f"{error_message}: invalid JSON response") from exc
