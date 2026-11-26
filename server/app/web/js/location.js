import { getJSON } from "./api.js";
import { el, skeleton, emptyState, errorCard } from "./ui.js";
import { onThemeChange } from "./theme.js";
import { addBasemap } from "./basemap.js";
import { n0 } from "./fmt.js";
import { isLive, stateLabel, directionsUrl, subtitle } from "./locationlogic.js";

const POLL_MS = 10000;
const PARKED_GROUP = new Set(["parked", "no_signal"]);
const NS = "http://www.w3.org/2000/svg";
const nil = (x) => x === null || x === undefined;

const PIN_SVG = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z" class="loc-pin-body"/><text x="12" y="13.2" text-anchor="middle" font-size="8" font-weight="700" class="loc-pin-text">P</text></svg>`;

const parkedIcon = () => L.divIcon({
  className: "loc-icon", iconSize: [34, 34], iconAnchor: [17, 32],
  html: `<div class="loc-pin">${PIN_SVG}</div>`,
});
const liveIcon = () => L.divIcon({
  className: "loc-icon", iconSize: [22, 22], iconAnchor: [11, 11],
  html: `<div class="loc-live"><span class="loc-halo"></span><span class="loc-core"></span></div>`,
});

function infoCard(data) {
  const live = isLive(data.state);
  const head = el("div", { class: "loc-state" },
    el("span", { class: `dot${live ? " ok" : ""}`, "aria-hidden": "true" }),
    el("span", {}, stateLabel(data.state)),
    live ? el("span", { class: "tag live-tag" }, "● En vivo") : null);
  const sub = subtitle(data, data.now ?? Date.now()); // reloj del servidor: inmune al desfase del móvil
  const card = el("section", { class: "card loc-card" }, head, sub ? el("p", { class: "loc-sub" }, sub) : null);

  if (live) {
    const meta = el("div", { class: "loc-meta" });
    if (!nil(data.speed_kmh)) meta.append(el("div", {}, "Velocidad", el("b", { class: "num" }, `${n0(data.speed_kmh)} km/h`)));
    if (!nil(data.rpm)) meta.append(el("div", {}, "Motor", el("b", { class: "num" }, `${n0(data.rpm)} rpm`)));
    if (meta.children.length) card.append(meta);
  }
  if (!nil(data.point) && PARKED_GROUP.has(data.state)) {
    const { lat, lon } = data.point;
    const url = directionsUrl(lat, lon, navigator.userAgent);
    const web = url.startsWith("http");
    card.append(el("a", { class: "loc-go", href: url, target: web ? "_blank" : null, rel: web ? "noopener" : null },
      (() => {
        const s = document.createElementNS(NS, "svg");
        s.setAttribute("viewBox", "0 0 24 24");
        s.setAttribute("aria-hidden", "true");
        const p = document.createElementNS(NS, "path");
        p.setAttribute("d", "M3 11 21 3l-8 18-2-8z");
        s.append(p);
        return s;
      })(), "Cómo llegar"));
  }
  if (nil(data.point)) card.append(el("p", { class: "loc-nogps" }, "Sin posición GPS todavía"));
  return card;
}

export async function render(root, params, query) {
  document.title = "Ubicación · Car Trace";
  root.append(el("h1", { class: "page-title" }, "Ubicación"));
  const body = el("div", { class: "loc-body" });
  root.append(body);

  let dead = false, map = null, basemap = null, marker = null, markerKind = null, lastLL = null;
  let timer = null, offTheme = null, reqId = 0, last = null, mapCard = null, mapEl = null, info = null;

  const clearTimer = () => { if (timer) clearTimeout(timer); timer = null; };
  const alive = () => !dead && root.isConnected;

  function paintMap(data) {
    const p = data.point;
    if (nil(p)) {
      if (mapCard) mapCard.hidden = true;
      return;
    }
    const ll = [p.lat, p.lon];
    const kind = isLive(data.state) ? "live" : "parked";
    if (!mapCard) {
      mapEl = el("div", { class: "loc-map", role: "img", "aria-label": "Mapa con la posición del coche" });
      mapCard = el("section", { class: "card map-card" }, mapEl);
      body.prepend(mapCard);
    }
    mapCard.hidden = false;
    if (!map) {
      map = L.map(mapEl, { zoomControl: true, attributionControl: true, maxZoom: 19 });
      map.setView(ll, 16);
      lastLL = ll;
      const m = map;
      addBasemap(m, () => alive() && map === m).then((b) => {
        if (alive() && map === m) basemap = b; else b.destroy();
      });
      offTheme = onThemeChange(() => { if (basemap) basemap.retheme(); });
    } else if (!lastLL || lastLL[0] !== ll[0] || lastLL[1] !== ll[1]) {
      map.panTo(ll, { animate: true });
      lastLL = ll;
    }
    if (!marker) {
      marker = L.marker(ll, { icon: kind === "live" ? liveIcon() : parkedIcon(), keyboard: false, interactive: false }).addTo(map);
      markerKind = kind;
    } else {
      marker.setLatLng(ll);
      if (markerKind !== kind) { marker.setIcon(kind === "live" ? liveIcon() : parkedIcon()); markerKind = kind; }
    }
    map.invalidateSize();
  }

  function paint(data) {
    last = data;
    if (data.state === "no_data") {
      if (mapCard) mapCard.hidden = true;
      if (info) info.remove();
      info = el("section", { class: "card" }, emptyState("Todavía no hay datos del coche."));
      body.append(info);
      return;
    }
    paintMap(data);
    if (info) info.remove();
    info = infoCard(data);
    body.append(info);
  }

  function schedule() {
    clearTimer();
    if (!alive() || !last || !isLive(last.state) || document.visibilityState === "hidden") return;
    timer = setTimeout(() => refresh(false), POLL_MS);
  }

  async function refresh(initial) {
    clearTimer();
    const mine = ++reqId;
    if (initial) body.replaceChildren(skeleton(2), skeleton(4));
    let data;
    try {
      data = await getJSON("/api/panel/location");
    } catch (e) {
      if (!alive() || mine !== reqId) return;
      if (initial) body.replaceChildren(errorCard(() => refresh(true)));
      else schedule();
      return;
    }
    if (!alive() || mine !== reqId) return;
    if (initial) body.replaceChildren();
    paint(data);
    schedule();
  }

  const onVis = () => {
    if (!alive()) return;
    if (document.visibilityState === "hidden") clearTimer();
    else if (last) refresh(false);
  };
  document.addEventListener("visibilitychange", onVis);

  await refresh(true);

  return () => {
    dead = true;
    clearTimer();
    document.removeEventListener("visibilitychange", onVis);
    if (offTheme) offTheme();
    offTheme = null;
    if (basemap) basemap.destroy();
    basemap = null;
    if (map) map.remove();
    map = null;
    marker = null;
  };
}
