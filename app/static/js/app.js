/* Help Lagbe? — progressive enhancement only. The site works without this file. */
(function () {
  "use strict";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var locale = document.body.dataset.locale || "en";
  var STR = {
    en: { copied: "Copied", copy: "Copy", sending: "Sending…", offline: "You appear to be offline. Some actions will wait until you reconnect.", noAgent: "No agent is available right now.", waiting: "Waiting for a human agent…", closed: "This conversation has ended." },
    bn: { copied: "কপি হয়েছে", copy: "কপি", sending: "পাঠানো হচ্ছে…", offline: "আপনি অফলাইনে আছেন। কিছু কাজ পুনরায় সংযোগের পর হবে।", noAgent: "এই মুহূর্তে কোনো এজেন্ট নেই।", waiting: "একজন মানুষ এজেন্টের জন্য অপেক্ষা করা হচ্ছে…", closed: "এই কথোপকথন শেষ হয়েছে।" }
  };
  var s = STR[locale] || STR.en;

  // Offline banner
  var banner = document.getElementById("offline-banner");
  function updateOnline() { if (banner) { banner.hidden = navigator.onLine; } }
  window.addEventListener("online", updateOnline);
  window.addEventListener("offline", updateOnline);
  updateOnline();

  // Service worker (public pages only; private paths are excluded inside sw.js)
  if ("serviceWorker" in navigator && location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1") {
    if ("serviceWorker" in navigator) { navigator.serviceWorker.register("/sw.js").catch(function () {}); }
  }

  // Quick exit: Esc pressed three times quickly
  var escCount = 0, escTimer = null;
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") { return; }
    escCount += 1; clearTimeout(escTimer);
    escTimer = setTimeout(function () { escCount = 0; }, 1200);
    if (escCount >= 3) { var f = document.querySelector(".quick-exit"); if (f) { f.submit(); } }
  });
  var qe = document.getElementById("quick-exit");
  if (qe) { qe.addEventListener("click", function () { try { history.replaceState(null, "", "/"); } catch (err) {} }); }

  // Copy buttons
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.dataset.copy);
      if (!target || !navigator.clipboard) { return; }
      navigator.clipboard.writeText(target.textContent.trim()).then(function () {
        var old = btn.textContent; btn.textContent = s.copied; setTimeout(function () { btn.textContent = old; }, 1500);
      });
    });
  });

  // Double-submit protection + loading state
  document.querySelectorAll("form[data-once]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var b = form.querySelector('button[type="submit"]');
      if (b) { b.classList.add("is-loading"); b.setAttribute("aria-disabled", "true"); setTimeout(function () { b.disabled = true; }, 0); }
    });
  });

  // Character counters
  document.querySelectorAll("textarea[maxlength]").forEach(function (ta) {
    var c = document.createElement("div"); c.className = "char-count"; c.setAttribute("aria-live", "polite");
    ta.insertAdjacentElement("afterend", c);
    function upd() { c.textContent = ta.value.length + " / " + ta.maxLength; }
    ta.addEventListener("input", upd); upd();
  });

  // Report form: identity section follows submission type; evidence size pre-check
  var typeRadios = document.querySelectorAll('input[name="submission_type"]');
  var identity = document.getElementById("identity-section");
  function syncIdentity() {
    var v = document.querySelector('input[name="submission_type"]:checked');
    if (identity) { identity.hidden = !(v && v.value === "confidential"); }
  }
  if (typeRadios.length) { typeRadios.forEach(function (r) { r.addEventListener("change", syncIdentity); }); syncIdentity(); }
  var evidence = document.getElementById("evidence");
  if (evidence) {
    evidence.addEventListener("change", function () {
      var max = parseInt(evidence.dataset.maxBytes || "0", 10), total = 0, msg = document.getElementById("evidence-msg");
      Array.prototype.forEach.call(evidence.files, function (f) { total += f.size; });
      if (msg) { msg.textContent = (max && total > max) ? evidence.dataset.tooLarge : (evidence.files.length ? evidence.files.length + " file(s), " + Math.round(total / 1024) + " KB" : ""); }
    });
  }

  // Support presence heartbeat (agent pages)
  var hb = document.body.dataset.heartbeat;
  if (hb) {
    setInterval(function () {
      fetch(hb, { method: "POST", headers: { "X-CSRFToken": csrf }, credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
        var el = document.getElementById("waiting-count"); if (el && typeof d.waiting === "number") { el.textContent = d.waiting; }
      }).catch(function () {});
    }, 45000);
  }

  // Chat (visitor and agent share the same markup)
  var chat = document.querySelector("[data-chat]");
  if (chat) {
    var log = chat.querySelector(".chat__log");
    var form = chat.querySelector("form");
    var textarea = form ? form.querySelector("textarea") : null;
    var pollUrl = chat.dataset.poll, sendUrl = chat.dataset.send;
    var last = parseInt(chat.dataset.last || "0", 10);
    var statusEl = document.getElementById("chat-status");
    var timer;

    function bubble(m) {
      var el = document.createElement("div");
      el.className = "chat__bubble chat__bubble--" + (m.type === "visitor" ? (chat.dataset.side === "visitor" ? "visitor" : "agent") : m.type === "agent" ? (chat.dataset.side === "visitor" ? "agent" : "visitor") : "system");
      el.textContent = m.body;
      if (m.type !== "system") { var t = document.createElement("time"); t.textContent = m.at; el.appendChild(t); }
      log.appendChild(el);
    }
    function poll() {
      fetch(pollUrl + "?after=" + last, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { if (r.status === 403 || r.status === 404) { throw new Error("gone"); } return r.json(); })
        .then(function (d) {
          var atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
          (d.messages || []).forEach(function (m) { bubble(m); last = Math.max(last, m.id); });
          if (atBottom || d.messages.length) { log.scrollTop = log.scrollHeight; }
          if (statusEl) {
            if (d.status === "waiting") { statusEl.textContent = s.waiting + (d.waiting_position ? " (" + d.waiting_position + ")" : ""); }
            else if (d.status === "closed") { statusEl.textContent = s.closed; if (textarea) { textarea.disabled = true; } clearInterval(timer); }
            else { statusEl.textContent = ""; }
          }
        }).catch(function () {});
    }
    timer = setInterval(poll, 4000);
    poll();
    if (form && textarea) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = textarea.value.trim(); if (!body) { return; }
        textarea.disabled = true;
        fetch(sendUrl, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "Accept": "application/json" }, body: JSON.stringify({ body: body }) })
          .then(function (r) { return r.json(); })
          .then(function () { textarea.value = ""; textarea.dispatchEvent(new Event("input")); poll(); })
          .catch(function () { form.submit(); })
          .finally(function () { textarea.disabled = false; textarea.focus(); });
      });
      textarea.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
    }
    log.scrollTop = log.scrollHeight;
  }

  // Live availability on the support page
  var avail = document.querySelector("[data-availability]");
  if (avail) {
    setInterval(function () {
      fetch(avail.dataset.availability, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
        avail.classList.toggle("is-open", !!d.open); avail.classList.toggle("is-closed", !d.open);
        var btn = document.getElementById("start-chat"); if (btn) { btn.disabled = !d.open; }
        var n = document.getElementById("agents-online"); if (n) { n.textContent = d.agents_online; }
      }).catch(function () {});
    }, 20000);
  }
})();
