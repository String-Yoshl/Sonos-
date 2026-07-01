"use strict";

const $ = (sel) => document.querySelector(sel);

let selectedSource = null; // {type, title, uri}
let searchTimer = null;

// Service Worker はセキュアコンテキスト(localhost / HTTPS)でのみ登録できる。
// LAN の HTTP 越しでも「ホーム画面に追加」でアプリ起動は可能なので、登録は任意。
if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  });
}

// ---- 認証トークン -----------------------------------------------------
// サーバ起動時に表示される URL の ?token=... を取り込んで保存し、URL からは消す。
const TOKEN_KEY = "bgm_token";
{
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get("token");
  if (fromUrl) {
    localStorage.setItem(TOKEN_KEY, fromUrl.trim());
    history.replaceState(null, "", location.pathname);
  }
}
const getToken = () => localStorage.getItem(TOKEN_KEY) || "";

async function api(path, opts) {
  const doFetch = () =>
    fetch(path, {
      headers: { "Content-Type": "application/json", "X-Auth-Token": getToken() },
      ...opts,
    });
  let res = await doFetch();
  if (res.status === 401) {
    const entered = prompt(
      "アクセストークンを入力してください（サーバ起動時のコンソールに表示されています）"
    );
    if (entered) {
      localStorage.setItem(TOKEN_KEY, entered.trim());
      res = await doFetch();
    }
  }
  let body = null;
  try { body = await res.json(); } catch (_) {}
  if (!res.ok) {
    throw new Error((body && body.error) || `エラー (${res.status})`);
  }
  return body;
}

function toast(msg, isErr) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("err", !!isErr);
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 3200);
}

// ---- 部屋 -----------------------------------------------------------
async function loadRooms() {
  const sel = $("#room");
  let rooms = [];
  try { rooms = await api("/api/rooms"); } catch (e) { toast(e.message, true); }
  const settings = await api("/api/settings");
  sel.innerHTML = "";
  if (!rooms.length) {
    const o = document.createElement("option");
    o.textContent = "（部屋が見つかりません）";
    o.value = "";
    sel.appendChild(o);
  }
  // 保存済みの部屋が検出に出てこない場合も選べるようにしておく。
  const names = rooms.map((r) => r.name);
  if (settings.room && !names.includes(settings.room)) names.unshift(settings.room);
  names.forEach((name) => {
    const o = document.createElement("option");
    o.value = name; o.textContent = name;
    if (name === settings.room) o.selected = true;
    sel.appendChild(o);
  });
}

$("#room").addEventListener("change", async (e) => {
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ room: e.target.value }) });
    toast("部屋を保存しました。");
  } catch (err) { toast(err.message, true); }
});
$("#refresh-rooms").addEventListener("click", loadRooms);

// ---- スケジュール一覧 ----------------------------------------------
function sleepLabel(min) {
  if (!min) return "スリープOFF";
  return `スリープ${min}分`;
}

