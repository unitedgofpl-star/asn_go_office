/**
 * Bot Telegram "Kantor ASN GO Digitals" — Cloudflare Worker (gratis), model sama dengan Kantor United Go.
 *
 * Telegram → Worker ini (langsung membalas dalam 1 detik) → GitHub Actions (tim AI bekerja ±1–2 menit)
 *
 * Variabel (Worker → Settings → Variables and Secrets):
 *   TELEGRAM_BOT_TOKEN  (secret)  token @asn_digitalbot dari @BotFather
 *   TELEGRAM_SECRET     (secret)  kata sandi bebas, mis. asngo-rahasia-2026
 *   GH_TOKEN            (secret)  token GitHub: repo asn_go_office, izin Actions + Contents = Read and write
 *   GH_REPO             (text)    unitedgofpl-star/asn_go_office
 *   OWNER_CHAT_ID       (text)    759159280
 *   KANTOR_URL          (text)    https://unitedgofpl-star.github.io/asn_go_office
 * Lalu buka https://<nama-worker>.<akun>.workers.dev/setup sekali.
 *
 * PENJAGA JADWAL (disarankan): Worker → Settings → Triggers → Cron Triggers → Add → isi teks CRON_JADWAL di bawah.
 * Tiap 10 menit Worker mengecek jadwal posting dan menyalakan tim tepat waktu (cron GitHub sering telat/terlewat).
 */

const HELP = `🏢 <b>Kantor Virtual ASN GO Digitals</b>
Perintah untuk Bos:

/buat [topik] — buat carousel baru (topik opsional)
/reels [topik] — buat video Reels baru
/berita [topik] — carousel berita terkini
/buat_promo [id_produk] — carousel soft-selling produk
/ide — 10 ide konten
/antrian — daftar draft
/lihat [id] — pratinjau ulang draft
/setuju [id] — setujui & langsung terbit
/terbit [id] — terbitkan sekarang
/revisi [id] [catatan] — tulis ulang dengan catatan
/tolak [id] — buang draft
/promo [id_produk] — copy promosi WA/Story
/tiktok [id] — paket TikTok (video + caption)
/produk — daftar produk lynk.id
/harga — lihat & ubah harga paket (CTA ikut berubah)
/sudah [id] — tandai paket manual sudah diposting
/flow [promo|edukasi] [topik] — brief video Google Flow
/jadi [id] — rakit video Flow dari klip yang dikirim
/laporan — laporan performa
/jadwal — jadwal posting hari ini (/jadwal besok)
/status — apa yang sedang dikerjakan karyawan
/otomatis on|off — terbit tanpa persetujuan
/kantor — buka kantor 3D

Atau ketik topik bebas, mis. "cara cepat bikin SK Kepala Desa".`;

const SLOW = {
  "/flow": "🎬 Kaka Selfina menulis brief video Google Flow... (±1 menit)",
  "/jadi": "🛠 Kaka Elisa merakit video Flow... (±2–3 menit)",
  "/buat": "👷 Siap Bos! Kaka Maria, Kaka Selfina, Kaka Agus & Kaka Elisa mulai bekerja. Pratinjau carousel dikirim ±2–3 menit lagi.",
  "/reels": "🎬 Tim membuat video Reels: naskah, desain, animasi. Pratinjau ±3–4 menit lagi.",
  "/berita": "📰 Kaka Maria memantau berita terkini dari media tepercaya, Kaka Selfina merangkum. Pratinjau ±3 menit lagi.",
  "/buat_promo": "💰 Kaka Yance & tim menyiapkan konten soft-selling. Pratinjau ±2–3 menit lagi.",
  "/revisi": "✍️ Kaka Selfina merevisi draft. Hasil ±2–3 menit lagi.",
  "/terbit": "🚀 Kaka Natalia menyiapkan penerbitan ke IG & FB (±1–2 menit).",
  "/laporan": "📊 Kaka Ruth menarik data Instagram (±1–2 menit).",
  "/ide": "💡 Kaka Selfina sedang brainstorm (±1 menit).",
  "/promo": "💰 Kaka Yance menulis copy promo (±1 menit).",
  "/tiktok": "📱 Kaka Natalia membuat video TikTok (±1–2 menit).",
};

