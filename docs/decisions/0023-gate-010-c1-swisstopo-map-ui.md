# ADR 0023 — GATE-010-C1 dashboard scale and free Swiss map

## Status

Accepted for implementation after GATE-012 merge.

## Context

The production dashboard used an oversized editorial hero and displayed mojibake in pending
metrics. Its vendored MapLibre module was imported correctly but the runtime checked a nonexistent
`window.maplibregl`, causing the map to report that the library was unavailable.

The product owner requested visible job markers and convenient access to Google Maps without
accepting an open-ended billing dependency. The frozen geospatial contract already selects
MapLibre, explicitly licensed tiles and geo.admin.ch SearchServer for the production MVP. The
frozen prototype used official swisstopo WMTS tiles.

## Decision

- Reduce the hero, pending-metric and detail-title scale without changing dashboard evidence.
- Correct visible UTF-8 mojibake.
- Preserve MapLibre as the default and fix its module-runtime check.
- Use the official `ch.swisstopo.pixelkarte-farbe` WMTS layer when no custom style is configured.
- Display the mandatory `© swisstopo` attribution.
- Add an `Open in Google Maps` action to each mappable popup using the free Maps URLs interface,
  which requires no API key or billing account.
- Preserve the already implemented Google JavaScript provider only as an explicit optional path;
  it is not required for normal operation.
- Feed every map/action exclusively from the existing filtered public GeoJSON endpoint.
- Keep the complete table available whenever the basemap is unavailable.

## Privacy and scientific integrity

Only `public_display_latitude` and `public_display_longitude` already accepted by the geospatial
pipeline can reach a map provider or outbound map URL. Private exact coordinates, raw addresses,
unresolved locations, geocoding review items and hidden evidence remain absent from the page and
GeoJSON. An outbound Google Maps link is never built from raw location text.

This correction changes presentation only. It does not geocode records, alter snapshots, change
geography precision, modify Day-0 counts or edit frozen research.

## Operational consequence

The Swiss basemap renders without a project API key. The current production snapshot still has
zero safely mappable records; a separate governed integration must execute the existing
`resolve_locations` pipeline before later PIT snapshots can expose markers.