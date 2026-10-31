"""Fixtures shared by the provider-native search tests: the vendor's own reply shape."""

from __future__ import annotations

import json

# The vendor's own documented reply, trimmed to two citations.
OBSERVED_SEARCH_RESPONSE = {
    "id": "9ffcbd3a-d3a2-4788-9edd-d8a79e47ae15_33e773cc83af482aa0b41b9fd120fdf1",
    "choices": [{
        "finish_reason": "stop",
        "index": 0,
        "message": {
            "content": "Wuhan tomorrow will be overcast with local showers, 22-25 C.",
            "role": "assistant",
            "annotations": [
                {
                    "type": "url_citation",
                    "url": "https://www.weather.com.cn/weather/101200101.shtml",
                    "title": "Wuhan weather forecast",
                    "summary": "Central Meteorological Observatory weather information.",
                    "site_name": "weather.com.cn",
                    "publish_time": "2026-09-21T08:32:25.0000000",
                    "logo_url": "https://weather.com.cn/favicon.ico",
                },
                {
                    "type": "url_citation",
                    "url": "https://www.qweather.com/weather/wuhan-101200101.html",
                    "title": "Wuhan weather and air quality",
                    "summary": "Forecast, alerts and history.",
                    "site_name": "qweather.com",
                    "publish_time": "2026-09-15T00:00:00.0000000",
                },
            ],
            "tool_calls": None,
        },
    }],
    "created": 1790008349,
    "model": "mimo-v2.6-flash",
    "object": "chat.completion",
    "usage": {
        "completion_tokens": 60,
        "prompt_tokens": 1476,
        "total_tokens": 1536,
        "completion_tokens_details": {"reasoning_tokens": 0},
        "prompt_tokens_details": {"cached_tokens": 0},
        "web_search_usage": {"tool_usage": 3, "page_usage": 3},
    },
}


def observed(**overrides) -> dict:
    body = json.loads(json.dumps(OBSERVED_SEARCH_RESPONSE))
    body.update(overrides)
    return body


def no_usage(body: dict) -> dict:
    body["usage"].pop("web_search_usage", None)
    return body


def template(**overrides) -> dict:
    block = {"protocol": "chat-web-search", "model": "mimo-v2.6-flash",
             "max_keyword": 2, "results_per_keyword": 1, "force_search": True,
             "source": "https://example.test/search"}
    block.update(overrides)
    return {"search": block}
