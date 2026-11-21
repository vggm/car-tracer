import { el } from "./ui.js";

export async function render(main) {
  document.title = "Trayectos · car-trace";
  main.append(el("h1", { class: "page-title" }, "Trayectos"));
}
