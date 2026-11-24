import test from "node:test";
import assert from "node:assert/strict";
import { groupDtc } from "../../app/web/js/dtcgroups.js";

const c = (code, desc = `d${code}`) => ({ code, desc });

test("groupDtc: both empty", () => {
  assert.deepEqual(groupDtc([], []), { confirmed: [], watching: [] });
});

test("groupDtc: only active", () => {
  const r = groupDtc([c("P0100")], []);
  assert.deepEqual(r.confirmed, [{ code: "P0100", desc: "dP0100", recurring: false }]);
  assert.deepEqual(r.watching, []);
});

test("groupDtc: only pending", () => {
  const r = groupDtc([], [c("P0200")]);
  assert.deepEqual(r.confirmed, []);
  assert.deepEqual(r.watching, [{ code: "P0200", desc: "dP0200" }]);
});

test("groupDtc: overlap is confirmed + recurring, not watching", () => {
  const r = groupDtc([c("P0100"), c("P0101")], [c("P0101"), c("P0300")]);
  assert.deepEqual(r.confirmed.map((x) => [x.code, x.recurring]), [["P0100", false], ["P0101", true]]);
  assert.deepEqual(r.watching.map((x) => x.code), ["P0300"]);
});

test("groupDtc: pending equal to active leaves watching empty", () => {
  const r = groupDtc([c("P0100"), c("P0101")], [c("P0101"), c("P0100")]);
  assert.equal(r.watching.length, 0);
  assert.ok(r.confirmed.every((x) => x.recurring));
});

test("groupDtc: duplicates within a list are deduped", () => {
  const r = groupDtc([c("P0100"), c("P0100")], [c("P0200"), c("P0200")]);
  assert.equal(r.confirmed.length, 1);
  assert.equal(r.watching.length, 1);
});

test("groupDtc: order preserved", () => {
  const r = groupDtc([c("P3"), c("P1"), c("P2")], [c("P9"), c("P5")]);
  assert.deepEqual(r.confirmed.map((x) => x.code), ["P3", "P1", "P2"]);
  assert.deepEqual(r.watching.map((x) => x.code), ["P9", "P5"]);
});

test("groupDtc: null/undefined lists are empty", () => {
  assert.deepEqual(groupDtc(null, undefined), { confirmed: [], watching: [] });
  assert.equal(groupDtc(undefined, [c("P1")]).watching.length, 1);
});
