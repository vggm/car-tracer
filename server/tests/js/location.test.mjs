import test from "node:test";
import assert from "node:assert/strict";
import { isLive, stateLabel, directionsUrl, subtitle, agoText } from "../../app/web/js/locationlogic.js";

test("isLive", () => {
  for (const s of ["moving", "idle", "engine_off", "stopped"]) assert.equal(isLive(s), true, s);
  for (const s of ["parked", "no_signal", "no_data", "x", undefined]) assert.equal(isLive(s), false, String(s));
});

test("stateLabel", () => {
  assert.equal(stateLabel("moving"), "En marcha");
  assert.equal(stateLabel("idle"), "Parado, motor encendido");
  assert.equal(stateLabel("engine_off"), "Contacto puesto, motor apagado");
  assert.equal(stateLabel("stopped"), "Parado");
  assert.equal(stateLabel("parked"), "Aparcado");
  assert.equal(stateLabel("no_signal"), "Sin señal");
  assert.equal(stateLabel("no_data"), "Sin datos");
});

test("directionsUrl android", () => {
  const u = directionsUrl(40.4168, -3.7038, "Mozilla/5.0 (Linux; Android 14) Chrome");
  assert.equal(u, "geo:40.416800,-3.703800?q=40.416800,-3.703800(Coche)");
});

test("directionsUrl other", () => {
  const u = directionsUrl(40.4168, -3.7038, "Mozilla/5.0 (X11; Linux x86_64)");
  assert.equal(u, "https://www.openstreetmap.org/?mlat=40.416800&mlon=-3.703800#map=18/40.416800/-3.703800");
});

test("agoText", () => {
  assert.equal(agoText(10_000, 16_000), "hace 6 s");
  assert.equal(agoText(0, 5 * 60_000), "hace 5 min");
  assert.equal(agoText(0, (2 * 60 + 15) * 60_000), "hace 2 h 15 min");
  assert.equal(agoText(0, 3 * 3600_000), "hace 3 h");
  assert.equal(agoText(0, 2 * 86400_000), "hace 2 días");
  assert.equal(agoText(0, 86400_000), "hace 1 día");
  assert.equal(agoText(5000, 1000), "hace 0 s");
});

test("subtitle", () => {
  const now = Date.parse("2026-01-15T12:00:00Z");
  const last = now - 6000;
  assert.equal(subtitle({ state: "moving", last_ts: last }, now), "Último dato hace 6 s");
  assert.match(subtitle({ state: "parked", last_ts: now - 3600_000 }, now), /^Desde las \d\d:\d\d · hace 1 h$/);
  assert.match(subtitle({ state: "no_signal", last_ts: now - 3600_000 }, now), /^Desde las \d\d:\d\d · iba en marcha$/);
  assert.equal(subtitle({ state: "no_data", last_ts: null }, now), "");
  assert.equal(subtitle({ state: "parked", last_ts: null }, now), "");
});
