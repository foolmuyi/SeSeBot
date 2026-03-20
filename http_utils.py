import json
import traceback


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
            print(f"Fetching {url} (attempt {attempt}/{attempts})")
            if timeout is not None:
                response = request_func(url=url, timeout=timeout, **kwargs)
            else:
                response = request_func(url=url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exc = exc
            traceback.print_exc()
    raise ValueError(f"{error_message}: {last_exc}")


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
