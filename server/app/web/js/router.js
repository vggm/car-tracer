// Router por hash.
// routes: [{ re, view }]; re se prueba contra location.hash sin "#" ni "?query".
// view.render(root, params, query):
//   - root: contenedor NUEVO en cada pintado (se descarta al navegar), así que
//     root.isConnected es false cuando una respuesta tardía llega a destiempo.
//   - params: capturas de la regex, YA DECODIFICADAS (decodeURIComponent).
//     Para llamar a la API hay que volver a codificarlas: encodeURIComponent(id).
//   - query: URLSearchParams del "?..." del hash.
//   - puede devolver una función de limpieza, que se llama antes del siguiente pintado.
let cleanup = null;
let token = 0;

const decode = (s) => {
  if (s === undefined) return s;
  try { return decodeURIComponent(s); } catch (e) { return s; }
};

export function start(routes) {
  async function run() {
    const [path, qs = ""] = location.hash.slice(1).split("?");
    let hit = null;
    for (const r of routes) {
      const m = r.re.exec(path);
      if (m) { hit = { view: r.view, params: m.slice(1).map(decode) }; break; }
    }
    if (!hit) { location.replace("#/resumen"); return; }
    const mine = ++token;
    if (cleanup) { try { cleanup(); } catch (e) { console.error(e); } cleanup = null; }
    const root = document.createElement("div");
    document.getElementById("main").replaceChildren(root);
    window.scrollTo(0, 0);
    document.dispatchEvent(new CustomEvent("route", { detail: { path } }));
    let fn;
    try {
      fn = await hit.view.render(root, hit.params, new URLSearchParams(qs));
    } catch (e) {
      console.error(e);
    }
    if (typeof fn === "function") {
      if (mine === token) cleanup = fn; else fn();
    }
  }
  window.addEventListener("hashchange", run);
  return run();
}
