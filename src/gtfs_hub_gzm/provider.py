"""Find GZM schedule files, whose names and IDs change with each publication."""

import json
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from gtfs_hub import (
    BaseProvider,
    Capabilities,
    GtfsConnectionError,
    GtfsFeedError,
    RealtimeEndpoints,
    StaticFeedRef,
    StopKeyField,
    raise_for_status,
)

_PORTAL = "https://otwartedane.metropoliagzm.pl"
# The temporary GTFS dataset is withdrawn, so only this one is read.
_DATASET = "rozklady-jazdy-i-lokalizacja-przystankow-gtfs-wersja-rozszerzona"
_REALTIME = "https://gtfsrt.transportgzm.pl:5443/gtfsrt/gzm"
_TIMEOUT = ClientTimeout(total=60)


class GzmProvider(BaseProvider):
    """Górnośląsko-Zagłębiowska Metropolia public transport."""

    key = "gzm"
    name = "GZM"
    attribution = "Data source: GZM ZTM, Creative Commons Attribution"
    stop_key: StopKeyField = "stop_code"
    # From the survey of 2026-10-31. Stable vehicle identity is not proven yet.
    capabilities = Capabilities(vehicle_positions=True, trip_delays=True, shapes=True)

    async def async_list_static_feeds(self, session: ClientSession) -> list[StaticFeedRef]:
        """List the ZIP resources of the current dataset."""
        url = f"{_PORTAL}/api/3/action/package_show"
        try:
            async with session.get(url, params={"id": _DATASET}, timeout=_TIMEOUT) as response:
                raise_for_status(response, url)
                body = await response.text()
        except (ClientError, TimeoutError) as err:
            raise GtfsConnectionError(f"Cannot reach the data portal: {err}") from err
        return _parse_resources(body)

    def realtime_endpoints(self) -> RealtimeEndpoints:
        """Return the published endpoints. No alert feed is published."""
        return RealtimeEndpoints(
            trip_updates=f"{_REALTIME}/tripUpdates",
            vehicle_positions=f"{_REALTIME}/vehiclePositions",
        )


def _parse_resources(body: str) -> list[StaticFeedRef]:
    try:
        data: Any = json.loads(body)
        if not data["success"]:
            raise GtfsFeedError("The data portal reported a failure")
        refs = [
            # The portal leaves `hash` empty, so the version comes from these two fields.
            StaticFeedRef(
                url=resource["url"],
                version=f"{resource['id']}:{resource['last_modified']}",
            )
            for resource in data["result"]["resources"]
            if str(resource["format"]).upper() == "ZIP"
        ]
    except (ValueError, KeyError, TypeError) as err:
        raise GtfsFeedError(f"Malformed data portal response: {err!r}") from err
    if not refs:
        raise GtfsFeedError("The data portal listed no ZIP resources")
    return refs