// Jam slot posting (WIT) — samakan dengan "slots" di config.yaml. Dipakai bila state.json belum punya jadwal.
const CRON_JADWAL = "*/10 * * * *"; // ← salin teks ini ke Cron Triggers Cloudflare (tiap 10 menit)
const SLOT_JAM = ["06:30", "08:00", "09:00", "12:00", "15:30", "17:00", "18:30", "20:00"];

export default {
  // Penjaga jadwal: dipanggil Cron Trigger Cloudflare tiap 10 menit
  async scheduled(event, env, ctx) {
    ctx.waitUntil(jagaJadwal(env));
  },
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "GET" && url.pathname === "/setup") return setup(url, env);
    if (req.method === "GET") return new Response("Bot Kantor ASN GO aktif ✅");
    if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_SECRET) return new Response("forbidden", { status: 403 });

    const update = await req.json();
    const msg = update.message || update.callback_query?.message || {};
    const chat = String(msg.chat?.id || "");
    if (!chat) return ok();

    if (!env.OWNER_CHAT_ID) {
      await send(env, chat, `ID chat Anda: <code>${chat}</code>\nIsi angka ini ke variabel OWNER_CHAT_ID di Cloudflare.`);
      return ok();
    }
    if (chat !== String(env.OWNER_CHAT_ID)) {
      await send(env, chat, "⛔ Maaf, kantor ini hanya menerima perintah dari pemilik.");
      return ok();
    }

    try {
      // Tombol di bawah pratinjau (Setujui / Terbit / Tulis ulang / Tolak)
      if (update.callback_query) {
        const [act] = (update.callback_query.data || "").split(":");
        const label = { ok: "✅ Disetujui, sedang terbit", now: "🚀 Diterbitkan sebentar lagi", redo: "🔁 Ditulis ulang", no: "🗑 Dibuang" }[act] || "Diproses";
        await tg(env, "answerCallbackQuery", { callback_query_id: update.callback_query.id, text: label });
        await dispatch(env, update);
        if (act === "now" || act === "ok" || act === "redo") await send(env, chat, act === "redo" ? SLOW["/revisi"] : SLOW["/terbit"]);
        return ok();
      }

      // Video dari Google Flow (dibalas ke pesan brief) → dirakit tim di GitHub
      if (msg.video || msg.document) {
        await dispatch(env, update);
        await send(env, chat, "🎬 Video diterima! Kaka Elisa sedang memprosesnya (±2–3 menit).");
        return ok();
      }
      const text = (msg.text || "").trim();
      if (!text) return ok();
      const cmd = text.split(/\s+/)[0].split("@")[0].toLowerCase();

      // Dijawab langsung oleh Worker (instan)
      if (cmd === "/start" || cmd === "/bantuan" || cmd === "/help" || /^menu$/i.test(text)) {
        await send(env, chat, HELP);
        return ok();
      }
      if (cmd === "/kantor") {
        await send(env, chat, `🏢 Kantor 3D live: ${env.KANTOR_URL || "(isi KANTOR_URL)"}`);
        return ok();
      }
      if (cmd === "/status") {
        await send(env, chat, await status(env));
        return ok();
      }
      if (cmd === "/jadwal") {
        await send(env, chat, await jadwal(env, /besok/i.test(text)));
        return ok();
      }

      // Dikerjakan tim di GitHub Actions
      await dispatch(env, update);
      const slow = SLOW[cmd] || (text.startsWith("/") ? "⏳ Bapa Yohanis menerima perintah, sedang diproses (±1 menit)." : SLOW["/buat"]);
      await send(env, chat, slow);
    } catch (e) {
      await send(env, chat, `⚠️ ${String(e.message || e).slice(0, 300)}`);
    }
    return ok();
  },
};

