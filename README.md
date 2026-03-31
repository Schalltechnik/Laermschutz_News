# 🔊 Lärmschutz News Monitor

Täglicher News-Crawler für Lärmschutz – Österreich, Europa, Wissenschaft.  
Automatisch aktualisiert via **GitHub Actions** · KI-Zusammenfassung via **Google Gemini** · Gehostet auf **GitHub Pages**.

---

## ⚡ Setup in 5 Schritten

### 1. Repository erstellen

1. Gehe zu [github.com](https://github.com) und melde dich an
2. Klicke oben rechts auf **„+"** → **„New repository"**
3. Name: `laermschutz-news`
4. Wähle **„Public"** (für GitHub Pages kostenlos)
5. Klicke **„Create repository"**

---

### 2. Dateien hochladen

Lade alle Dateien aus diesem Paket hoch:

1. Klicke im neuen Repository auf **„uploading an existing file"**
2. Ziehe alle Dateien und Ordner hinein:
   - `fetch_news.py`
   - `.github/workflows/daily-update.yml`
   - `docs/index.html`
   - `docs/data.json`
3. Klicke **„Commit changes"**

> **Wichtig:** Der Ordner `.github` ist versteckt – stelle sicher dass er mitgeladen wird.

---

### 3. Gemini API Key holen (kostenlos)

1. Gehe zu [aistudio.google.com](https://aistudio.google.com)
2. Melde dich mit deinem Google-Konto an
3. Klicke oben links auf **„Get API key"** → **„Create API key"**
4. Kopiere den Key (z.B. `AIzaSy...`)

---

### 4. API Key in GitHub hinterlegen

1. Gehe in deinem Repository zu **Settings** → **Secrets and variables** → **Actions**
2. Klicke **„New repository secret"**
3. Name: `GEMINI_API_KEY`
4. Value: deinen kopierten Key einfügen
5. **„Add secret"** klicken

---

### 5. GitHub Pages aktivieren

1. Gehe zu **Settings** → **Pages**
2. Bei **„Source"**: wähle **„Deploy from a branch"**
3. Branch: **`main`**, Ordner: **`/docs`**
4. **„Save"** klicken
5. Nach 1–2 Minuten ist deine Website live unter:  
   `https://DEIN-USERNAME.github.io/laermschutz-news`

---

## 🚀 Ersten Lauf starten

Der Cron-Job läuft täglich um 07:00 Uhr (Wien). Um sofort zu testen:

1. Gehe zu **Actions** → **„Daily News Update"**
2. Klicke **„Run workflow"** → **„Run workflow"**
3. Warte ~1 Minute
4. Lade deine Website neu – die News erscheinen!

---

## 📅 Update-Zeitplan

Der Job läuft täglich um **07:00 Uhr Wiener Zeit** (06:00 UTC).  
Zum Ändern: bearbeite `.github/workflows/daily-update.yml`, Zeile `cron: "0 6 * * *"`.

---

## 🔧 Anpassungen

**Andere Suchbegriffe:** bearbeite `fetch_news.py` → `CATEGORIES` → `feeds`  
**Andere Uhrzeit:** bearbeite `.github/workflows/daily-update.yml` → `cron`  
**Mehr/weniger Artikel:** ändere `MAX_ITEMS_PER_CATEGORY` in `fetch_news.py`

---

## 💰 Kosten

| Dienst | Kosten |
|---|---|
| GitHub Actions | Kostenlos (2000 Min/Monat) |
| GitHub Pages | Kostenlos |
| Google Gemini API | Kostenlos (60 Anfragen/Tag) |
| **Gesamt** | **$0 / Monat** |
