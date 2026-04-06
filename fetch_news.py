<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Newsletter abonnieren – Lärmschutz News Monitor</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root { --green: #1a5c38; --green-dark: #133f28; --green-light: #e8f2ec; --border: #d4e4d4; }
    body { font-family: 'DM Sans', sans-serif; background: #f0f4f0; color: #1a1a1a; min-height: 100vh; padding: 40px 20px 80px; }
    .page { max-width: 520px; margin: 0 auto; }
    .back { display: inline-block; margin-bottom: 24px; font-size: 13px; color: var(--green); text-decoration: none; }
    .back:hover { text-decoration: underline; }
    .card { background: #fff; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; box-shadow: 0 2px 16px rgba(26,92,56,0.08); }
    .card-header { background: var(--green); color: #fff; padding: 24px 32px 20px; }
    .card-header .kw { font-size: 10px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 6px; }
    .card-header h1 { font-family: 'DM Serif Display', serif; font-weight: 400; font-size: 22px; line-height: 1.3; }
    .card-body { padding: 28px 32px 32px; }
    .field { margin-bottom: 18px; }
    label { display: block; font-size: 13px; font-weight: 600; color: #444; margin-bottom: 6px; }
    input[type="text"], input[type="email"] { width: 100%; padding: 10px 14px; font-family: 'DM Sans', sans-serif; font-size: 14px; border: 1px solid var(--border); border-radius: 6px; outline: none; transition: border-color 0.15s; }
    input:focus { border-color: var(--green); }
    .checkbox-group { margin-bottom: 20px; }
    .checkbox-group .group-label { font-size: 13px; font-weight: 600; color: #444; margin-bottom: 10px; }
    .checkbox-group label { font-weight: 400; display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; margin-bottom: 10px; }
    .checkbox-group input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--green); flex-shrink: 0; }
    .btn { width: 100%; padding: 12px; background: var(--green); color: #fff; border: none; border-radius: 6px; font-family: 'DM Sans', sans-serif; font-size: 15px; font-weight: 700; cursor: pointer; transition: background 0.15s; }
    .btn:hover { background: var(--green-dark); }
    .btn:disabled { background: #aaa; cursor: not-allowed; }
    .msg { margin-top: 16px; padding: 12px 16px; border-radius: 6px; font-size: 14px; display: none; line-height: 1.5; }
    .msg.success { background: var(--green-light); border: 1px solid #b8d4b8; color: var(--green); }
    .msg.error   { background: #fff3f3; border: 1px solid #fcc; color: #900; }
    .note { margin-top: 16px; font-size: 12px; color: #aaa; line-height: 1.5; }

    /* Current subscribers list */
    .sub-list { margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--border); }
    .sub-list h2 { font-size: 14px; font-weight: 700; color: #444; margin-bottom: 14px; }
    .sub-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
    .sub-item:last-child { border-bottom: none; }
    .sub-email { color: var(--text); font-weight: 500; }
    .sub-type { font-size: 11px; color: var(--muted); }
    .sub-remove { background: none; border: none; color: #c00; font-size: 13px; cursor: pointer; padding: 2px 6px; border-radius: 4px; }
    .sub-remove:hover { background: #fff0f0; }
    .empty-list { font-size: 13px; color: var(--muted); }
  </style>
</head>
<body>
<div class="page">
  <a class="back" href="index.html">← Zurück zur Übersicht</a>

  <div class="card">
    <div class="card-header">
      <div class="kw">✉️ Lärmschutz News Monitor</div>
      <h1>Newsletter abonnieren</h1>
    </div>
    <div class="card-body">
      <div class="field">
        <label for="name">Name (optional)</label>
        <input type="text" id="name" placeholder="Florian Lackner" />
      </div>
      <div class="field">
        <label for="email">E-Mail-Adresse *</label>
        <input type="email" id="email" placeholder="ihre@email.at" />
      </div>

      <div class="checkbox-group">
        <p class="group-label">Newsletter-Typ:</p>
        <label><input type="checkbox" id="weekly" checked /> 📄 Wöchentlicher Newsletter (jeden Donnerstag)</label>
        <label><input type="checkbox" id="monthly" checked /> 📅 Monatlicher Newsletter (Ende des Monats)</label>
      </div>

      <button class="btn" id="subscribe-btn" onclick="subscribe()">Jetzt anmelden</button>

      <div class="msg success" id="msg-success">
        ✅ Vielen Dank für Ihre Anmeldung! Sie erhalten in Kürze eine Bestätigung per E-Mail.
      </div>
      <div class="msg error" id="msg-error">❌ Fehler. Bitte versuchen Sie es erneut.</div>

      <p class="note">Ihre E-Mail-Adresse wird ausschließlich für diesen Newsletter verwendet und nicht weitergegeben.</p>

      <!-- Subscriber management (only visible if loaded from local file or admin) -->
      <div class="sub-list" id="sub-list" style="display:none">
        <h2>Aktuelle Abonnenten</h2>
        <div id="sub-items"></div>
      </div>
    </div>
  </div>
</div>

<script>
  // ── Configuration ──────────────────────────────────────────────────────────
  // Replace with your actual Brevo API key and your admin email
  // NOTE: This key is visible in the HTML source — use a restricted key
  // in Brevo that only allows sending transactional emails, not accessing contacts.
  const BREVO_API_KEY  = "YOUR_BREVO_API_KEY_HERE";  // Replace this!
  const ADMIN_EMAIL    = "YOUR_EMAIL_HERE";            // Your email to receive notifications
  const SENDER_EMAIL   = "YOUR_EMAIL_HERE";            // Must be verified in Brevo
  const SENDER_NAME    = "Lärmschutz News Monitor";

  // ── Subscribe ──────────────────────────────────────────────────────────────
  async function subscribe() {
    const email   = document.getElementById("email").value.trim();
    const name    = document.getElementById("name").value.trim();
    const weekly  = document.getElementById("weekly").checked;
    const monthly = document.getElementById("monthly").checked;

    if (!email || !email.includes("@")) {
      showMsg("error", "Bitte geben Sie eine gültige E-Mail-Adresse ein.");
      return;
    }
    if (!weekly && !monthly) {
      showMsg("error", "Bitte wählen Sie mindestens einen Newsletter-Typ.");
      return;
    }

    const btn = document.getElementById("subscribe-btn");
    btn.disabled = true;
    btn.textContent = "Wird verarbeitet…";

    const types = [weekly ? "Wöchentlich" : null, monthly ? "Monatlich" : null]
      .filter(Boolean).join(", ");

    // Send notification email to admin via Brevo
    const adminEmailBody = `
      <h2>Neue Newsletter-Anmeldung</h2>
      <p><strong>Name:</strong> ${name || "(nicht angegeben)"}</p>
      <p><strong>E-Mail:</strong> ${email}</p>
      <p><strong>Typ:</strong> ${types}</p>
      <hr>
      <p>Bitte füge diesen Abonnenten in <code>docs/subscribers.json</code> ein:</p>
      <pre style="background:#f5f5f5;padding:12px;border-radius:4px;">{
  "email": "${email}",
  "name": "${name}",
  "weekly": ${weekly},
  "monthly": ${monthly},
  "active": true
}</pre>
    `;

    // Send confirmation email to subscriber
    const confirmEmailBody = `
      <div style="font-family:sans-serif;max-width:500px;margin:0 auto;">
        <div style="background:#1a5c38;color:#fff;padding:24px;border-radius:8px 8px 0 0;">
          <h1 style="margin:0;font-size:20px;">🔊 Lärmschutz News Monitor</h1>
        </div>
        <div style="background:#fff;padding:24px;border:1px solid #d4e4d4;border-radius:0 0 8px 8px;">
          <p>Guten Tag${name ? " " + name : ""},</p>
          <p>vielen Dank für Ihre Anmeldung zum <strong>Lärmschutz Newsletter</strong>!</p>
          <p>Sie erhalten ab sofort: <strong>${types}</strong></p>
          <p style="margin-top:16px;font-size:12px;color:#999;">
            Falls Sie sich abmelden möchten, antworten Sie einfach auf diese E-Mail.
          </p>
        </div>
      </div>
    `;

    try {
      // 1. Notify admin
      await sendBrevoEmail(ADMIN_EMAIL, "Admin", `Neue Newsletter-Anmeldung: ${email}`, adminEmailBody);
      // 2. Confirm to subscriber
      await sendBrevoEmail(email, name || email, "Ihre Anmeldung beim Lärmschutz Newsletter", confirmEmailBody);
      showMsg("success");
    } catch(e) {
      showMsg("error", "Fehler beim Senden. Bitte versuchen Sie es später erneut.");
      console.error(e);
    }

    btn.disabled = false;
    btn.textContent = "Jetzt anmelden";
  }

  async function sendBrevoEmail(toEmail, toName, subject, htmlContent) {
    const resp = await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept":       "application/json",
        "api-key":      BREVO_API_KEY,
      },
      body: JSON.stringify({
        sender:      { name: SENDER_NAME, email: SENDER_EMAIL },
        to:          [{ email: toEmail, name: toName }],
        subject:     subject,
        htmlContent: htmlContent,
      }),
    });
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(`Brevo error ${resp.status}: ${err}`);
    }
    return resp.json();
  }

  function showMsg(type, text) {
    document.getElementById("msg-success").style.display = "none";
    document.getElementById("msg-error").style.display   = "none";
    const el = document.getElementById("msg-" + type);
    if (text) el.textContent = (type === "error" ? "❌ " : "✅ ") + text;
    el.style.display = "block";
  }
</script>
</body>
</html>
