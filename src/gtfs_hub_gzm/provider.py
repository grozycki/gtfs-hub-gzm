"""Find GZM schedule files, whose names and IDs change with each publication."""

import json
from typing import override

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

    @override
    def realtime_endpoints(self) -> RealtimeEndpoints:
        """Return the published endpoints. No alert feed is published."""
        return RealtimeEndpoints(
            trip_updates=f"{_REALTIME}/tripUpdates",
            vehicle_positions=f"{_REALTIME}/vehiclePositions",
        )


def _parse_resources(body: str) -> list[StaticFeedRef]:
    """Validate a portal response, whose shape is outside any type."""
    try:
        data: object = json.loads(body)
    except ValueError as err:
        raise GtfsFeedError(f"Malformed data portal response: {err}") from err
    if not isinstance(data, dict) or not data.get("success"):
        raise GtfsFeedError("The data portal reported a failure")
    result: object = data.get("result")
    resources: object = result.get("resources") if isinstance(result, dict) else None
    if not isinstance(resources, list):
        raise GtfsFeedError("The data portal response lists no resources")
    refs = [ref for resource in resources if (ref := _parse_resource(resource)) is not None]
    if not refs:
        raise GtfsFeedError("The data portal listed no ZIP resources")
    return refs


def _parse_resource(resource: object) -> StaticFeedRef | None:
    """Return a ZIP resource, or None for any other format."""
    if not isinstance(resource, dict):
        raise GtfsFeedError("Malformed data portal resource")
    kind, url, resource_id, modified = (
        resource.get(name) for name in ("format", "url", "id", "last_modified")
    )
    if not isinstance(kind, str):
        raise GtfsFeedError("Data portal resource has no format")
    if kind.upper() != "ZIP":
        return None
    if not isinstance(url, str) or not isinstance(resource_id, str):
        raise GtfsFeedError("Data portal resource has no URL or ID")
    # The portal leaves `hash` empty, so the version comes from these two fields.
    return StaticFeedRef(url=url, version=f"{resource_id}:{modified}")
