import { ApiError } from "./api.js";
import { monthLong, addMonths, thisMonth } from "./fmt.js";

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "class") node.className = v;
    else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function monthPicker(month, hrefFor) {
  const prev = el("a", { class: "mp-btn", href: hrefFor(addMonths(month, -1)), "aria-label": "Mes anterior" }, "‹");
  const next = month >= thisMonth()
    ? el("span", { class: "mp-btn", "aria-disabled": "true", "aria-label": "Mes siguiente" }, "›")
    : el("a", { class: "mp-btn", href: hrefFor(addMonths(month, 1)), "aria-label": "Mes siguiente" }, "›");
  return el("div", { class: "month-picker" }, prev, el("span", { class: "mp-label" }, monthLong(month)), next);
}

export function card(title, ...children) {
  return el("section", { class: "card" }, title ? el("h2", { class: "card-title" }, title) : null, ...children);
}

export function stat(label, value, unit) {
  return el("div", { class: "stat" },
    el("div", { class: "stat-label" }, label),
    el("div", { class: "stat-value num" }, value, unit ? el("small", {}, ` ${unit}`) : null));
}

export function skeleton(lines = 3) {
  const box = el("div", { class: "card skeleton", "aria-hidden": "true" });
  for (let i = 0; i < lines; i++) {
    box.append(el("div", { class: "sk-line", style: `width:${i === 0 ? 40 : 92 - i * 12}%` }));
  }
  return box;
}

export function emptyState(text) {
  return el("div", { class: "empty" }, text);
}

export function errorCard(onRetry) {
  return el("section", { class: "card error-card", role: "alert" },
    el("p", {}, "No se pudieron cargar los datos"),
    el("button", { class: "btn", type: "button", onclick: onRetry }, "Reintentar"));
}

export async function load(main, fetcher, paint) {
  const attempt = async () => {
    main.replaceChildren(skeleton(2), skeleton(4));
    let data;
    try {
      data = await fetcher();
    } catch (e) {
      if (!(e instanceof ApiError)) console.error(e);
      if (main.isConnected) main.replaceChildren(errorCard(attempt));
      return;
    }
    if (!main.isConnected) return;
    main.replaceChildren();
    paint(data);
  };
  await attempt();
}
