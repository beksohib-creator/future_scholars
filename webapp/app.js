(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready(); tg.expand();
    document.documentElement.classList.add("tg");
    if (tg.colorScheme === "dark") document.documentElement.classList.add("dark");
  }
  const devUser = new URLSearchParams(location.search).get("dev_user");

  const state = { me: null, schema: {}, tab: "guide", userId: null, users: [], cache: {} };
  const $ = (s) => document.querySelector(s);
  const view = $("#view");

  // ------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const linkify = (s) => esc(s).replace(/https?:\/\/[^\s<]+/g, (u) => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`);
  const num = (n) => (Math.round(Number(n || 0) * 100) / 100).toLocaleString("uz-UZ");

  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2600);
  }
  function haptic(type = "light") { try { tg && tg.HapticFeedback.impactOccurred(type); } catch (_) {} }

  async function api(method, path, body) {
    const headers = { "Content-Type": "application/json", "X-Init-Data": (tg && tg.initData) || "" };
    if (devUser) headers["X-Dev-User"] = devUser;
    let url = "/api/" + path;
    if (state.me && state.me.is_admin && state.userId && !path.startsWith("users") && !path.startsWith("me")) {
      url += (url.includes("?") ? "&" : "?") + "user_id=" + state.userId;
    }
    const r = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(data.error || "Xatolik"), { status: r.status });
    return data;
  }

  // ------------------------------------------------------------ card config
  const CARD = {
    universities: {
      title: (r) => r.name, sub: (r) => [r.country, r.major].filter(Boolean).join(" · "),
      pill: (r) => r.level ? [r.level, r.level.toLowerCase()] : null,
      skip: ["name", "country", "major", "level"],
    },
    activities: {
      title: (r) => r.name, sub: (r) => [r.date, r.kind, r.hours ? r.hours + " soat" : ""].filter(Boolean).join(" · "),
      pill: (r) => r.kind ? [r.kind, ""] : null,
      skip: ["name", "date", "kind", "hours"],
    },
    weekly: {
      title: (r) => (r.week ? r.week + "-hafta" : "Vazifa") + (r.range ? " · " + r.range : ""),
      sub: (r) => r.due ? "Muddat: " + r.due : "",
      pill: (r) => r.status ? [r.status, { Bajarildi: "ok", Jarayonda: "warn" }[r.status] || ""] : ["Boshlanmagan", ""],
      skip: ["week", "range", "due", "status"],
    },
    tests: {
      title: (r) => r.test, sub: (r) => [r.date, r.score ? "Natija: " + r.score : "", r.target ? "Maqsad: " + r.target : ""].filter(Boolean).join(" · "),
      pill: null, skip: ["test", "date", "score", "target"],
    },
  };

  // ------------------------------------------------------------ tabs
  function tabsList() {
    const t = [["guide", "📘 Ko'rsatma"]];
    for (const [k, s] of Object.entries(state.schema)) t.push([k, `${s.icon} ${s.title}`]);
    if (state.me.is_admin) t.push(["users", "👥 O'quvchilar"]);
    return t;
  }
  function renderTabs() {
    $("#tabs").innerHTML = tabsList().map(([k, l]) =>
      `<button class="tab" role="tab" data-tab="${k}" aria-selected="${k === state.tab}">${l}</button>`).join("");
  }
  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]"); if (!b) return;
    state.tab = b.dataset.tab; haptic(); renderTabs(); render();
  });

  // ------------------------------------------------------------ user picker (admin)
  function renderPicker() {
    const p = $("#userPicker");
    if (!state.me.is_admin) { p.hidden = true; return; }
    p.hidden = false;
    const opts = state.users.map((u) => `<option value="${u.tg_id}">${esc(u.name)}</option>`);
    p.innerHTML = opts.length ? opts.join("") : `<option value="">O'quvchi yo'q</option>`;
    if (!state.users.some((u) => String(u.tg_id) === String(state.userId))) state.userId = state.users[0] ? state.users[0].tg_id : null;
    p.value = state.userId ?? "";
  }
  $("#userPicker").addEventListener("change", (e) => {
    state.userId = e.target.value; state.cache = {};
    if (state.tab === "users") state.tab = "universities";
    renderTabs(); render();
  });

  function currentName() {
    if (!state.me.is_admin) return state.me.name;
    const u = state.users.find((x) => String(x.tg_id) === String(state.userId));
    return u ? u.name : "";
  }

  // ------------------------------------------------------------ views
  async function render() {
    if (state.tab === "guide") return renderGuide();
    if (state.tab === "users") return renderUsers();
    if (state.me.is_admin && !state.userId) {
      view.innerHTML = `<div class="empty">Avval «👥 O'quvchilar» bo'limida o'quvchi qo'shing.</div>`; return;
    }
    return renderSection(state.tab);
  }

  function renderGuide() {
    const s = state.schema;
    view.innerHTML = `
      <div class="section-head"><h1>Ish jadvali</h1></div>
      <p class="hint">Bu jadvalni mentor bilan birgalikda to'ldirib borasiz. Har hafta yangilang.</p>
      <div class="guide"><h2>Qanday ishlatiladi</h2><ol>
        <li>Faqat <span class="swatch"></span>och sariq maydonlarni to'ldiring. 🔒 belgili maydonlarni mentor to'ldiradi.</li>
        <li>Yangi yozuv qo'shish uchun bo'limdagi «+ Qo'shish» tugmasini bosing, tahrirlash uchun kartani bosing.</li>
        <li>Har bir ma'lumot uchun manba havolasini qo'ying. Universitet ma'lumotlarini faqat rasmiy saytdan oling.</li>
      </ol></div>
      <div class="guide"><h2>Bo'limlar</h2><ul>
        ${Object.entries(s).map(([k, x]) => `<li><a href="#" data-go="${k}">${x.icon} ${esc(x.title)}</a> — ${esc(x.hint)}</li>`).join("")}
      </ul></div>
      <div class="guide"><h2>Maxfiylik</h2><p class="hint" style="margin:0">Siz kiritgan ma'lumotlar faqat sizga va mentoringizga ko'rinadi.</p></div>`;
    view.querySelectorAll("[data-go]").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault(); state.tab = a.dataset.go; renderTabs(); render();
    }));
  }

  async function renderSection(key) {
    const sch = state.schema[key];
    view.innerHTML = `<div class="hint">Yuklanmoqda…</div>`;
    let rows, stats;
    try { [rows, stats] = await Promise.all([api("GET", "records/" + key), api("GET", "stats")]); }
    catch (e) { view.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    if (state.tab !== key) return;
    state.cache[key] = rows;

    const canCreate = !sch.admin_create || state.me.is_admin;
    const who = state.me.is_admin ? `<p class="hint">O'quvchi: <b>${esc(currentName())}</b></p>` : "";
    view.innerHTML = `
      <div class="section-head"><h1>${sch.icon} ${esc(sch.title)}</h1>
        ${canCreate ? `<button class="btn primary small" id="addBtn">+ Qo'shish</button>` : ""}</div>
      ${who}<p class="hint">${esc(sch.hint)}</p>
      ${statsBlock(key, stats, rows)}
      <div class="list">${rows.length ? rows.map((r) => cardHtml(key, r)).join("") :
        `<div class="empty">Hali yozuv yo'q.${canCreate ? " «+ Qo'shish» tugmasini bosing." : " Mentor vazifa qo'shishini kuting."}</div>`}</div>`;
    const add = $("#addBtn"); if (add) add.onclick = () => openForm(key, null);
    view.querySelectorAll("[data-id]").forEach((c) => c.addEventListener("click", () => {
      openForm(key, rows.find((r) => String(r.id) === c.dataset.id));
    }));
  }

  function statsBlock(key, st, rows) {
    if (key === "universities") {
      const pct = Math.min(100, (st.universities / 10) * 100);
      const lv = (l) => rows.filter((r) => r.level === l).length;
      return `<div class="stats">
        <div class="stat"><b>${st.universities} / 10</b><span>To'ldirilgan universitetlar</span><div class="bar"><i style="width:${pct}%"></i></div></div>
        <div class="stat"><b>${lv("Reach")} · ${lv("Match")} · ${lv("Safety")}</b><span>Reach · Match · Safety</span></div></div>`;
    }
    if (key === "activities") {
      const max = Math.max(1, ...Object.values(st.hours_by_kind));
      return `<div class="stats">
          <div class="stat"><b>${num(st.hours_total)}</b><span>Jami soat</span></div>
          <div class="stat"><b>${st.activities}</b><span>Faoliyatlar soni</span></div></div>
        <div class="kinds">${Object.entries(st.hours_by_kind).map(([k, v]) =>
          `<div class="kind-row"><span>${esc(k)}</span><div class="bar"><i style="width:${(v / max) * 100}%"></i></div><em>${num(v)}</em></div>`).join("")}</div>`;
    }
    if (key === "weekly") {
      return `<div class="stats">
        <div class="stat"><b>${st.tasks_done} / ${st.tasks_total}</b><span>Bajarildi / Jami vazifalar</span></div>
        <div class="stat"><b>${st.tasks_percent}%</b><span>Bajarilgan foiz</span><div class="bar"><i style="width:${st.tasks_percent}%"></i></div></div>
        <div class="stat"><b>${num(st.avg_score)}</b><span>O'rtacha ball</span></div></div>`;
    }
    return "";
  }

  function cardHtml(key, r) {
    const c = CARD[key], sch = state.schema[key];
    const pill = c.pill && c.pill(r);
    const body = sch.fields.filter((f) => !c.skip.includes(f.key) && r[f.key])
      .map((f) => `<div class="kv"><span>${esc(f.label)}</span><span>${linkify(r[f.key])}</span></div>`).join("");
    return `<div class="card" data-id="${r.id}">
      <div class="card-top"><div><div class="card-title">${esc(c.title(r) || "—")}</div>
        ${c.sub(r) ? `<div class="card-sub">${esc(c.sub(r))}</div>` : ""}</div>
        ${pill ? `<span class="pill ${pill[1]}">${esc(pill[0])}</span>` : ""}</div>
      ${body ? `<div class="card-body">${body}</div>` : ""}</div>`;
  }

  // ------------------------------------------------------------ form sheet
  let formCtx = null;
  function fieldHtml(f, val, locked) {
    const id = "f_" + f.key, dis = locked ? "disabled" : "";
    const label = `<label for="${id}">${esc(f.label)}${f.required ? ' <span class="req">*</span>' : ""}${f.admin ? '<span class="lock">🔒 mentor</span>' : ""}</label>`;
    let input;
    if (f.type === "select") {
      input = `<select id="${id}" name="${f.key}" ${dis}><option value="">— tanlang —</option>${f.options.map((o) =>
        `<option ${o === val ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
    } else if (f.type === "textarea") {
      input = `<textarea id="${id}" name="${f.key}" ${dis}>${esc(val)}</textarea>`;
    } else {
      const t = { number: "number", date: "date", url: "url" }[f.type] || "text";
      input = `<input id="${id}" name="${f.key}" type="${t}" ${t === "number" ? 'step="any" inputmode="decimal"' : ""} value="${esc(val)}" ${dis}>`;
    }
    return `<div class="field">${label}${input}</div>`;
  }

  function openForm(key, rec) {
    const sch = state.schema[key], admin = state.me.is_admin;
    formCtx = { key, rec };
    $("#sheetTitle").textContent = (rec ? "Tahrirlash · " : "Yangi · ") + sch.title;
    $("#sheetBody").innerHTML = sch.fields.map((f) => fieldHtml(f, rec ? rec[f.key] ?? "" : "", f.admin && !admin)).join("");
    $("#sheetDelete").hidden = !rec || (sch.admin_create && !admin);
    $("#sheet").hidden = false;
    document.body.style.overflow = "hidden";
  }
  function closeForm() { $("#sheet").hidden = true; document.body.style.overflow = ""; formCtx = null; }
  $("#sheet").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeForm(); });

  $("#sheetForm").addEventListener("submit", async (e) => {
    e.preventDefault(); if (!formCtx) return;
    if (formCtx.key === "__user") return submitUser(e.target);
    const { key, rec } = formCtx;
    const data = {};
    new FormData(e.target).forEach((v, k) => (data[k] = v));
    const btn = $("#sheetSave"); btn.disabled = true;
    try {
      if (rec) await api("PUT", `records/${key}/${rec.id}`, data);
      else await api("POST", `records/${key}`, data);
      haptic("medium"); toast("Saqlandi ✓"); closeForm(); render();
    } catch (err) { toast(err.message); }
    finally { btn.disabled = false; }
  });

  $("#sheetDelete").addEventListener("click", async () => {
    if (!formCtx || !formCtx.rec) return;
    const ok = await confirmBox("Yozuvni o'chirasizmi?");
    if (!ok) return;
    try { await api("DELETE", `records/${formCtx.key}/${formCtx.rec.id}`); toast("O'chirildi"); closeForm(); render(); }
    catch (err) { toast(err.message); }
  });

  function confirmBox(msg) {
    return new Promise((res) => {
      if (tg && tg.showConfirm && tg.initData) tg.showConfirm(msg, res); else res(window.confirm(msg));
    });
  }

  // ------------------------------------------------------------ admin: users
  async function renderUsers() {
    view.innerHTML = `<div class="hint">Yuklanmoqda…</div>`;
    let list;
    try { list = await api("GET", "users"); } catch (e) { view.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    if (state.tab !== "users") return;
    state.users = list; renderPicker();
    view.innerHTML = `
      <div class="section-head"><h1>👥 O'quvchilar</h1><button class="btn primary small" id="addUser">+ Qo'shish</button></div>
      <p class="hint">O'quvchi Telegram ID sini bilish uchun u botga /start yozsin — bot sizga uning ID sini yuboradi.</p>
      <div class="list">${list.length ? list.map((u) => `
        <div class="card" data-uid="${u.tg_id}">
          <div class="user-row"><div class="avatar">${esc((u.name || "?").trim()[0] || "?").toUpperCase()}</div>
            <div class="user-meta"><div class="card-title">${esc(u.name)}</div><div class="card-sub">ID: ${u.tg_id}</div>
              <div class="mini-stats">
                <span>🎓 <b>${u.stats.universities}/10</b></span>
                <span>🏅 <b>${num(u.stats.hours_total)}</b> soat</span>
                <span>🗓 <b>${u.stats.tasks_done}/${u.stats.tasks_total}</b> (${u.stats.tasks_percent}%)</span>
                <span>⭐ <b>${num(u.stats.avg_score)}</b></span>
                <span>📝 <b>${u.stats.tests}</b> test</span>
              </div></div>
            <button class="icon-btn" data-del="${u.tg_id}" aria-label="O'chirish">🗑</button></div>
        </div>`).join("") : `<div class="empty">Hali o'quvchi yo'q.</div>`}</div>`;

    $("#addUser").onclick = openUserForm;
    view.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async (e) => {
      e.stopPropagation();
      const u = list.find((x) => String(x.tg_id) === b.dataset.del);
      if (!(await confirmBox(`${u.name} va uning barcha ma'lumotlari o'chirilsinmi?`))) return;
      try { await api("DELETE", "users/" + u.tg_id); toast("O'chirildi"); renderUsers(); } catch (err) { toast(err.message); }
    }));
    view.querySelectorAll("[data-uid]").forEach((c) => c.addEventListener("click", () => {
      state.userId = c.dataset.uid; state.tab = "universities"; renderPicker(); renderTabs(); render();
    }));
  }

  function openUserForm() {
    formCtx = { key: "__user" };
    $("#sheetTitle").textContent = "Yangi o'quvchi";
    $("#sheetBody").innerHTML = `
      <div class="field"><label for="u_id">Telegram ID <span class="req">*</span></label><input id="u_id" name="tg_id" inputmode="numeric" placeholder="123456789"></div>
      <div class="field"><label for="u_name">Ism familiya <span class="req">*</span></label><input id="u_name" name="name"></div>`;
    $("#sheetDelete").hidden = true; $("#sheet").hidden = false;
  }
  async function submitUser(form) {
    const fd = new FormData(form);
    try {
      await api("POST", "users", { tg_id: fd.get("tg_id"), name: fd.get("name") });
      toast("Qo'shildi ✓"); closeForm(); renderUsers();
    } catch (err) { toast(err.message); }
  }

  // ------------------------------------------------------------ boot
  async function boot() {
    try {
      const me = await api("GET", "me");
      state.me = me; state.schema = me.schema; state.users = me.users || [];
      $("#whoami").textContent = me.is_admin ? `Mentor · ${me.name}` : me.name;
      renderPicker(); renderTabs(); render();
    } catch (e) {
      $("#tabs").hidden = true;
      $("#whoami").textContent = "";
      const uid = tg && tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : null;
      view.innerHTML = `<div class="blocker"><h1>${e.status === 401 ? "Ilovani Telegram orqali oching" : "Kirish cheklangan"}</h1>
        <p class="hint">${esc(e.message)}</p>${uid ? `<p>Sizning ID: <code>${uid}</code></p><p class="hint">Bu raqamni mentoringizga yuboring.</p>` : ""}</div>`;
    }
  }
  boot();
})();
