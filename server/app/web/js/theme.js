// Tema claro/oscuro: data-theme en <html> (si hay elección guardada) o sistema.
const KEY = "ct.theme";
const mq = window.matchMedia("(prefers-color-scheme: light)");
const root = document.documentElement;

const stored = () => {
  try { const v = localStorage.getItem(KEY); return v === "light" || v === "dark" ? v : null; } catch { return null; }
};

export const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : !mq.matches);

function syncButton() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.setAttribute("aria-label", isDark() ? "Cambiar a tema claro" : "Cambiar a tema oscuro");
  btn.title = btn.getAttribute("aria-label");
}

function apply(emit) {
  const dark = isDark();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = dark ? "#111315" : "#f6f5f2";
  syncButton();
  if (emit) document.dispatchEvent(new CustomEvent("themechange", { detail: { dark } }));
}

export function initTheme() {
  const s = stored();
  if (s) root.dataset.theme = s;
  apply(false);
  mq.addEventListener("change", () => { if (!stored()) apply(true); });
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch { /* sin almacenamiento */ }
    apply(true);
  });
}

// Suscripción a cambios de tema; devuelve la función para darse de baja.
export function onThemeChange(fn) {
  document.addEventListener("themechange", fn);
  return () => document.removeEventListener("themechange", fn);
}
