import json
import logging

logger = logging.getLogger(__name__)


def fetch_response(
    request_func,
    *,
    url,
    attempts=4,
    timeout=None,
    error_message="Request failed",
    **kwargs,
):
    last_exc = None
    for attempt in range(1, attempts + 1):
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