function fmtNext(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const days = ["日", "月", "火", "水", "木", "金", "土"];
  return `次回 ${d.getMonth() + 1}/${d.getDate()}(${days[d.getDay()]}) ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

async function loadSchedules() {
  const items = await api("/api/schedules");
  const box = $("#schedules");
  box.innerHTML = "";
  $("#empty").classList.toggle("hidden", items.length > 0);
  for (const s of items) {
    const card = document.createElement("div");
    card.className = "card" + (s.enabled ? "" : " disabled");
    card.innerHTML = `
      <div class="time">${s.time}</div>
      <div class="meta">
        <div class="name">${escapeHtml(s.name)}</div>
        <div class="sub">${escapeHtml(s.source.title || s.source.uri || "")}
          <span class="tag">${sleepLabel(s.sleep_timer_minutes)}</span>
          <span class="tag">音量${s.volume ?? "—"}</span>
        </div>
        <div class="next">${s.enabled ? fmtNext(s.next_run) : "（無効）"}</div>
      </div>
      <div class="actions">
        <button class="icon" data-act="play" title="今すぐ再生">▶</button>
        <button class="icon" data-act="edit" title="編集">✎</button>
        <button class="danger" data-act="del" title="削除">🗑</button>
        <label class="switch"><input type="checkbox" data-act="toggle" ${s.enabled ? "checked" : ""}/><span class="slider"></span></label>
      </div>`;
    card.querySelector('[data-act=play]').onclick = () => playNow(s.id);
    card.querySelector('[data-act=edit]').onclick = () => openModal(s);
    card.querySelector('[data-act=del]').onclick = () => delSchedule(s);
    card.querySelector('[data-act=toggle]').onclick = (e) => toggleSchedule(s, e.target.checked);
    box.appendChild(card);
  }
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function playNow(id) {
  try { await api(`/api/schedules/${id}/play-now`, { method: "POST" }); toast("再生しました。"); }
  catch (e) { toast(e.message, true); }
}

async function delSchedule(s) {
  if (!confirm(`「${s.name}」を削除しますか？`)) return;
  try { await api(`/api/schedules/${s.id}`, { method: "DELETE" }); await loadSchedules(); toast("削除しました。"); }
  catch (e) { toast(e.message, true); }
}

async function toggleSchedule(s, enabled) {
  const payload = { ...s, enabled };
  delete payload.next_run;
  try { await api(`/api/schedules/${s.id}`, { method: "PUT", body: JSON.stringify(payload) }); await loadSchedules(); }
  catch (e) { toast(e.message, true); await loadSchedules(); }
}

// ---- モーダル -------------------------------------------------------
function openModal(s) {
  $("#modal-title").textContent = s ? "セットを編集" : "新しいセット";
  $("#f-id").value = s ? s.id : "";
  $("#f-name").value = s ? s.name : "";
  $("#f-time").value = s ? s.time : "21:00";
  $("#f-volume").value = s && s.volume != null ? s.volume : 18;
  $("#vol-label").textContent = $("#f-volume").value;
  $("#f-fade").value = s ? s.fade_in_seconds : 30;
  $("#f-enabled").checked = s ? s.enabled : true;

  // スリープタイマー
  const sleepSel = $("#f-sleep");
  const min = s ? s.sleep_timer_minutes : 60;
  const preset = ["", "15", "30", "45", "60", "90", "120"];
  if (min == null) sleepSel.value = "";
  else if (preset.includes(String(min))) sleepSel.value = String(min);
  else { sleepSel.value = "custom"; $("#f-sleep-custom").value = min; }
  updateSleepCustom();

  selectedSource = s ? { ...s.source } : null;
  renderSelectedSource();
  $("#source-search").value = "";
  $("#form-error").classList.add("hidden");
  $("#modal").classList.remove("hidden");
  loadSources("");
}

function closeModal() { $("#modal").classList.add("hidden"); }

function renderSelectedSource() {
  $("#selected-source").textContent = selectedSource ? selectedSource.title || selectedSource.uri : "未選択";
}

function updateSleepCustom() {
  $("#sleep-custom-wrap").classList.toggle("hidden", $("#f-sleep").value !== "custom");
}

$("#f-sleep").addEventListener("change", updateSleepCustom);
$("#f-volume").addEventListener("input", (e) => { $("#vol-label").textContent = e.target.value; });
$("#add-schedule").addEventListener("click", () => openModal(null));
$("#cancel").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

// ---- 音源の閲覧・検索 ----------------------------------------------
async function loadSources(query) {
  const list = $("#source-list");
  const hint = $("#source-hint");
  list.innerHTML = "";
  hint.textContent = "読み込み中…";
  try {
    const sources = await api(`/api/sources?q=${encodeURIComponent(query)}`);
    hint.textContent = sources.length ? "" : "該当する音源がありません。";
    for (const src of sources) {
      const row = document.createElement("div");
      row.className = "source-item";
      if (selectedSource && selectedSource.type === src.type && selectedSource.title === src.title) {
        row.classList.add("selected");
      }
      row.innerHTML = `<span class="s-title">${escapeHtml(src.title)}</span><span class="tag">${escapeHtml(src.subtitle)}</span>`;
      row.onclick = () => {
        selectedSource = { type: src.type, title: src.title, uri: src.uri };
        renderSelectedSource();
        list.querySelectorAll(".source-item").forEach((el) => el.classList.remove("selected"));
        row.classList.add("selected");
      };
      list.appendChild(row);
    }
  } catch (e) {
    hint.textContent = e.message + "（部屋の設定を確認してください）";
  }
}

$("#source-search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadSources(e.target.value), 250);
});

// ---- 保存 -----------------------------------------------------------
$("#schedule-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#form-error");
  err.classList.add("hidden");

  if (!selectedSource) { err.textContent = "BGM（プレイリスト/お気に入り）を選んでください。"; err.classList.remove("hidden"); return; }

  let sleep = null;
  const sv = $("#f-sleep").value;
  if (sv === "custom") sleep = parseInt($("#f-sleep-custom").value, 10) || null;
  else if (sv !== "") sleep = parseInt(sv, 10);

  const payload = {
    name: $("#f-name").value.trim(),
    time: $("#f-time").value,
    enabled: $("#f-enabled").checked,
    source: selectedSource,
    volume: parseInt($("#f-volume").value, 10),
    fade_in_seconds: parseInt($("#f-fade").value, 10) || 0,
    sleep_timer_minutes: sleep,
  };

  const id = $("#f-id").value;
  try {
    if (id) await api(`/api/schedules/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api("/api/schedules", { method: "POST", body: JSON.stringify(payload) });
    closeModal();
    await loadSchedules();
    toast("保存しました。");
  } catch (e2) {
    err.textContent = e2.message; err.classList.remove("hidden");
  }
});

// ---- 初期化 ---------------------------------------------------------
(async function init() {
  await loadRooms();
  await loadSchedules();
})();
