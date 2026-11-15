// OPSIONAL — "Mode Instan": bot membalas dalam ±1 menit, bukan menunggu putaran 15 menit.
// Cloudflare Workers gratis 100.000 request/hari.
// Variabel (Settings → Variables): GH_TOKEN (fine-grained PAT, izin Contents: Read & write pada repo ini),
// GH_REPO (mis. "arifitra/asn-go-office"), TG_SECRET (string acak bebas).
// Lalu daftarkan webhook:
//   https://api.telegram.org/bot<TOKEN>/setWebhook?url=<URL_WORKER>&secret_token=<TG_SECRET>
// Catatan: setelah webhook aktif, mode polling otomatis tidak menerima pesan lagi (itu normal).
// Untuk kembali ke polling: https://api.telegram.org/bot<TOKEN>/deleteWebhook

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Kantor ASN GO aktif");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TG_SECRET)
      return new Response("forbidden", { status: 403 });

    const update = await request.json();
    await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "kantor-asn-go",
      },
      body: JSON.stringify({ event_type: "telegram", client_payload: { update } }),
    });
    return new Response("ok");
  },
};
