// ==UserScript==
// @name         Leylu portal helper
// @namespace    leylu
// @version      1.4
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
// 1.1 (R120, "This check timed out"): every field is filled the moment a page check loads (by label and kind, the order
// and names shuffle every load), the team key comes from Tampermonkey storage (asked once, never in this file, so no
// typing and no autofill race), the cookie wall and ad pop-ups are closed by their own close/decline buttons (never
// "Subscribe"), the cursor sits in the sum box, and a check nobody has started typing into is swapped for a fresh one
// ("New sum") after #t= seconds (default 20), so the person always gets a fresh sum. The last job is remembered, so a
// reload without the link still fills the form. Backend: #b=http://localhost:8000 (default; only
// localhost / 127.0.0.1 accepted, so a crafted link can't send the paste secret elsewhere). The backend's
// PORTAL_PASTE_SECRET is asked once and kept in Tampermonkey's storage, never in this file.
// 1.2: "New sum" and a timed-out check rebuild the whole form empty: every field is written again within 0.2 s through
// the input's native value setter (the page is React: a plain .value write is lost on its next render). Enter in the
// sum box presses the form's submit button, found by type/position (its label changes every load: "Show price",
// "Get rate", "See my rate"), never "New sum". No automatic "New sum" unless the link asks for it (#t=20).
// 1.3 (R122): after each rate the next lane airline of the link is filled at once (even if the backend send failed),
// so the person only types one sum per airline; the panel shows which one is next.
// ======== FILL IN ON YOUR OWN COMPUTER ONLY (Tampermonkey editor), never commit or share them ========
var TEAM_KEY = "";      // the 5U team key: then the script never asks for it
var PASTE_SECRET = "";  // the backend's PORTAL_PASTE_SECRET: then the script never asks for it
// =======================================================================================================
// 1.4: with the two constants above filled in, no prompt at all; otherwise each is asked once per browser (Tampermonkey
// storage, localStorage as a fallback) and never again on that page, even when the prompt is cancelled.
(function () {
  "use strict";
  var hash = new URLSearchParams(location.hash.slice(1));
  var store = typeof GM_getValue === "function";
  if (store && hash.get("d")) GM_setValue("lastJob", location.hash.slice(1));
  else if (store && !hash.get("d") && GM_getValue("lastJob", "")) hash = new URLSearchParams(GM_getValue("lastJob", ""));
  var freshS = hash.get("t") ? Math.max(5, parseFloat(hash.get("t")) || 20) : 0, loadedAt = Date.now();
  var job = {
    session: hash.get("s"), origin: (hash.get("o") || "").toUpperCase(), destination: (hash.get("d") || "").toUpperCase(),
    weight: hash.get("w") || "", volume: hash.get("v") || "",
    airlines: (hash.get("a") || "").split(",").map(function (x) { return x.trim().toUpperCase(); }).filter(Boolean),
    backend: /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(hash.get("b") || "") ? hash.get("b") : "http://localhost:8000"
  };
  var current = 0, lastSent = null, lastImage = null, lastForm = null, wasInSum = false, status = "";

  function labelOf(input) {
    var prev = input.previousElementSibling, wrap = input.parentElement;
    var text = (prev && prev.textContent) || (wrap && wrap.firstElementChild !== input && wrap.firstElementChild &&
      wrap.firstElementChild.textContent) || input.getAttribute("aria-label") || input.placeholder || "";
    return text.toLowerCase();
  }
  var asked = {};
  function kept(name, constant, question) {  // the constant, else storage, else asked once (never twice on a page)
    if (constant) return constant;
    var v = "";
    try { v = store ? GM_getValue(name, "") : (localStorage.getItem("leylu-" + name) || ""); } catch (e) { v = ""; }
    if (!v && !asked[name]) {
      asked[name] = true;
      v = (prompt(question) || "").trim();
      try { if (store) GM_setValue(name, v); else localStorage.setItem("leylu-" + name, v); } catch (e) { /* kept for this page */ }
    }
    return v;
  }
  function forget(name) {
    asked[name] = false;
    try { if (store) GM_setValue(name, ""); else localStorage.removeItem("leylu-" + name); } catch (e) { /* nothing kept */ }
  }
  function teamKey() { return kept("teamKey", TEAM_KEY, "Leylu: 5U team key for the portal (kept in this browser only)"); }
  var nativeSet = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  function setValue(input, value, force) {
    if (!value || (input.value && !force) || input.value === value) return;
    nativeSet.call(input, value);  // React keeps its own copy of the value: only the native setter + input event reach it
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function isSum(i) { return /solve|sum/.test(labelOf(i)) || i.inputMode === "numeric"; }
  function submitButton(form) {  // by type, else the last button that is not "New sum": never by its changing label
    var buttons = Array.prototype.filter.call(form.querySelectorAll("button"), function (b) {
      return !/new sum|another|refresh|reload/i.test(b.textContent) && !b.disabled;
    });
    return buttons.find(function (b) { return (b.getAttribute("type") || "submit") === "submit"; }) || buttons[buttons.length - 1];
  }
  document.addEventListener("keydown", function (e) {  // the person typed the sum and pressed Enter
    var t = e.target;
    if (e.key !== "Enter" || !t || t.tagName !== "INPUT" || !t.form || !isSum(t) || !t.value.trim()) return;
    prefill(false);  // a field the page cleared a moment ago is written again before the submit
    var b = submitButton(t.form);
    if (b) { e.preventDefault(); b.click(); }
  }, true);

  // ---- pop-ups: the ad's own close (X) button; the cookie wall: the "necessary only" choice
  function popups() {
    document.querySelectorAll("div.fixed.inset-0.z-30 button").forEach(function (x) {
      var name = (x.getAttribute("aria-label") || x.textContent || "").trim();  // never "Subscribe" or a rating
      if (/^(close|dismiss|hide|×|✕|x|no thanks|not now|maybe later|skip)$/i.test(name)) x.click();
    });
    document.querySelectorAll("div.fixed.inset-0.z-40 button").forEach(function (b) {
      if (/^(necessary only|reject optional|decline)$/i.test(b.textContent.trim())) b.click();
    });
  }

  // ---- the form: by the field's kind (datalist / input mode) and its label, never by position or name
  function prefill(forceAirline) {
    var form = document.querySelector("[data-app] form") || document.querySelector("form");
    if (!form) return;
    form.querySelectorAll("input").forEach(function (i) {
      var label = labelOf(i), list = i.getAttribute("list");
      if (i.type === "password" || /team key|api key|\bkey\b/.test(label)) {
        setValue(i, teamKey());
      } else if (isSum(i)) {
        // the sum: the person's
      } else if (list === "dl-airports" || /\(iata\)|airport/.test(label)) {
        if (/orig|from|depart/.test(label)) setValue(i, job.origin);
        else if (/dest|arriv|\bto\b/.test(label)) setValue(i, job.destination);
      } else if (list === "dl-airlines" || /airline|carrier/.test(label)) {
        setValue(i, job.airlines[current], forceAirline);
      } else if (i.inputMode === "decimal" || /weight|kg|vol|cbm/.test(label)) {
        if (/weight|kg/.test(label)) setValue(i, job.weight);
        else if (/vol|cbm|m3|m³/.test(label)) setValue(i, job.volume);
      }
    });
    // the page rebuilds the form on every pop-up and page check: the cursor goes back into the sum box (new sum, or
    // the person was typing there), never elsewhere
    var img = form.querySelector("img");
    var box = (img && img.parentElement && img.parentElement.parentElement &&
      img.parentElement.parentElement.querySelector("input")) ||
      Array.prototype.find.call(form.querySelectorAll("input"), isSum);
    var idle = !document.activeElement || document.activeElement === document.body;
    if (img && img.src !== lastImage) loadedAt = Date.now();
    if (box && (img.src !== lastImage || (form !== lastForm && (wasInSum || idle)))) box.focus();
    // a check nobody has started on gets stale: swap it for a fresh one before the person starts reading
    if (freshS && box && !box.value && Date.now() - loadedAt > freshS * 1000 && !document.querySelector("div.fixed.inset-0")) {
      var again = Array.prototype.find.call(form.querySelectorAll("button"), function (b) { return /new sum/i.test(b.textContent); });
      if (again) { loadedAt = Date.now(); again.click(); }
    }
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
    // the next lane airline at once (the page loads a fresh check after every result): one sum each, nothing to click
    if (current < job.airlines.length - 1) { current += 1; prefill(true); }
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
        if (r.status === 403 && !PASTE_SECRET) forget("pasteSecret");  // wrong secret: asked again next time
        status = r.status < 300 ? "✓ " + airline + " sent to session #" + job.session : "✗ backend " + r.status + ": " + r.responseText;
        panel();
      },
      onerror: function () { status = "✗ backend not reachable at " + job.backend; panel(); }
    });
  }

  function secret() { return kept("pasteSecret", PASTE_SECRET, "Leylu: backend paste secret (PORTAL_PASTE_SECRET)"); }

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
      " " + job.weight + " kg — type the sum, Enter" + (freshS ? " (fresh sum every " + freshS + " s)" : "") + ". Airline: "));
    job.airlines.forEach(function (code, n) {
      var b = document.createElement("button");
      b.textContent = code;
      b.style.cssText = "margin:0 2px;padding:1px 6px;border-radius:4px;border:1px solid #888;background:" +
        (n === current ? "#fff;color:#111" : "transparent;color:#fff");
      b.addEventListener("click", function () { current = n; prefill(true); panel(); });
      p.appendChild(b);
    });
    var key = document.createElement("button");
    key.textContent = "key";
    key.title = "enter the team key again";
    key.style.cssText = "margin-left:6px;padding:1px 6px;border-radius:4px;border:1px solid #888;background:transparent;color:#aaa";
    key.addEventListener("click", function () { if (!TEAM_KEY) { forget("teamKey"); prefillKeyAgain(); } });
    p.appendChild(key);
    if (status) { p.appendChild(document.createElement("br")); p.appendChild(document.createTextNode(status)); }
  }

  function prefillKeyAgain() {
    var form = document.querySelector("[data-app] form") || document.querySelector("form");
    if (!form) return;
    form.querySelectorAll("input").forEach(function (i) {
      if (i.type === "password" || /team key|api key|\bkey\b/.test(labelOf(i))) setValue(i, teamKey(), true);
    });
  }
  var queued = false;
  function tick() { queued = false; popups(); prefill(false); result(); }
  // the page rebuilds the form on "New sum" and on a timed-out check: refill at the next frame, not after a poll
  new MutationObserver(function () { if (!queued) { queued = true; requestAnimationFrame(tick); } })
    .observe(document.body, { childList: true, subtree: true });
  setInterval(tick, 200);
  panel();
})();
