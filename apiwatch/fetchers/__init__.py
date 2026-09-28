from .base import Fetcher, Http, SkipPlatform
from .google_discovery import GoogleDiscoveryFetcher
from .meta_sdk import MetaSDKFetcher
from .sample import TTDSampleFetcher

FETCHERS: dict[str, type[Fetcher]] = {
    "google_discovery": GoogleDiscoveryFetcher,
    "meta_sdk": MetaSDKFetcher,
    "ttd_sample": TTDSampleFetcher,
}


def make_fetcher(platform: str, cfg: dict, http: Http | None = None) -> Fetcher:
    kind = cfg.get("type")
    if kind not in FETCHERS:
        raise ValueError(f"{platform}: unknown fetcher type {kind!r} (choose from {sorted(FETCHERS)})")
    return FETCHERS[kind](platform, cfg, http or Http())


__all__ = ["FETCHERS", "Fetcher", "Http", "SkipPlatform", "make_fetcher"]
