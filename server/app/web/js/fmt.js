export const TZ = "Europe/Madrid";
const LOC = "es-ES";
const num1 = new Intl.NumberFormat(LOC, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const num0 = new Intl.NumberFormat(LOC, { maximumFractionDigits: 0 });
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const f = (opts) => new Intl.DateTimeFormat(LOC, { timeZone: TZ, ...opts });
const fHour = f({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const fDay = f({ weekday: "long", day: "numeric", month: "long" });
const fDate = f({ day: "numeric", month: "short", year: "numeric" });
const fMonthLong = new Intl.DateTimeFormat(LOC, { timeZone: "UTC", month: "long", year: "numeric" });
const fMonth = new Intl.DateTimeFormat(LOC, { timeZone: "UTC", month: "long" });
const fParts = f({ year: "numeric", month: "2-digit" });
const fIso = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ });

const nil = (x) => x === null || x === undefined || Number.isNaN(x);
const ym = (m) => {
  const [y, mo] = m.split("-").map(Number);
  return new Date(Date.UTC(y, mo - 1, 1));
};

export const n1 = (x) => (nil(x) ? "—" : num1.format(x));
export const n0 = (x) => (nil(x) ? "—" : num0.format(Math.round(x)));
// "YYYY-MM-DD" local (Europe/Madrid) de un ms UTC.
export const localDate = (ts) => fIso.format(ts);
export const monthOf = (ts) => localDate(ts).slice(0, 7);
export const today = () => localDate(Date.now());
// "20 sep": mismo criterio de abreviar que las etiquetas del mapa de calor (3 letras).
export const dayMonth = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${fMonth.format(new Date(Date.UTC(y, m - 1, 1))).slice(0, 3)}`;
};

export const km = (x) => (nil(x) ? "—" : `${num1.format(x)} km`);
export const kmh = (x) => (nil(x) ? "—" : `${num0.format(Math.round(x))} km/h`);
export const dur = (ms) => {
  if (nil(ms)) return "—";
  const min = Math.round(ms / 60000);
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
};
export const hhmm = (ts) => fHour.format(ts);
export const dayLong = (ts) => cap(fDay.format(ts).replace(",", ""));
export const monthLong = (m) => fMonthLong.format(ym(m)).replace(" de ", " ");
export const monthName = (m) => fMonth.format(ym(m));
export const dateShort = (ts) => `${fDate.format(ts).replace(/\./g, "")}, ${hhmm(ts)}`;
export const rel = (ts) => {
  const s = Math.max(0, (Date.now() - ts) / 1000);
  if (s < 60) return "hace un momento";
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  const d = Math.floor(s / 86400);
  return d === 1 ? "hace 1 día" : `hace ${d} días`;
};
export const addMonths = (m, n) => {
  const d = ym(m);
  d.setUTCMonth(d.getUTCMonth() + n);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};
export const thisMonth = () => {
  const p = Object.fromEntries(fParts.formatToParts(Date.now()).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}`;
};
