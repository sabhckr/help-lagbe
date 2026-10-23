/* Help Lagbe? progressive enhancement. Every page works without this file. */
(function () {
  "use strict";
  var root = document.documentElement;
  var locale = root.lang || "bn";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var M = {
    bn: {
      copied: "কপি হয়েছে", sending: "পাঠানো হচ্ছে…", notSent: "পাঠানো যায়নি। আবার চেষ্টা করুন।", connLost: "সংযোগ বিচ্ছিন্ন। আবার চেষ্টা হচ্ছে…",
      waiting: "একজন মানুষ এজেন্টের জন্য অপেক্ষা করা হচ্ছে…", closed: "এই কথোপকথন শেষ হয়েছে।", uploading: "ফাইল পাঠানো হচ্ছে",
      uploadFailed: "ফাইল পাঠানো যায়নি। আবার চেষ্টা করুন।", tooLarge: "এই ফাইলটি অনেক বড়।", badType: "এই ধরনের ফাইল অনুমোদিত নয়।", of: "সর্বোচ্চ"
    },
    en: {
      copied: "Copied", sending: "Sending…", notSent: "Not sent. Please try again.", connLost: "Connection lost. Trying again…",
      waiting: "Waiting for a human agent…", closed: "This conversation has ended.", uploading: "Uploading files",
      uploadFailed: "The files could not be uploaded. Please try again.", tooLarge: "This file is too large.", badType: "This file type is not allowed.", of: "of"
    }
  };
  var S = M[locale] || M.bn;

  /* Mobile menu */
  var toggle = document.getElementById("nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("is-open")) {
        nav.classList.remove("is-open"); toggle.setAttribute("aria-expanded", "false"); toggle.focus();
      }
    });
  }

  /* Quick exit: press Escape three times quickly */
  var escCount = 0, escTimer = null;
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") { return; }
    escCount += 1; clearTimeout(escTimer);
    escTimer = setTimeout(function () { escCount = 0; }, 1200);
    if (escCount >= 3) { leaveNow(); }
  });
  function clearAllAutosave() {
    try { Object.keys(sessionStorage).forEach(function (k) { if (k.indexOf("hl:") === 0) { sessionStorage.removeItem(k); } }); } catch (err) {}
  }
  /* Quick exit: wipe text saved in this tab, then replace this page so Back does not return to it */
  var qe = document.getElementById("quick-exit");
  function leaveNow() {
    clearAllAutosave();
    window.location.replace(qe ? qe.href : "/quick-exit");
  }
  if (qe) { qe.addEventListener("click", function (e) { e.preventDefault(); leaveNow(); }); }
  document.querySelectorAll("form[data-clear-autosave]").forEach(function (f) { f.addEventListener("submit", clearAllAutosave); });
  document.querySelectorAll("[data-print]").forEach(function (b) { b.addEventListener("click", function () { window.print(); }); });

  /* Offline banner */
  var banner = document.getElementById("offline-banner");
  function online() { if (banner) { banner.hidden = navigator.onLine !== false ? true : false; } }
  window.addEventListener("online", online); window.addEventListener("offline", function () { if (banner) { banner.hidden = false; } });

  /* Copy buttons */
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.getAttribute("data-copy"));
      if (!target || !navigator.clipboard) { return; }
      navigator.clipboard.writeText(target.textContent.trim()).then(function () {
        var old = btn.textContent; btn.textContent = S.copied; setTimeout(function () { btn.textContent = old; }, 1600);
      });
    });
  });

  /* Duplicate-submit protection */
  document.querySelectorAll("form[data-once]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.submitting === "1") { e.preventDefault(); return; }
      form.dataset.submitting = "1";
      var b = form.querySelector('button[type="submit"]:not([name="action"][value="back"])');
      if (b) { b.classList.add("is-busy"); b.setAttribute("aria-disabled", "true"); }
      if (form.hasAttribute("data-autosave")) { clearSaved(form); }
    });
  });

  /* Character counters */
  document.querySelectorAll("textarea[maxlength]").forEach(function (ta) {
    var out = document.querySelector('[data-counter-for="' + ta.id + '"]');
    if (!out) { return; }
    function update() { out.textContent = ta.value.length + " / " + ta.maxLength; }
    ta.addEventListener("input", update); update();
  });

  /* Autosave answers in this tab, so a language switch or reload keeps unsaved text */
  function key(form) { return "hl:" + form.getAttribute("data-autosave"); }
  function clearSaved(form) { try { sessionStorage.removeItem(key(form)); } catch (err) {} }
  document.querySelectorAll("form[data-autosave]").forEach(function (form) {
    var store;
    try { store = JSON.parse(sessionStorage.getItem(key(form)) || "{}"); } catch (err) { store = {}; }
    form.querySelectorAll("input[name], textarea[name], select[name]").forEach(function (el) {
      if (el.type === "hidden" || el.type === "file" || el.name === "csrf_token") { return; }
      if (store[el.name] === undefined) { return; }
      if (el.type === "radio" || el.type === "checkbox") { el.checked = (el.value === store[el.name]) || (el.type === "checkbox" && store[el.name] === true); }
      else if (!el.value) { el.value = store[el.name]; }
    });
    function save() {
      var data = {};
      form.querySelectorAll("input[name], textarea[name], select[name]").forEach(function (el) {
        if (el.type === "hidden" || el.type === "file" || el.name === "csrf_token") { return; }
        if (el.type === "radio") { if (el.checked) { data[el.name] = el.value; } }
        else if (el.type === "checkbox") { data[el.name] = el.checked ? el.value : ""; }
        else { data[el.name] = el.value; }
      });
      try { sessionStorage.setItem(key(form), JSON.stringify(data)); } catch (err) {}
    }
    var timer = null;
    form.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(save, 300); });
    form.addEventListener("change", save);
  });

  /* Identity details appear only for a confidential report */
  var identityForm = document.querySelector("[data-identity-toggle]");
  if (identityForm) {
    var panel = identityForm.querySelector("[data-identity-fields]");
    function syncIdentity() {
      var chosen = identityForm.querySelector('input[name="submission_type"]:checked');
      if (panel) { panel.hidden = !(chosen && chosen.value === "confidential"); }
    }
    identityForm.querySelectorAll('input[name="submission_type"]').forEach(function (r) { r.addEventListener("change", syncIdentity); });
    syncIdentity();
  }

  /* Evidence step: list chosen files, check type and size before sending, show upload progress */
  var evidenceForm = document.querySelector("[data-upload-progress]");
  if (evidenceForm) {
    var input = evidenceForm.querySelector('input[type="file"]');
    var picked = document.getElementById("evidence-picked");
    var maxBytes = input ? parseInt(input.getAttribute("data-max-bytes") || "0", 10) : 0;
    var allowed = ["jpg", "jpeg", "png", "webp", "pdf", "mp3", "m4a", "mp4", "txt"];
    if (input && picked) {
      input.addEventListener("change", function () {
        picked.textContent = "";
        Array.prototype.forEach.call(input.files, function (f) {
          var ext = (f.name.split(".").pop() || "").toLowerCase();
          var li = document.createElement("li");
          var msg = "";
          if (allowed.indexOf(ext) === -1) { msg = S.badType; }
          else if (maxBytes && f.size > maxBytes) { msg = S.tooLarge; }
          li.textContent = f.name + " · " + Math.max(1, Math.round(f.size / 1024)) + " KB" + (msg ? " — " + msg : "");
          picked.appendChild(li);
        });
      });
    }
    evidenceForm.addEventListener("submit", function (e) {
      if (!input || !input.files || input.files.length === 0 || !window.XMLHttpRequest || !window.FormData) { return; }
      e.preventDefault();
      var fd = new FormData(evidenceForm);
      var box = evidenceForm.querySelector(".upload-progress");
      var bar = document.getElementById("upload-progress");
      var status = document.getElementById("upload-status");
      if (box) { box.hidden = false; }
      var xhr = new XMLHttpRequest();
      xhr.open("POST", evidenceForm.action || window.location.href, true);
      xhr.upload.onprogress = function (ev) {
        if (ev.lengthComputable && bar) { bar.value = Math.round((ev.loaded / ev.total) * 100); }
        if (status) { status.textContent = S.uploading + " " + (ev.lengthComputable ? Math.round((ev.loaded / ev.total) * 100) + "%" : ""); }
      };
      xhr.onload = function () {
        if (xhr.status >= 200 && xhr.status < 400) { window.location.assign(xhr.responseURL || window.location.href); }
        else if (status) { status.textContent = S.uploadFailed; evidenceForm.dataset.submitting = "0"; }
      };
      xhr.onerror = function () { if (status) { status.textContent = S.uploadFailed; } evidenceForm.dataset.submitting = "0"; };
      xhr.send(fd);
    });
  }

  /* Live chat: polling, connection-lost state, failed sends stay in the box */
  var chat = document.querySelector("[data-chat]");
  if (chat) {
    var log = chat.querySelector(".chat__log");
    var form = chat.querySelector("form");
    var textarea = form ? form.querySelector("textarea") : null;
    var pollUrl = chat.getAttribute("data-poll"), sendUrl = chat.getAttribute("data-send");
    var last = parseInt(chat.getAttribute("data-last") || "0", 10);
    var statusEl = document.getElementById("chat-status");
    var connBanner = document.getElementById("chat-connection");
    var timer = null, failures = 0;

    function bubble(m, side) {
      var el = document.createElement("div");
      var mine = m.type === "visitor" && side === "visitor";
      el.className = "chat__bubble chat__bubble--" + (m.type === "system" ? "system" : (m.type === side ? "visitor" : "agent"));
      el.textContent = m.body;
      if (m.type !== "system") { var t = document.createElement("time"); t.textContent = m.at; el.appendChild(t); }
      log.appendChild(el);
    }
    var side = chat.getAttribute("data-side") || "visitor";
    function poll() {
      fetch(pollUrl + "?after=" + last, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { if (!r.ok) { throw new Error(String(r.status)); } return r.json(); })
        .then(function (d) {
          failures = 0; if (connBanner) { connBanner.hidden = true; }
          var atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 60;
          (d.messages || []).forEach(function (m) { bubble(m, side); last = Math.max(last, m.id); });
          if (atBottom || (d.messages || []).length) { log.scrollTop = log.scrollHeight; }
          if (statusEl) {
            if (d.status === "waiting") { statusEl.textContent = S.waiting; }
            else if (d.status === "closed") { statusEl.textContent = S.closed; if (textarea) { textarea.disabled = true; } clearInterval(timer); }
            else { statusEl.textContent = ""; }
          }
        })
        .catch(function (err) {
          if (err && /^4/.test(err.message)) { if (statusEl) { statusEl.textContent = S.closed; } clearInterval(timer); return; }
          failures += 1; if (connBanner && failures >= 2) { connBanner.hidden = false; }
        });
    }
    timer = setInterval(poll, 4000);
    poll();
    if (form && textarea) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = textarea.value.trim(); if (!body) { return; }
        var bubbleEl = null;
        textarea.disabled = true;
        if (statusEl) { statusEl.textContent = S.sending; }
        fetch(sendUrl, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, Accept: "application/json" }, body: JSON.stringify({ body: body }) })
          .then(function (r) { if (!r.ok) { throw new Error(String(r.status)); } return r.json(); })
          .then(function () { textarea.value = ""; textarea.dispatchEvent(new Event("input")); poll(); if (statusEl) { statusEl.textContent = ""; } })
          .catch(function () { if (statusEl) { statusEl.textContent = S.notSent; } textarea.value = body; })
          .finally(function () { textarea.disabled = false; textarea.focus(); });
      });
      textarea.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
    }
    log.scrollTop = log.scrollHeight;
  }

  /* Availability on the help and home pages */
  var avail = document.querySelector("[data-availability]");
  if (avail) {
    setInterval(function () {
      fetch(avail.getAttribute("data-availability"), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
        document.querySelectorAll(".status-dot").forEach(function (el) { el.classList.toggle("is-open", !!d.open); el.classList.toggle("is-closed", !d.open); });
      }).catch(function () {});
    }, 20000);
  }

  /* Service worker: public pages only; private pages are never cached */
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }
})();
