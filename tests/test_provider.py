"""Tests read a recorded portal sample and never the live service."""

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer
from gtfs_hub import (
    Capabilities,
    GtfsConnectionError,
    GtfsFeedError,
    Provider,
    TableReader,
    VehicleClass,
    create_provider,
    list_provider_keys,
)

from gtfs_hub_gzm import GzmProvider
from gtfs_hub_gzm import provider as module

SAMPLE = (Path(__file__).parent / "samples" / "package_show.json").read_text(encoding="utf-8")

Portal = Callable[[web.Response], None]


@pytest.fixture
async def session() -> AsyncIterator[ClientSession]:
    async with ClientSession() as client:
        yield client


@pytest.fixture
async def portal(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Portal]:
    """Point the provider at a local server and let tests choose its response."""
    answer = [web.json_response(text=SAMPLE)]

    async def handle(request: web.Request) -> web.Response:
        assert request.query["id"] == module._DATASET
        response = answer[0]
        return web.Response(body=response.body, status=response.status)

    app = web.Application()
    app.router.add_get("/api/3/action/package_show", handle)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(module, "_PORTAL", str(server.make_url("")).rstrip("/"))
    yield lambda response: answer.__setitem__(0, response)
    await server.close()


def test_created_from_its_key_through_core() -> None:
    assert "gzm" in list_provider_keys()
    provider = create_provider("gzm")
    assert isinstance(provider, GzmProvider)


def test_declarations() -> None:
    provider: Provider = GzmProvider()
    assert provider.key == "gzm"
    assert provider.stop_key == "stop_code"
    assert provider.attribution is not None
    assert "GZM ZTM" in provider.attribution


def test_capabilities_match_the_survey() -> None:
    capabilities = GzmProvider().capabilities
    assert capabilities == Capabilities(
        vehicle_positions=True, trip_delays=True, shapes=True, stable_vehicle_id=True
    )
    assert not capabilities.bearing
    assert not capabilities.speed
    assert not capabilities.occupancy
    assert not capabilities.alerts


def test_vehicle_key_drops_the_trip() -> None:
    key = GzmProvider().vehicle_key("116_116005627_trip_11_7204619", "", "11_7204619")
    assert key == "116_116005627"


def test_vehicle_key_survives_a_new_trip() -> None:
    provider = GzmProvider()
    first = provider.vehicle_key("116_116005627_trip_11_7204619", "", "11_7204619")
    later = provider.vehicle_key("116_116005627_trip_11_7204700", "", "11_7204700")
    assert first == later


def test_empty_vehicle_id_has_no_key() -> None:
    assert GzmProvider().vehicle_key("", "", "t") is None


def test_realtime_endpoints() -> None:
    endpoints = GzmProvider().realtime_endpoints()
    assert endpoints.trip_updates and endpoints.trip_updates.endswith("/tripUpdates")
    assert endpoints.vehicle_positions and endpoints.vehicle_positions.endswith("/vehiclePositions")
    assert endpoints.alerts is None


async def test_lists_zip_resources_only(portal: Portal, session: ClientSession) -> None:
    refs = await GzmProvider().async_list_static_feeds(session)
    resources = json.loads(SAMPLE)["result"]["resources"]
    zips = [resource for resource in resources if resource["format"] == "ZIP"]
    assert len(zips) < len(resources)
    assert [ref.url for ref in refs] == [resource["url"] for resource in zips]
    assert all(ref.url.endswith(".zip") for ref in refs)


async def test_new_names_need_no_code_change(portal: Portal, session: ClientSession) -> None:
    body = {
        "success": True,
        "result": {
            "resources": [
                {
                    "id": "new-id",
                    "format": "zip",
                    "last_modified": "2027-01-01T00:00:00",
                    "url": "https://example.test/anything-at-all.zip",
                }
            ]
        },
    }
    portal(web.json_response(body))
    [ref] = await GzmProvider().async_list_static_feeds(session)
    assert ref.url == "https://example.test/anything-at-all.zip"
    assert ref.version == "new-id:2027-01-01T00:00:00"