async function dispatch(env, update) {
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/kantor.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "asn-go-bot" },
    body: JSON.stringify({ ref: "main", inputs: { mode: "event", update: JSON.stringify(update).slice(0, 60000) } }),
  });
  if (r.status !== 204) throw new Error(`GitHub menolak (${r.status}): ${(await r.text()).slice(0, 200)}`);
}

async function dispatchSlot(env, idx) {
  const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/kantor.yml/dispatches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json", "User-Agent": "asn-go-bot" },
    body: JSON.stringify({ ref: "main", inputs: { mode: "slot", slot: String(idx) } }),
  });
  if (r.status !== 204) throw new Error(`GitHub menolak (${r.status})`);
}

async function bacaState(env) {
  const r = await fetch(`https://raw.githubusercontent.com/${env.GH_REPO}/main/data/state.json?t=${Date.now()}`);
  return r.json();
}

function waktuWIT(offsetHari = 0) {
  const d = new Date(Date.now() + 9 * 3600e3 + offsetHari * 864e5);
  return { tgl: d.toISOString().slice(0, 10), menit: d.getUTCHours() * 60 + d.getUTCMinutes(), hari: d.getUTCDay(), tanggal: d.getUTCDate(), bulan: d.getUTCMonth() };
}
const keMenit = j => { const [h, m] = j.split(":").map(Number); return h * 60 + m; };

async function jagaJadwal(env) {
  try {
    const d = await bacaState(env).catch(() => ({}));
    const w = waktuWIT();
    const jg = d.jadwal || {};
    const jam = (jg.tanggal === w.tgl ? jg.hari_ini : jg.besok_tanggal === w.tgl ? jg.besok : null)?.map(r => r.jam) || SLOT_JAM;
    const log = (d.slot_log || {})[w.tgl] || {};
    for (let i = 0; i < jam.length; i++) {
      const selisih = w.menit - keMenit(jam[i]);
      if (selisih >= 0 && selisih < 10 && !log[String(i)]) {
        await dispatchSlot(env, i);
        console.log(`Slot ${i} (${jam[i]} WIT) dinyalakan`);
      }
    }
  } catch (e) {
    console.log("Penjaga jadwal gagal:", e);
  }
}

