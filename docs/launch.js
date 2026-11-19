"use strict";

// Fail closed: the HTML link has no href until configuration passes validation.
function configureLaunch(raw, link, status) {
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" || !url.hostname.includes(".") ||
        url.username || url.password || url.search || url.hash) return;
    link.href = url.href;
    link.removeAttribute("aria-disabled");
    link.removeAttribute("tabindex");
    status.textContent = "Open the platform to search for a pitcher and begin an analysis.";
  } catch {
    // Missing or invalid configuration keeps the explicit unavailable state.
  }
}

if (typeof document !== "undefined") {
  configureLaunch(globalThis.PAP_APP_URL, document.getElementById("launch"),
                  document.getElementById("launch-status"));
}
