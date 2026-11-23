import test from "node:test";
import assert from "node:assert/strict";
import { segVar, bearingDeg, arrowsAlong, LANE_PX, offsetPath, shiftPx, endBearings } from "../../app/web/js/segmap.js";

test("segVar: single segment uses the accent", () => {
  assert.equal(segVar(0, 1), "--accent");
});

test("segVar: multiple segments use the palette and wrap after 6", () => {
  assert.equal(segVar(0, 3), "--seg-1");
  assert.equal(segVar(2, 3), "--seg-3");
  assert.equal(segVar(5, 8), "--seg-6");
  assert.equal(segVar(6, 8), "--seg-1");
  assert.equal(segVar(7, 8), "--seg-2");
});

test("bearingDeg: cardinal directions", () => {
  // El rumbo inicial por círculo máximo se desvía algo de 90/270 al ir por un paralelo.
  const near = (x, y) => assert.ok(Math.abs(x - y) < 0.5, `got ${x}, want ${y}`);
  near(bearingDeg([40, -3], [41, -3]), 0);
  near(bearingDeg([40, -3], [40, -2]), 90);
  near(bearingDeg([40, -3], [39, -3]), 180);
  near(bearingDeg([40, -3], [40, -4]), 270);
});

test("bearingDeg stays within [0, 360)", () => {
  const b = bearingDeg([40, -3], [40.001, -3.001]);
  assert.ok(b >= 0 && b < 360);
  assert.ok(b > 270 && b < 360, `got ${b}`);
});

test("arrowsAlong: fewer than 2 points or zero length gives none", () => {
  assert.deepEqual(arrowsAlong([]), []);
  assert.deepEqual(arrowsAlong([[40, -3, 0]]), []);
  assert.deepEqual(arrowsAlong([[40, -3, 0], [40, -3, 1]]), []);
});

test("arrowsAlong: short route (< 1500 m) has one arrow at the middle", () => {
  // 0.01 deg of latitude ~ 1112 m, heading north
  const a = arrowsAlong([[40, -3, 0], [40.01, -3, 1]]);
  assert.equal(a.length, 1);
  assert.ok(Math.abs(a[0].lat - 40.005) < 1e-6);
  assert.ok(Math.abs(a[0].lon - -3) < 1e-9);
  assert.ok(Math.abs(a[0].bearing) < 0.01);
});

test("arrowsAlong: long route (>= 1500 m) has three arrows at 25/50/75 %", () => {
  // 0.04 deg ~ 4448 m, heading east-ish along a parallel
  const a = arrowsAlong([[40, -3, 0], [40, -2.96, 1]]);
  assert.equal(a.length, 3);
  assert.ok(Math.abs(a[0].lon - -2.99) < 1e-6);
  assert.ok(Math.abs(a[1].lon - -2.98) < 1e-6);
  assert.ok(Math.abs(a[2].lon - -2.97) < 1e-6);
  assert.ok(Math.abs(a[1].bearing - 90) < 0.1);
});

test("arrowsAlong: bearing follows the containing segment and skips zero-length ones", () => {
  // north 0.02 deg, then a duplicate point, then east
  const pts = [[40, -3, 0], [40.02, -3, 1], [40.02, -3, 2], [40.02, -2.97, 3]];
  const a = arrowsAlong(pts);
  assert.equal(a.length, 3);
  assert.ok(Math.abs(a[0].bearing) < 0.01); // 25 %: still going north
  assert.ok(Math.abs(a[2].bearing - 90) < 0.1); // 75 %: going east
});

const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `got ${a}, want ${b}`);

test("LANE_PX is 3", () => {
  assert.equal(LANE_PX, 3);
});

test("offsetPath: eastward line shifts y by d (right of travel, y down)", () => {
  const r = offsetPath([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 20, y: 0 }], 3);
  assert.equal(r.length, 3);
  r.forEach((p, i) => { close(p.y, 3); close(p.x, i * 10); });
});

test("offsetPath: northward line shifts x by d", () => {
  const r = offsetPath([{ x: 0, y: 20 }, { x: 0, y: 10 }, { x: 0, y: 0 }], 3);
  r.forEach((p, i) => { close(p.x, 3); close(p.y, 20 - i * 10); });
});

test("offsetPath: right-angle corner uses a miter of length d*sqrt2", () => {
  // este y luego sur (y crece): giro a la derecha
  const r = offsetPath([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }], 3);
  const m = r[1];
  close(Math.hypot(m.x - 10, m.y - 0), 3 * Math.SQRT2);
  close(m.x, 10 - 3);
  close(m.y, 3);
});

test("offsetPath: duplicate points stay finite", () => {
  const r = offsetPath([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 0 }, { x: 20, y: 0 }], 3);
  assert.equal(r.length, 4);
  r.forEach((p) => { assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y)); close(p.y, 3); });
});

test("offsetPath: 180 degree hairpin stays finite and bounded", () => {
  const r = offsetPath([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 0 }], 3);
  const orig = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 0 }];
  r.forEach((p, i) => {
    assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));
    assert.ok(Math.hypot(p.x - orig[i].x, p.y - orig[i].y) <= 2 * 3 + 1e-9);
  });
});

test("offsetPath: fewer than 2 points or zero length returns an unchanged copy", () => {
  const one = [{ x: 1, y: 2 }];
  const r = offsetPath(one, 3);
  assert.deepEqual(r, one);
  assert.notEqual(r, one);
  assert.deepEqual(offsetPath([], 3), []);
  const z = [{ x: 1, y: 1 }, { x: 1, y: 1 }];
  assert.deepEqual(offsetPath(z, 3), z);
});

test("shiftPx: moves d px to the right of the heading", () => {
  const p = { x: 5, y: 5 };
  let r = shiftPx(p, 0, 3);
  close(r.x, 8); close(r.y, 5);
  r = shiftPx(p, 90, 3);
  close(r.x, 5); close(r.y, 8);
  r = shiftPx(p, 180, 3);
  close(r.x, 2); close(r.y, 5);
});

test("endBearings: first and last non-zero-length pairs", () => {
  const pts = [[40, -3, 0], [40, -3, 1], [40.01, -3, 2], [40.01, -2.99, 3], [40.01, -2.99, 4]];
  const b = endBearings(pts);
  close(b.first, 0, 0.01);
  close(b.last, 90, 0.1);
});

test("endBearings: none when no usable pair", () => {
  assert.deepEqual(endBearings([]), { first: null, last: null });
  assert.deepEqual(endBearings([[40, -3, 0]]), { first: null, last: null });
  assert.deepEqual(endBearings([[40, -3, 0], [40, -3, 1]]), { first: null, last: null });
});
