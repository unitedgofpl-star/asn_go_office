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
 */

const HELP = `🏢 <b>Kantor Virtual ASN GO Digitals</b>
Perintah untuk Bos:

/buat [topik] — buat carousel baru (topik opsional)
/buat_promo [id_produk] — carousel soft-selling produk
/ide — 10 ide konten
/antrian — daftar draft
/lihat [id] — pratinjau ulang draft
/setuju [id] — setujui (terbit sesuai jadwal 19.00 WIT)
/terbit [id] — terbitkan sekarang
/revisi [id] [catatan] — tulis ulang dengan catatan
/tolak [id] — buang draft
/promo [id_produk] — copy promosi WA/Story
/produk — daftar produk lynk.id
/laporan — laporan performa
/status — apa yang sedang dikerjakan karyawan
/otomatis on|off — terbit tanpa persetujuan
/kantor — buka kantor 3D

Atau ketik topik bebas, mis. "cara cepat bikin SK Kepala Desa".`;

const SLOW = {
  "/buat": "👷 Siap Bos! Mbak Riset, Bu Naskah, Pak Verifikator & Mas Desain mulai bekerja. Pratinjau carousel dikirim ±2–3 menit lagi.",
  "/buat_promo": "💰 Bang Cuan & tim menyiapkan konten soft-selling. Pratinjau ±2–3 menit lagi.",
  "/revisi": "✍️ Bu Naskah merevisi draft. Hasil ±2–3 menit lagi.",
  "/terbit": "🚀 Mbak Humas menyiapkan penerbitan ke IG & FB (±1–2 menit).",
  "/laporan": "📊 Kak Analis menarik data Instagram (±1–2 menit).",
  "/ide": "💡 Bu Naskah sedang brainstorm (±1 menit).",
  "/promo": "💰 Bang Cuan menulis copy promo (±1 menit).",
};

export default {
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
        const label = { ok: "✅ Disetujui", now: "🚀 Diterbitkan sebentar lagi", redo: "🔁 Ditulis ulang", no: "🗑 Dibuang" }[act] || "Diproses";
        await tg(env, "answerCallbackQuery", { callback_query_id: update.callback_query.id, text: label });
        await dispatch(env, update);
        if (act === "now" || act === "redo") await send(env, chat, act === "now" ? SLOW["/terbit"] : SLOW["/revisi"]);
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

      // Dikerjakan tim di GitHub Actions
      await dispatch(env, update);
      const slow = SLOW[cmd] || (text.startsWith("/") ? "⏳ Pak Kepala menerima perintah, sedang diproses (±1 menit)." : SLOW["/buat"]);
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
