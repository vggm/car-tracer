import { el } from "./ui.js";

export async function render(main) {
  document.title = "Avisos · car-trace";
  main.append(el("h1", { class: "page-title" }, "Avisos"));
}
