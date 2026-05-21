"""Twitter ingestion via X's filtered stream (xdk SDK).

`stream_tweets(settings)` yields the body of each new tweet from the
tracked X account as a `str`. Thin wrapper around `client.stream.posts()`;
the SDK manages reconnection internally.
"""

import logging
from collections.abc import Iterator

from xdk import Client
from xdk.stream.models import UpdateRulesRequest

from serenity.config import Settings

log = logging.getLogger(__name__)


def extract_handle(profile_url: str) -> str:
    return profile_url.rstrip("/").rsplit("/", 1)[-1]


def stream_tweets(settings: Settings) -> Iterator[str]:
    client = Client(bearer_token=settings.x_bearer_token.get_secret_value())
    handle = extract_handle(str(settings.tracked_x_account))

    log.info("Twitter ingestion starting: @%s via X filtered stream", handle)
    client.stream.update_rules(body=UpdateRulesRequest(), delete_all=True)
    client.stream.update_rules(
        body=UpdateRulesRequest(add=[{"value": f"from:{handle}"}])
    )

    for post_response in client.stream.posts():
        data = post_response.model_dump()
        if data.get("data"):
            tweet = data["data"]
            text = tweet.get("text", "") if isinstance(tweet, dict) else getattr(tweet, "text", "")
            if text:
                yield text
