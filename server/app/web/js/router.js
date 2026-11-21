let cleanup = null;
let token = 0;

export function start(routes) {
  async function run() {
    const [path, qs = ""] = location.hash.slice(1).split("?");
    let hit = null;
    for (const r of routes) {
      const m = r.re.exec(path);
      if (m) { hit = { view: r.view, params: m.slice(1) }; break; }
    }
    if (!hit) { location.replace("#/resumen"); return; }
    const mine = ++token;
    if (cleanup) { try { cleanup(); } catch (e) { console.error(e); } cleanup = null; }
    const main = document.getElementById("main");
    main.replaceChildren();
    window.scrollTo(0, 0);
    document.dispatchEvent(new CustomEvent("route", { detail: { path } }));
    let fn;
    try {
      fn = await hit.view.render(main, hit.params, new URLSearchParams(qs));
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
