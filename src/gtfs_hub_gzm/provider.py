"""Find GZM schedule files, whose names and IDs change with each publication."""

import json
import re
from collections.abc import Mapping
from typing import override

from aiohttp import ClientError, ClientSession, ClientTimeout
from gtfs_hub import (
    BaseProvider,
    Capabilities,
    GtfsConnectionError,
    GtfsFeedError,
    Livery,
    RealtimeEndpoints,
    StaticFeedRef,
    StopKeyField,
    TableReader,
    VehicleClass,
    raise_for_status,
)

_PORTAL = "https://otwartedane.metropoliagzm.pl"
# The temporary GTFS dataset is withdrawn, so only this one is read.
_DATASET = "rozklady-jazdy-i-lokalizacja-przystankow-gtfs-wersja-rozszerzona"
_REALTIME = "https://gtfsrt.transportgzm.pl:5443/gtfsrt/gzm"
_TIMEOUT = ClientTimeout(total=60)
_LENGTH = re.compile(r"ok\.\s*(\d+)\s*metr")
# The length clause, which length already states as a number.
_LENGTH_CLAUSE = re.compile(r"\s*o długości\b.*$")


class GzmProvider(BaseProvider):
    """Górnośląsko-Zagłębiowska Metropolia public transport."""

    key = "gzm"
    name = "GZM"
    attribution = "Data source: GZM ZTM, Creative Commons Attribution"
    stop_key: StopKeyField = "stop_code"
    # From the survey of 2026-10-31 to 2026-11-02, recorded in the README.
    capabilities = Capabilities(
        vehicle_positions=True, trip_delays=True, shapes=True, stable_vehicle_id=True
    )
    # GZM vehicles are yellow with black.
    livery = Livery(body="#FFD200", trim="#1A1A1A")

    async def async_list_static_feeds(self, session: ClientSession) -> list[StaticFeedRef]:
        """List the ZIP resources of the current dataset."""
        url = f"{_PORTAL}/api/3/action/package_show"
        try:
            async with session.get(url, params={"id": _DATASET}, timeout=_TIMEOUT) as response:
                raise_for_status(response, url)
                body = await response.text()
        except (ClientError, TimeoutError) as err:
            raise GtfsConnectionError(f"Cannot reach the data portal: {err}") from err
        except UnicodeDecodeError as err:
            raise GtfsFeedError(f"Malformed data portal response: {err}") from err
        return _parse_resources(body)

    @override
    def vehicle_key(self, vehicle_id: str, label: str, trip_id: str) -> str | None:
        """Return the ID without its trip, which changes it at every trip."""
        return vehicle_id.partition("_trip_")[0] or None

    @override
    def vehicle_label(self, vehicle_id: str, label: str) -> str | None:
        """Return the fleet number, which ends the key after the carrier prefix it repeats.

        The feed sends no label: `108_108001347` is vehicle 1347.
        """
        carrier, _, rest = vehicle_id.partition("_trip_")[0].partition("_")
        if not carrier or not rest.startswith(carrier):
            return None
        return rest.removeprefix(carrier).lstrip("0") or None

    @override
    def trip_vehicle_classes(self, read: TableReader) -> Mapping[str, VehicleClass]:
        """Read the planned vehicle, which only the extension files state."""
        classes = {
            row["vehicle_class_id"]: _parse_class(row)
            for row in read("vehicles_ext")
            if "vehicle_class_id" in row
        }
        return {
            row["trip_id"]: classes[row["vehicle_class_id"]]
            for row in read("trips_ext")
            if row.get("vehicle_class_id") in classes and "trip_id" in row
        }

    @override
    def realtime_endpoints(self) -> RealtimeEndpoints:
        """Return the published endpoints. No alert feed is published."""
        return RealtimeEndpoints(
            trip_updates=f"{_REALTIME}/tripUpdates",
            vehicle_positions=f"{_REALTIME}/vehiclePositions",
        )


def _parse_class(row: Mapping[str, str]) -> VehicleClass:
    """Read a class. Length is stated only in the Polish description."""
    name = row.get("vehicle_short_name", "").strip()
    long_name = row.get("vehicle_long_name", "").strip()
    length = _LENGTH.search(long_name)
    description = _LENGTH_CLAUSE.sub("", long_name)
    return VehicleClass(
        name=name,
        length=int(length[1]) if length else None,
        units=2 if name.startswith("2x") else 1,
        low_floor=row.get("low_floor", "").strip() == "1",
        description=description[:1].upper() + description[1:] if description else None,
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
    # Without a date there is no version, so core downloads the file and compares its hash.
    version = f"{resource_id}:{modified}" if isinstance(modified, str) else None
    return StaticFeedRef(url=url, version=version)
