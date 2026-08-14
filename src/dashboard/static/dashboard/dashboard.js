import * as maplibregl from "./vendor/maplibre-gl.mjs";

(function () {
  "use strict";

  const app = document.getElementById("dashboard-app");
  if (!app) return;

  const form = document.getElementById("filters");
  const body = document.getElementById("results-body");
  const resultCount = document.getElementById("result-count");
  const mapCount = document.getElementById("map-count");
  const resultEmpty = document.getElementById("results-empty");
  const mapEmpty = document.getElementById("map-empty");
  const quality = document.getElementById("quality-note");
  const drawer = document.getElementById("job-drawer");
  const backdrop = document.getElementById("drawer-backdrop");
  const drawerContent = document.getElementById("drawer-content");
  const closeButton = document.getElementById("drawer-close");
  let snapshotId = app.dataset.snapshotId || "";
  let activeTrigger = null;
  let map = null;
  let mapReady = false;
  const mapProvider = app.dataset.mapProvider || "maplibre";
  const googleMapsApiKey = app.dataset.googleMapsApiKey || "";
  const defaultMapEmptyMessage = mapEmpty.textContent;
  let mapUnavailableMessage = "";
  let googleMarkers = [];
  let googleInfoWindow = null;
  let latestGeoJSON = { type: "FeatureCollection", features: [] };
  let dataController = null;
  let requestSequence = 0;

  function swisstopoStyle() {
    return {
      version: 8,
      sources: {
        swisstopo: {
          type: "raster",
          tiles: [
            "https://wmts.geo.admin.ch/1.0.0/" +
            "ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg"
          ],
          tileSize: 256,
          maxzoom: 18,
          attribution: "© swisstopo"
        }
      },
      layers: [
        {
          id: "background",
          type: "background",
          paint: { "background-color": "#dfe5d6" }
        },
        {
          id: "swisstopo-basemap",
          type: "raster",
          source: "swisstopo"
        }
      ]
    };
  }

  function activeParams() {
    const params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      const clean = String(value).trim();
      if (clean) params.set(key, clean);
    });
    return params;
  }

  function restoreParams() {
    const params = new URLSearchParams(window.location.search);
    params.forEach(function (value, key) {
      const control = form.elements.namedItem(key);
      if (control) control.value = value;
    });
  }

  function endpoint(kind, params) {
    const base = "/api/v1/dashboard/snapshots/" + snapshotId + "/";
    const path = kind === "geojson" ? "vacancies.geojson" : "vacancies/";
    const query = params.toString();
    return base + path + (query ? "?" + query : "");
  }

  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value == null || value === "" ? "Not reported" : String(value);
    if (className) node.className = className;
    return node;
  }

  function safeExternalLink(url, label) {
    if (!url || !label) return null;
    let parsed;
    try { parsed = new URL(url); } catch (_) { return null; }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
    const link = document.createElement("a");
    link.href = parsed.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label;
    return link;
  }

  async function openDetail(url, trigger) {
    activeTrigger = trigger || document.activeElement;
    const response = await fetch(url, { headers: { "X-Requested-With": "dashboard-v0.1" } });
    if (!response.ok) throw new Error("Detail unavailable");
    const parsed = new DOMParser().parseFromString(await response.text(), "text/html");
    parsed.querySelectorAll(
      "script,style,svg,math,iframe,object,embed,template,noscript,foreignObject"
    ).forEach(function (node) { node.remove(); });
    parsed.querySelectorAll("*").forEach(function (node) {
      Array.from(node.attributes).forEach(function (attribute) {
        if (!["class", "href", "target", "rel"].includes(attribute.name)) {
          node.removeAttribute(attribute.name);
        }
      });
      if (node.hasAttribute("href")) {
        const safe = safeExternalLink(node.getAttribute("href"), node.textContent);
        if (!safe) node.removeAttribute("href");
        else {
          node.setAttribute("href", safe.href);
          node.setAttribute("target", "_blank");
          node.setAttribute("rel", "noopener noreferrer");
        }
      }
    });
    drawerContent.replaceChildren(...parsed.body.childNodes);
    drawer.hidden = false;
    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    closeButton.focus();
  }

  function closeDetail() {
    drawer.hidden = true;
    backdrop.hidden = true;
    drawerContent.textContent = "";
    document.body.style.overflow = "";
    if (activeTrigger && typeof activeTrigger.focus === "function") activeTrigger.focus();
  }

  function renderRows(records) {
    body.textContent = "";
    records.forEach(function (record) {
      const row = document.createElement("tr");
      row.tabIndex = 0;
      row.dataset.detailUrl = record.detail_url;
      row.dataset.vacancyKey = record.run_vacancy_key;
      row.dataset.mappingStatus = record.mapping_status;

      const role = document.createElement("td");
      role.append(text("span", record.title, "role-title"));
      role.append(text("span", record.employer, "role-employer"));
      const place = document.createElement("td");
      place.append(text("span", record.municipality || record.canton || "Unresolved", "place-name"));
      if (record.mapping_status !== "MAPPABLE") {
        const labels = {
          LOCATION_UNRESOLVED: "Location unresolved",
          LOCATION_REVIEW: "Location requires review",
          PUBLIC_COORDINATES_MISSING: "Public coordinates missing",
          PRIVACY_RESOLUTION_MISSING: "Privacy resolution pending",
          LOCATION_HIDDEN: "Private location hidden"
        };
        const label = labels[record.mapping_status] || "Not safely mappable";
        const badge = text("span", "Not shown on map · " + label, "location-map-status");
        badge.setAttribute("aria-label", "Map status: " + label);
        place.append(badge);
      }
      const observed = text("td", record.first_observed.slice(0, 10));
      const source = text("td", record.source_name);
      row.append(role, place, observed, source);

      const activate = function () {
        if (record.mapping_status === "MAPPABLE") {
          const feature = latestGeoJSON.features.find(function (item) {
            return item.properties.run_vacancy_key === record.run_vacancy_key;
          });
          if (feature) focusMapFeature(feature);
        }
        openDetail(record.detail_url, row).catch(showError);
      };
      row.addEventListener("click", activate);
      row.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
      body.append(row);
    });
    resultCount.textContent = records.length + (records.length === 1 ? " record" : " records");
    resultEmpty.hidden = records.length !== 0;
  }

  function googleMapsUrl(coordinates) {
    if (!Array.isArray(coordinates) || coordinates.length !== 2) return "";
    const longitude = Number(coordinates[0]);
    const latitude = Number(coordinates[1]);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return "";
    const url = new URL("https://www.google.com/maps/search/");
    url.searchParams.set("api", "1");
    url.searchParams.set("query", latitude + "," + longitude);
    return url.href;
  }

  function popupNode(properties, coordinates) {
    const root = document.createElement("div");
    root.append(text("strong", properties.title));
    root.append(text("div", properties.employer));
    root.append(text("div", properties.municipality || properties.canton || "Region unresolved"));
    root.append(text("div", "Published: " + (properties.source_publication_date || "Not reported by source")));
    root.append(text("div", "First observed: " + properties.first_observed.slice(0, 10)));
    root.append(text("div", "Segment: " + properties.segment));
    root.append(text("div", "Precision: " + properties.location_precision));
    if (properties.approximate_location) {
      root.append(text("div", "Approximate location for privacy", "privacy-warning"));
    }
    const actions = document.createElement("div");
    actions.className = "popup-actions";
    const detail = document.createElement("button");
    detail.type = "button";
    detail.textContent = "View full job details";
    detail.addEventListener("click", function () {
      openDetail(properties.detail_url, detail).catch(showError);
    });
    actions.append(detail);
    const external = safeExternalLink(properties.external_url, properties.source_link_label);
    if (external) actions.append(external);
    const googleMaps = safeExternalLink(googleMapsUrl(coordinates), "Open in Google Maps");
    if (googleMaps) actions.append(googleMaps);
    root.append(actions);
    return root;
  }

  function showMapMessage(message) {
    mapUnavailableMessage = message;
    mapEmpty.hidden = false;
    mapEmpty.textContent = message;
  }

  function loadGoogleMaps(apiKey) {
    if (window.google && window.google.maps) return Promise.resolve(window.google.maps);
    return new Promise(function (resolve, reject) {
      const callbackName = "__swissGardenGoogleMapsReady";
      const existing = document.querySelector('script[data-google-maps-loader="true"]');
      if (existing) {
        existing.addEventListener("error", function () {
          reject(new Error("Google Maps failed to load"));
        }, { once: true });
        return;
      }
      window[callbackName] = function () {
        delete window[callbackName];
        resolve(window.google.maps);
      };
      const script = document.createElement("script");
      script.dataset.googleMapsLoader = "true";
      script.async = true;
      script.defer = true;
      script.src = "https://maps.googleapis.com/maps/api/js?key=" +
        encodeURIComponent(apiKey) + "&callback=" + callbackName + "&v=weekly";
      script.addEventListener("error", function () {
        delete window[callbackName];
        reject(new Error("Google Maps failed to load"));
      }, { once: true });
      document.head.append(script);
    });
  }

  function googleClusterCell(zoom) {
    if (zoom <= 7) return 0.6;
    if (zoom <= 9) return 0.18;
    if (zoom <= 11) return 0.05;
    return 0;
  }

  function googleFeaturePosition(feature) {
    return {
      lat: Number(feature.geometry.coordinates[1]),
      lng: Number(feature.geometry.coordinates[0])
    };
  }

  function groupedGoogleFeatures() {
    const cell = googleClusterCell(map.getZoom() || 7);
    const groups = new Map();
    latestGeoJSON.features.forEach(function (feature) {
      const position = googleFeaturePosition(feature);
      const key = cell === 0
        ? feature.properties.run_vacancy_key
        : Math.round(position.lat / cell) + ":" + Math.round(position.lng / cell);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(feature);
    });
    return Array.from(groups.values());
  }

  function clearGoogleMarkers() {
    googleMarkers.forEach(function (marker) { marker.setMap(null); });
    googleMarkers = [];
  }

  function renderGoogleMarkers(fitToData) {
    if (mapProvider !== "google" || !mapReady || !window.google || !window.google.maps) return;
    clearGoogleMarkers();
    if (!latestGeoJSON.features.length) return;

    const bounds = new window.google.maps.LatLngBounds();
    groupedGoogleFeatures().forEach(function (features) {
      const positions = features.map(googleFeaturePosition);
      const position = {
        lat: positions.reduce(function (sum, item) { return sum + item.lat; }, 0) / positions.length,
        lng: positions.reduce(function (sum, item) { return sum + item.lng; }, 0) / positions.length
      };
      const isCluster = features.length > 1;
      const approximate = !isCluster && Boolean(features[0].properties.approximate_location);
      const marker = new window.google.maps.Marker({
        map: map,
        position: position,
        title: isCluster
          ? features.length + " safely mappable vacancies"
          : features[0].properties.title,
        label: isCluster ? { text: String(features.length), color: "#fffef8" } : undefined,
        icon: {
          path: window.google.maps.SymbolPath.CIRCLE,
          scale: isCluster ? 18 : 9,
          fillColor: approximate ? "#dce966" : "#164d38",
          fillOpacity: 1,
          strokeColor: "#fffef8",
          strokeWeight: 2
        }
      });
      marker.addListener("click", function () {
        if (isCluster) {
          map.panTo(position);
          map.setZoom(Math.min((map.getZoom() || 7) + 2, 14));
          return;
        }
        googleInfoWindow.setContent(
          popupNode(features[0].properties, features[0].geometry.coordinates)
        );
        googleInfoWindow.open(map, marker);
      });
      googleMarkers.push(marker);
      bounds.extend(position);
    });

    if (fitToData) {
      if (latestGeoJSON.features.length === 1) {
        map.setCenter(googleFeaturePosition(latestGeoJSON.features[0]));
        map.setZoom(11);
      } else {
        map.fitBounds(bounds, 40);
      }
    }
  }

  function initGoogleMap() {
    if (!googleMapsApiKey) {
      showMapMessage(
        "Google Maps is selected but GOOGLE_MAPS_API_KEY is not configured. " +
        "The complete public table remains available."
      );
      return;
    }
    loadGoogleMaps(googleMapsApiKey).then(function (maps) {
      map = new maps.Map(document.getElementById("map"), {
        center: { lat: 46.82, lng: 8.23 },
        zoom: 7,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: true
      });
      googleInfoWindow = new maps.InfoWindow();
      mapReady = true;
      mapUnavailableMessage = "";
      map.addListener("idle", function () { renderGoogleMarkers(false); });
      updateMap();
    }).catch(function () {
      showMapMessage(
        "Google Maps could not be loaded. The complete public table remains available."
      );
    });
  }

  function focusMapFeature(feature) {
    if (!mapReady || !map) return;
    if (mapProvider === "google") {
      map.panTo(googleFeaturePosition(feature));
      map.setZoom(11);
      return;
    }
    map.easeTo({ center: feature.geometry.coordinates, zoom: 11 });
  }

  function initMap() {
    if (mapProvider === "google") initGoogleMap();
    else initMapLibre();
  }

  function initMapLibre() {
    if (!maplibregl || typeof maplibregl.Map !== "function") {
      mapEmpty.hidden = false;
      mapEmpty.textContent = "Map library unavailable. The complete table remains available.";
      return;
    }
    const configured = app.dataset.mapStyle;
    map = new maplibregl.Map({
      container: "map",
      style: configured || swisstopoStyle(),
      center: [8.23, 46.82],
      zoom: 6.4,
      attributionControl: false
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution: app.dataset.mapAttribution || "MapLibre"
    }));
    map.on("load", function () {
      mapReady = true;
      map.addSource("vacancies", {
        type: "geojson",
        data: latestGeoJSON,
        cluster: true,
        clusterMaxZoom: 12,
        clusterRadius: 48
      });
      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "vacancies",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#164d38",
          "circle-radius": ["step", ["get", "point_count"], 18, 10, 24, 30, 32],
          "circle-stroke-color": "#dce966",
          "circle-stroke-width": 3
        }
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "vacancies",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
        paint: { "text-color": "#fffef8" }
      });
      map.addLayer({
        id: "vacancy-points",
        type: "circle",
        source: "vacancies",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": ["case", ["get", "approximate_location"], "#dce966", "#164d38"],
          "circle-radius": 8,
          "circle-stroke-color": "#fffef8",
          "circle-stroke-width": 2
        }
      });
      map.on("click", "clusters", function (event) {
        const features = map.queryRenderedFeatures(event.point, { layers: ["clusters"] });
        if (!features.length) return;
        const clusterId = features[0].properties.cluster_id;
        map.getSource("vacancies").getClusterExpansionZoom(clusterId).then(function (zoom) {
          map.easeTo({ center: features[0].geometry.coordinates, zoom: zoom });
        });
      });
      map.on("click", "vacancy-points", function (event) {
        if (!event.features || !event.features.length) return;
        new maplibregl.Popup()
          .setLngLat(event.features[0].geometry.coordinates)
          .setDOMContent(
            popupNode(event.features[0].properties, event.features[0].geometry.coordinates)
          )
          .addTo(map);
      });
      updateMap();
    });
    map.on("error", function () {
      if (!configured) return;
      mapEmpty.hidden = false;
      mapEmpty.textContent = "The configured basemap is unavailable. Job records remain in the table.";
    });
  }

  function updateMap() {
    mapCount.textContent = latestGeoJSON.features.length + " markers";
    if (mapUnavailableMessage) {
      mapEmpty.hidden = false;
      mapEmpty.textContent = mapUnavailableMessage;
    } else {
      mapEmpty.textContent = defaultMapEmptyMessage;
      mapEmpty.hidden = latestGeoJSON.features.length !== 0;
    }
    if (mapProvider === "google") {
      renderGoogleMarkers(true);
      return;
    }
    if (mapReady && map && map.getSource("vacancies")) {
      map.getSource("vacancies").setData(latestGeoJSON);
    }
  }

  async function loadData(pushState) {
    if (dataController) dataController.abort();
    dataController = new AbortController();
    const signal = dataController.signal;
    const sequence = ++requestSequence;
    quality.setAttribute("aria-busy", "true");
    if (!snapshotId) {
      const current = await fetch(app.dataset.currentUrl, { signal: signal }).then(function (response) {
        if (!response.ok) throw new Error("No dashboard snapshot available");
        return response.json();
      });
      snapshotId = current.snapshot_id;
      app.dataset.snapshotId = snapshotId;
    }
    const params = activeParams();
    if (pushState) {
      const query = params.toString();
      window.history.replaceState({}, "", window.location.pathname + (query ? "?" + query : ""));
    }
    const responses = await Promise.all([
      fetch(endpoint("table", params), { signal: signal }),
      fetch(endpoint("geojson", params), { signal: signal })
    ]);
    if (!responses[0].ok || !responses[1].ok) throw new Error("Invalid or unavailable filter state");
    if (sequence !== requestSequence) return;
    const table = await responses[0].json();
    latestGeoJSON = await responses[1].json();
    renderRows(table.results);
    updateMap();
    quality.setAttribute("aria-busy", "false");
    quality.textContent =
      table.counts.mappable + " safely mappable · " +
      table.counts.unmappable + " public but unmapped · snapshot " +
      table.as_of + ". Headline market counters remain pending Day-0.";
  }

  function showError(error) {
    quality.setAttribute("aria-busy", "false");
    quality.textContent = "Dashboard request failed safely. " + error.message;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    loadData(true).catch(showError);
  });
  form.addEventListener("reset", function () {
    window.setTimeout(function () { loadData(true).catch(showError); }, 0);
  });
  closeButton.addEventListener("click", closeDetail);
  backdrop.addEventListener("click", closeDetail);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !drawer.hidden) closeDetail();
    if (event.key === "Tab" && !drawer.hidden) {
      const focusable = Array.from(
        drawer.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')
      ).filter(function (node) { return !node.hasAttribute("disabled"); });
      if (!focusable.length) {
        event.preventDefault();
        closeButton.focus();
      } else if (event.shiftKey && document.activeElement === focusable[0]) {
        event.preventDefault();
        focusable[focusable.length - 1].focus();
      } else if (!event.shiftKey && document.activeElement === focusable[focusable.length - 1]) {
        event.preventDefault();
        focusable[0].focus();
      }
    }
  });

  window.dashboardApp = {
    openDetail: openDetail,
    openMapFixture: function (feature) {
      const node = popupNode(feature.properties, feature.geometry.coordinates);
      const button = node.querySelector("button");
      button.click();
    },
    googleMapsUrl: googleMapsUrl,
    renderRowsFixture: renderRows
  };

  restoreParams();
  initMap();
  loadData(false).catch(showError);
}());