async def test_version_is_stable_and_changes_with_the_resource(
    portal: Portal, session: ClientSession
) -> None:
    provider = GzmProvider()
    first = await provider.async_list_static_feeds(session)
    assert await provider.async_list_static_feeds(session) == first
    changed = json.loads(SAMPLE)
    for resource in changed["result"]["resources"]:
        resource["last_modified"] = "2030-01-01T00:00:00"
    portal(web.json_response(changed))
    second = await provider.async_list_static_feeds(session)
    assert {ref.version for ref in first}.isdisjoint(ref.version for ref in second)


async def test_server_failure_is_a_connection_error(portal: Portal, session: ClientSession) -> None:
    portal(web.Response(status=503))
    with pytest.raises(GtfsConnectionError):
        await GzmProvider().async_list_static_feeds(session)


async def test_unreachable_portal_is_a_connection_error(
    monkeypatch: pytest.MonkeyPatch, session: ClientSession
) -> None:
    monkeypatch.setattr(module, "_PORTAL", "http://127.0.0.1:9")
    with pytest.raises(GtfsConnectionError):
        await GzmProvider().async_list_static_feeds(session)


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "{}",
        '{"success": false}',
        '{"success": true, "result": {"resources": [{"format": "ZIP"}]}}',
        '{"success": true, "result": {"resources": []}}',
        '{"success": true, "result": {"resources": [{"format": "PDF"}]}}',
    ],
)
async def test_malformed_response_is_a_feed_error(
    portal: Portal, session: ClientSession, body: str
) -> None:
    portal(web.Response(text=body))
    with pytest.raises(GtfsFeedError):
        await GzmProvider().async_list_static_feeds(session)


async def test_resource_without_a_date_has_no_version(
    portal: Portal, session: ClientSession
) -> None:
    resource = {"id": "x", "format": "ZIP", "url": "https://example.test/a.zip"}
    portal(web.json_response({"success": True, "result": {"resources": [resource]}}))
    [ref] = await GzmProvider().async_list_static_feeds(session)
    assert ref.version is None


async def test_undecodable_response_is_a_feed_error(portal: Portal, session: ClientSession) -> None:
    portal(web.Response(body=b"\xff\xfe", content_type="application/json", charset="utf-8"))
    with pytest.raises(GtfsFeedError):
        await GzmProvider().async_list_static_feeds(session)


def _reader(tables: dict[str, list[dict[str, str]]]) -> TableReader:
    return lambda name: tables.get(name, [])


def test_vehicle_classes_of_trips() -> None:
    long_name = "autobus niskopodłogowy o długości ok.18 metrów"
    tables = {
        "vehicles_ext": [
            {
                "vehicle_class_id": "14",
                "vehicle_short_name": "C N",
                "vehicle_long_name": long_name,
                "low_floor": "1",
            },
            {
                "vehicle_class_id": "20",
                "vehicle_short_name": "2x105HF",
                "vehicle_long_name": "",
                "low_floor": "0",
            },
        ],
        "trips_ext": [
            {"trip_id": "a", "vehicle_class_id": "14"},
            {"trip_id": "b", "vehicle_class_id": "20"},
            {"trip_id": "c", "vehicle_class_id": "99"},
        ],
    }
    classes = GzmProvider().trip_vehicle_classes(_reader(tables))
    assert classes == {
        "a": VehicleClass("C N", 18, 1, True),
        "b": VehicleClass("2x105HF", None, 2, False),
    }


def test_no_extension_tables() -> None:
    assert GzmProvider().trip_vehicle_classes(_reader({})) == {}


def test_changed_extension_columns_do_not_stop_an_import() -> None:
    tables = {"vehicles_ext": [{"other": "x"}], "trips_ext": [{"other": "y"}]}
    assert GzmProvider().trip_vehicle_classes(_reader(tables)) == {}
