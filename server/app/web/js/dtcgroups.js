// Agrupa los códigos de avería para que cada uno salga en un solo grupo.
// active = confirmadas (modo 03); pending = en observación (modo 07).
const uniq = (list) => {
  const seen = new Set();
  const out = [];
  for (const c of list || []) {
    if (seen.has(c.code)) continue;
    seen.add(c.code);
    out.push(c);
  }
  return out;
};

export function groupDtc(active, pending) {
  const act = uniq(active);
  const pend = uniq(pending);
  const pendCodes = new Set(pend.map((c) => c.code));
  const actCodes = new Set(act.map((c) => c.code));
  return {
    confirmed: act.map((c) => ({ code: c.code, desc: c.desc, recurring: pendCodes.has(c.code) })),
    watching: pend.filter((c) => !actCodes.has(c.code)).map((c) => ({ code: c.code, desc: c.desc })),
  };
}
