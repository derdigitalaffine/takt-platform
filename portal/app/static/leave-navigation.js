/* Progressive same-document navigation between server-authorized leave sections.
 * Only replaces the leave workspace; POST forms and other modules remain native.
 * A failed or unexpected response falls back to normal navigation.
 */
(() => {
  "use strict";
  let controller = null;
  let serial = 0;
  const isLeavePage = () => !!document.querySelector(".planning-workspace.planning-leave");
  const eligible = (link) => {
    if (!link || link.target || link.hasAttribute("download")) return false;
    const url = new URL(link.href, location.href);
    return url.origin === location.origin &&
      /^\/urlaub(?:\/|$)/.test(url.pathname) &&
      !!link.closest(".planning-leave");
  };
  async function navigate(url, push = true) {
    const requestId = ++serial;
    controller?.abort();
    controller = new AbortController();
    const current = document.querySelector(".planning-workspace.planning-leave");
    if (!current) { location.assign(url); return; }
    current.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        signal: controller.signal,
        headers: { Accept: "text/html" },
      });
      if (!response.ok || response.redirected) throw Error("Navigation nicht verfügbar");
      const html = new DOMParser().parseFromString(await response.text(), "text/html");
      const replacement = html.querySelector(".planning-workspace.planning-leave");
      if (!replacement || requestId !== serial) throw Error("Unvollständige Seite");
      window.taktDisposeLeave?.();
      window.taktDisposeLeaveWorkspace?.();
      window.taktDisposeUiPreferences?.();
      current.replaceWith(replacement);
      document.title = html.title;
      if (push) history.pushState({ leaveWorkspace: true }, "", url);
      window.taktInitLeaveWorkspace?.();
      window.taktInitUiPreferences?.();
      window.taktInitPlanningPolish?.();
      window.taktInitLeave?.();
      const heading = replacement.querySelector("h1, h2");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus({ preventScroll: true });
      }
      replacement.scrollIntoView({ block: "start" });
    } catch (error) {
      if (error.name === "AbortError") return;
      location.assign(url);
    } finally {
      if (requestId === serial) {
        document.querySelector(".planning-workspace.planning-leave")?.removeAttribute("aria-busy");
      }
    }
  }
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!eligible(link) || event.defaultPrevented || event.button !== 0 ||
        event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    // Keep external workflows, history/details and anchored links native.
    event.preventDefault();
    navigate(link.href);
  });
  window.addEventListener("popstate", () => {
    if (isLeavePage() && /^\/urlaub(?:\/|$)/.test(location.pathname))
      navigate(location.href, false);
  });
})();