const IKON = { terbit: "✅", menunggu: "⏸", proses: "🔄", gagal: "⚠️", manual: "📦", terlewat: "❌", akan: "🕒", berikutnya: "⏭" };
const LABEL = { terbit: "Terbit", menunggu: "Menunggu persetujuan", proses: "Sedang diproses", gagal: "Gagal", manual: "Paket manual", terlewat: "Tidak jalan", berikutnya: "Berikutnya" };
const HARI = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];
const BLN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const esc = s => String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function jadwal(env, besok) {
  try {
    const d = await bacaState(env);
    const jg = d.jadwal || {};
    const w = waktuWIT(besok ? 1 : 0);
    let rows = jg.tanggal === w.tgl ? jg.hari_ini : jg.besok_tanggal === w.tgl ? jg.besok : null;
    if (!rows) rows = SLOT_JAM.map((j, i) => ({ jam: j, jenis: "Konten terjadwal", pilar: "", status: "akan" }));
    rows = rows.map(r => ({ ...r }));
    if (!besok) {  // perbarui status berdasar jam sekarang (state bisa beberapa jam lalu)
      rows.forEach(r => {
        if (r.status === "akan" || r.status === "berikutnya") {
          const lewat = w.menit - keMenit(r.jam);
          r.status = lewat < 0 ? "akan" : lewat < 45 ? "proses" : "terlewat";
        }
      });
      const n = rows.find(r => r.status === "akan");
      if (n) n.status = "berikutnya";
    } else rows.forEach(r => (r.status = "akan"));
    const out = [`📅 <b>Jadwal posting ${besok ? "besok" : "hari ini"}</b>\n${HARI[w.hari]}, ${w.tanggal} ${BLN[w.bulan]} • jam WIT\n`];
    rows.forEach(r => {
      let l = `${IKON[r.status] || "🕒"} <b>${r.jam}</b> ${esc(r.jenis)}${r.pilar ? " • " + esc(r.pilar) : ""}`;
      if (r.judul) l += `\n      “${esc(r.judul.slice(0, 70))}”`;
      if (r.status !== "akan") l += `\n      <i>${LABEL[r.status] || r.status}${r.terbit ? " " + r.terbit : ""}</i>${r.id ? " #" + r.id : ""}`;
      out.push(l);
    });
    if (!besok) {
      const man = jg.tanggal === w.tgl ? jg.manual || [] : [];
      if (man.length) {
        out.push("\n✍️ <b>Konten manual hari ini</b>");
        man.forEach(m => out.push(`${IKON[m.status] || "🔄"} ${m.jam} ${esc(m.jenis)} #${m.id} — ${esc((m.judul || "").slice(0, 60))}`));
      }
      const done = rows.filter(r => r.status === "terbit").length + man.filter(m => m.status === "terbit").length;
      out.push(`\n📊 Terbit hari ini: <b>${done}</b> • Terjadwal: ${rows.length} slot`);
      const n = rows.find(r => r.status === "berikutnya");
      if (n) { const s = keMenit(n.jam) - w.menit; out.push(`⏭ Berikutnya ${n.jam} WIT (${Math.floor(s / 60)} jam ${s % 60} menit lagi): ${esc(n.jenis)}`); }
    }
    out.push(`<i>Data kantor: ${String(jg.dibuat || d.updated || "-").slice(11, 16)} WIT</i> • Lihat besok: /jadwal besok`);
    return out.join("\n");
  } catch (e) {
    return "Belum bisa membaca jadwal kantor.";
  }
}

async function status(env) {
  try {
    const r = await fetch(`https://raw.githubusercontent.com/${env.GH_REPO}/main/data/state.json?t=${Date.now()}`);
    const d = await r.json();
    const ag = Object.values(d.agents || {}).map(a => `${a.status === "idle" ? "🟢" : "🟠"} <b>${a.name}</b>\n   ${a.last} (${a.at || "-"})`).join("\n");
    const drafts = Object.values(d.drafts || {});
    const wait = drafts.filter(x => x.status === "draft").length, ok = drafts.filter(x => x.status === "approved").length;
    return `🏢 <b>Status kantor</b> (update ${String(d.updated || "-").slice(0, 16).replace("T", " ")})\n` +
      `Terbit: ${(d.stats || {}).published || 0} · Menunggu persetujuan: ${wait} · Siap terbit: ${ok}\n\n${ag}`;
  } catch (e) {
    return "Belum bisa membaca status kantor.";
  }
}

async function setup(url, env) {
  const r = await tg(env, "setWebhook", {
    url: `${url.origin}/tg`, secret_token: env.TELEGRAM_SECRET, allowed_updates: ["message", "callback_query"], drop_pending_updates: false,
  });
  return new Response(r.ok ? "Webhook terpasang ✅ Sekarang chat bot Anda di Telegram dan ketik /bantuan." : `Gagal: ${JSON.stringify(r)}`,
    { headers: { "content-type": "text/plain; charset=utf-8" } });
}

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`,
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}
async function send(env, chat, text) {
  const r = await tg(env, "sendMessage", { chat_id: chat, text, parse_mode: "HTML", disable_web_page_preview: true });
  if (!r.ok) await tg(env, "sendMessage", { chat_id: chat, text: text.replace(/<[^>]+>/g, "") });
}
const ok = () => new Response("ok");
