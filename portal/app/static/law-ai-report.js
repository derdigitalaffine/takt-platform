/* Report generation is local browser printing; no POST, publication or upload. */
(() => {
  "use strict";
  const button = document.querySelector("[data-law-report-print]");
  button?.addEventListener("click", () => window.print());
})();
