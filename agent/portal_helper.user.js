// ==UserScript==
// @name         Leylu portal helper
// @namespace    leylu
// @version      1.0
// @description  5U rate portal: closes the ad pop-ups (their X, never the ad button), prefills the form from the
//               push link (#s=41&o=FRA&d=LAX&w=300&v=1.1&a=GN,MD), focuses the sum, sends "Your rate" to the local backend.
// @match        https://start-hack.5u.ai/portal/ui*
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @connect      localhost
// @connect      127.0.0.1
// ==/UserScript==
// A person solves the sum and presses Enter. This script never reads, solves or fills the sum.
// The API key field is left to the browser's own autofill. Backend: #b=http://localhost:8000 (default; only
// localhost / 127.0.0.1 accepted, so a crafted link can't send the paste secret elsewhere). The backend's
// PORTAL_PASTE_SECRET is asked once and kept in Tampermonkey's storage, never in this file.
(function () {
  "use strict";
  var hash = new URLSearchParams(location.hash.slice(1));
  var job = {
    session: hash.get("s"), origin: (hash.get("o") || "").toUpperCase(), destination: (hash.get("d") || "").toUpperCase(),
    weight: hash.get("w") || "", volume: hash.get("v") || "",
    airlines: (hash.get("a") || "").split(",").map(function (x) { return x.trim().toUpperCase(); }).filter(Boolean),
    backend: /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(hash.get("b") || "") ? hash.get("b") : "http://localhost:8000"
  };
  var current = 0, lastSent = null, lastImage = null, lastForm = null, wasInSum = false, status = "";

  function labelOf(input) {
    var prev = input.previousElementSibling;
    return ((prev && prev.textContent) || input.name || "").toLowerCase();
  }
  function setValue(input, value, force) {
    if (!value || (input.value && !force)) return;
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // ---- pop-ups: the ad's own close (X) button; the cookie wall: the "necessary only" choice
  function popups() {
    document.querySelectorAll("div.fixed.inset-0.z-30 button[aria-label]").forEach(function (x) {
      if (/^(close|dismiss|hide)$/i.test(x.getAttribute("aria-label") || "")) x.click();
    });
    document.querySelectorAll("div.fixed.inset-0.z-40 button").forEach(function (b) {
      if (/^(necessary only|reject optional|decline)$/i.test(b.textContent.trim())) b.click();
    });
  }

  // ---- the form: by the field's kind (datalist / input mode) and its label, never by position or name
  function prefill(forceAirline) {
    var form = document.querySelector("[data-app] form");
    if (!form) return;
    form.querySelectorAll("input").forEach(function (i) {
      var label = labelOf(i), list = i.getAttribute("list");
      if (list === "dl-airports") {
        if (/orig|from|depart/.test(label)) setValue(i, job.origin);
        else if (/dest|arriv|\bto\b/.test(label)) setValue(i, job.destination);
      } else if (list === "dl-airlines") {
        setValue(i, job.airlines[current], forceAirline);
      } else if (i.inputMode === "decimal") {
        if (/weight|kg/.test(label)) setValue(i, job.weight);
        else if (/vol|cbm|m3|m³/.test(label)) setValue(i, job.volume);
      }
    });
    // the page rebuilds the form on every pop-up and page check: the cursor goes back into the sum box (new sum, or
    // the person was typing there), never elsewhere
    var img = form.querySelector("img");
    var box = img && img.parentElement && img.parentElement.parentElement &&
      img.parentElement.parentElement.querySelector("input");
    var idle = !document.activeElement || document.activeElement === document.body;
    if (box && (img.src !== lastImage || (form !== lastForm && (wasInSum || idle)))) box.focus();
    lastImage = img ? img.src : lastImage;
    lastForm = form;
    wasInSum = !!box && document.activeElement === box;
  }

  // ---- "Your rate": to the backend once, then the next airline
  function result() {
    var heads = Array.prototype.filter.call(document.querySelectorAll("[data-app] h2"), function (h) {
      return /your rate/i.test(h.textContent);
    });
    if (!heads.length || !job.session) return;
    var text = heads[0].parentElement.innerText;
    if (text === lastSent) return;
    lastSent = text;
    var airline = job.airlines[current] || "";
    if (typeof GM_xmlhttpRequest !== "function") {  // the bookmarklet: no cross-site send, the person forwards it
      var total = (text.match(/total[^\d]{0,20}([\d.,]+)/i) || [])[1] || "?";
      var days = (text.match(/(\d+)\s*days?/i) || [])[1] || "";
      var id = (text.match(/\bR-[A-Za-z0-9-]+/) || [""])[0];
      status = "Run: uv run python portal_rate.py " + job.session + " " + airline + " " + total + " " + days + " " + id;
      panel();
      return;
    }
    GM_xmlhttpRequest({
      method: "POST", url: job.backend + "/api/sessions/" + job.session + "/portal-rate",
      headers: { "Content-Type": "application/json", "X-Paste-Secret": secret() },
      data: JSON.stringify({ airline: airline, origin: job.origin, destination: job.destination, text: text }),
      onload: function (r) {
        if (r.status === 403) GM_setValue("pasteSecret", "");  // wrong secret: asked again next time
        status = r.status < 300 ? "✓ " + airline + " sent to session #" + job.session : "✗ backend " + r.status + ": " + r.responseText;
        if (r.status < 300 && current < job.airlines.length - 1) { current += 1; prefill(true); }
        panel();
      },
      onerror: function () { status = "✗ backend not reachable at " + job.backend; panel(); }
    });
  }

  function secret() {  // the backend's PORTAL_PASTE_SECRET, asked once, kept in Tampermonkey storage (never in this file)
    var s = GM_getValue("pasteSecret", "");
    if (!s) { s = (prompt("Leylu: backend paste secret (PORTAL_PASTE_SECRET)") || "").trim(); GM_setValue("pasteSecret", s); }
    return s;
  }

  function panel() {
    var p = document.getElementById("leylu-panel");
    if (!p) {
      p = document.createElement("div");
      p.id = "leylu-panel";
      p.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:60;background:#111;color:#fff;font:12px system-ui;" +
        "padding:8px 10px;border-radius:8px;max-width:300px;box-shadow:0 2px 8px rgba(0,0,0,.3)";
      document.body.appendChild(p);
    }
    p.innerHTML = "";
    p.appendChild(document.createTextNode("Leylu #" + (job.session || "?") + " " + job.origin + "→" + job.destination +
      " " + job.weight + " kg — type the sum, Enter. Airline: "));
    job.airlines.forEach(function (code, n) {
      var b = document.createElement("button");
      b.textContent = code;
      b.style.cssText = "margin:0 2px;padding:1px 6px;border-radius:4px;border:1px solid #888;background:" +
        (n === current ? "#fff;color:#111" : "transparent;color:#fff");
      b.addEventListener("click", function () { current = n; prefill(true); panel(); });
      p.appendChild(b);
    });
    if (status) { p.appendChild(document.createElement("br")); p.appendChild(document.createTextNode(status)); }
  }

  function tick() { popups(); prefill(false); result(); }
  new MutationObserver(tick).observe(document.body, { childList: true, subtree: true });
  setInterval(tick, 500);
  panel();
})();
