import base64
import os
import re
from typing import Optional

import markdown as md
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── DB ───────────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.environ["DATABASE_URL"]
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

app = FastAPI(title="Feduk USA — Rapoarte Auto")

# ── Favicon (inline SVG → base64 data-URI) ───────────────────────────────────
_FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#DC2626"/>
  <path d="M14 40 L18 27 Q19 24 22 24 L42 24 Q45 24 46 27 L50 40 Z"
        fill="white" opacity="0.95"/>
  <circle cx="21" cy="41" r="4.5" fill="#DC2626" stroke="white" stroke-width="2"/>
  <circle cx="43" cy="41" r="4.5" fill="#DC2626" stroke="white" stroke-width="2"/>
  <rect x="13" y="38" width="38" height="4" rx="2" fill="white" opacity="0.2"/>
  <path d="M22 24 L25 17 L39 17 L42 24" fill="none" stroke="white"
        stroke-width="2" stroke-linejoin="round" opacity="0.75"/>
</svg>"""
_FAVICON_B64  = base64.b64encode(_FAVICON_SVG.encode()).decode()
FAVICON_URI   = f"data:image/svg+xml;base64,{_FAVICON_B64}"

# ── Translations ─────────────────────────────────────────────────────────────
T = {
    "ro": {
        "title": "Verifică Mașina",
        "subtitle": "Introdu VIN-ul și vezi raportul complet + analiza experților noștri",
        "placeholder": "ex: 5UXTS1C00M9H70629",
        "btn_search": "Verifică",
        "tab_analysis": "Analiza AMIGO",
        "tab_pdf": "Raport PDF",
        "btn_pdf": "Deschide Raportul PDF",
        "not_found_title": "VIN-ul nu a fost analizat",
        "not_found_body": "VIN-ul <strong>{vin}</strong> nu a trecut prin analiza Feduk USA.",
        "not_found_cta": "Trimite raportul Carfax pe Telegram pentru o analiză completă:",
        "contact_btn": "@fedukusa pe Telegram",
        "footer": "© 2026 Feduk USA · Auto din America, Canada, Korea",
        "vin_label": "VIN",
        "lang_note": "Analiză disponibilă în:",
        "error_vin": "VIN-ul trebuie să conțină exact 17 caractere alfanumerice.",
    },
    "ru": {
        "title": "Проверить Автомобиль",
        "subtitle": "Введите VIN и получите полный отчёт + анализ наших экспертов",
        "placeholder": "напр.: 5UXTS1C00M9H70629",
        "btn_search": "Проверить",
        "tab_analysis": "Анализ AMIGO",
        "tab_pdf": "Отчёт PDF",
        "btn_pdf": "Открыть PDF Отчёт",
        "not_found_title": "VIN не найден в базе",
        "not_found_body": "VIN <strong>{vin}</strong> ещё не анализировался командой Feduk USA.",
        "not_found_cta": "Отправь Carfax в Telegram для получения полного анализа:",
        "contact_btn": "@fedukusa в Telegram",
        "footer": "© 2026 Feduk USA · Авто из Америки, Канады, Кореи",
        "vin_label": "VIN",
        "lang_note": "Анализ доступен на:",
        "error_vin": "VIN должен содержать ровно 17 буквенно-цифровых символов.",
    },
    "en": {
        "title": "Check the Car",
        "subtitle": "Enter the VIN and view the full report + our expert analysis",
        "placeholder": "e.g. 5UXTS1C00M9H70629",
        "btn_search": "Check",
        "tab_analysis": "AMIGO Analysis",
        "tab_pdf": "PDF Report",
        "btn_pdf": "Open PDF Report",
        "not_found_title": "VIN not found",
        "not_found_body": "VIN <strong>{vin}</strong> has not been analysed by the Feduk USA team yet.",
        "not_found_cta": "Send your Carfax PDF on Telegram for a full analysis:",
        "contact_btn": "@fedukusa on Telegram",
        "footer": "© 2026 Feduk USA · Cars from America, Canada, Korea",
        "vin_label": "VIN",
        "lang_note": "Analysis available in:",
        "error_vin": "VIN must be exactly 17 alphanumeric characters.",
    },
}

LANG_NAMES = {"ro": "RO", "ru": "RU", "en": "EN"}
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)

# ── Design tokens (single source of truth) ───────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root{
  --bg:#080808;
  --surface:#111111;
  --surface-2:#1a1a1a;
  --border:#222222;
  --border-2:#2e2e2e;
  --text:#f2f2f2;
  --text-2:#888888;
  --text-3:#555555;
  --red:#DC2626;
  --red-dim:#b91c1c;
  --green:#22c55e;
  --radius:10px;
  --mono:'JetBrains Mono',monospace;
  --sans:'Space Grotesk',system-ui,sans-serif;
  --transition:180ms cubic-bezier(.4,0,.2,1);
}

html{scroll-behavior:smooth}
body{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}

/* ── HEADER ── */
header{position:sticky;top:0;z-index:50;background:rgba(8,8,8,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 24px;height:56px;display:flex;align-items:center;justify-content:space-between}
.logo{display:flex;align-items:center;gap:10px;text-decoration:none}
.logo-icon{width:32px;height:32px;background:var(--red);border-radius:7px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;color:#fff;letter-spacing:-.5px;flex-shrink:0}
.logo-name{font-size:.9rem;font-weight:600;color:var(--text);letter-spacing:.02em}
.logo-sub{font-size:.7rem;color:var(--text-3);letter-spacing:.04em;display:block;margin-top:-2px}
.lang-switcher{display:flex;gap:2px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:3px}
.lang-btn{font-family:var(--sans);font-size:.75rem;font-weight:600;color:var(--text-3);background:none;border:none;cursor:pointer;padding:4px 10px;border-radius:6px;transition:var(--transition);text-decoration:none;letter-spacing:.04em}
.lang-btn:hover{color:var(--text);background:var(--border-2)}
.lang-btn.active{color:var(--text);background:var(--surface);box-shadow:0 1px 3px rgba(0,0,0,.4)}

/* ── HERO ── */
.hero{padding:72px 24px 64px;text-align:center}
.hero-eyebrow{font-size:.72rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--red);margin-bottom:16px}
.hero h1{font-size:clamp(2rem,5vw,3.2rem);font-weight:700;letter-spacing:-.03em;line-height:1.1;color:var(--text);margin-bottom:14px}
.hero p{color:var(--text-2);font-size:1rem;margin-bottom:40px;max-width:480px;margin-left:auto;margin-right:auto;line-height:1.6}

/* ── SEARCH BOX ── */
.search-wrap{max-width:540px;margin:0 auto}
.search-box{display:flex;background:var(--surface);border:1px solid var(--border-2);border-radius:12px;overflow:hidden;transition:border-color var(--transition),box-shadow var(--transition)}
.search-box:focus-within{border-color:var(--red);box-shadow:0 0 0 3px rgba(220,38,38,.15)}
.search-box input{flex:1;background:none;border:none;outline:none;padding:15px 18px;font-family:var(--mono);font-size:.95rem;color:var(--text);letter-spacing:.05em}
.search-box input::placeholder{color:var(--text-3);font-family:var(--mono)}
.search-btn{background:var(--red);color:#fff;border:none;padding:0 28px;font-family:var(--sans);font-size:.9rem;font-weight:600;cursor:pointer;transition:background var(--transition);white-space:nowrap;letter-spacing:.02em}
.search-btn:hover{background:var(--red-dim)}
.error-msg{color:#f87171;font-size:.8rem;margin-top:10px;text-align:center}

/* ── MAIN ── */
main{flex:1;max-width:860px;width:100%;margin:0 auto;padding:32px 20px 64px}

/* ── CARD ── */
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden;margin-bottom:20px}
.card-top{background:var(--surface-2);padding:16px 22px;display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--border)}
.card-top-title{font-size:.8rem;font-weight:600;color:var(--text-2);letter-spacing:.06em;text-transform:uppercase}
.vin-tag{font-family:var(--mono);font-size:.8rem;font-weight:500;background:var(--red);color:#fff;padding:3px 10px;border-radius:6px;letter-spacing:.06em}

/* ── TABS ── */
.tabs{display:flex;padding:0 22px;border-bottom:1px solid var(--border);gap:0}
.tab{font-size:.82rem;font-weight:600;color:var(--text-3);padding:14px 16px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;transition:color var(--transition),border-color var(--transition);letter-spacing:.02em;user-select:none}
.tab:hover{color:var(--text-2)}
.tab.active{color:var(--text);border-bottom-color:var(--red)}
.tab-pane{display:none;padding:28px 24px}
.tab-pane.active{display:block}

/* ── LANG PILLS ── */
.lang-pills{display:flex;gap:6px;margin-bottom:22px}
.lang-pill{font-size:.75rem;font-weight:600;letter-spacing:.06em;padding:5px 14px;border-radius:20px;border:1px solid var(--border-2);color:var(--text-3);background:none;cursor:pointer;transition:var(--transition);font-family:var(--sans)}
.lang-pill.active{background:var(--red);border-color:var(--red);color:#fff}
.lang-body{display:none}
.lang-body.active{display:block}

/* ── ANALYSIS TYPOGRAPHY ── */
.analysis-content{line-height:1.75;color:var(--text)}
.analysis-content h2{font-size:1rem;font-weight:600;color:var(--red);margin:24px 0 10px;letter-spacing:.01em}
.analysis-content h2:first-child{margin-top:0}
.analysis-content h3{font-size:.95rem;font-weight:600;color:var(--text);margin:16px 0 8px}
.analysis-content p{margin-bottom:12px;color:var(--text-2);font-size:.925rem}
.analysis-content ul,
.analysis-content ol{padding-left:18px;margin-bottom:12px}
.analysis-content li{margin-bottom:6px;color:var(--text-2);font-size:.925rem}
.analysis-content strong{color:var(--text);font-weight:600}
.analysis-content table{width:100%;border-collapse:collapse;margin-bottom:16px;font-size:.875rem}
.analysis-content th{background:var(--surface-2);color:var(--text-2);font-weight:600;padding:8px 12px;text-align:left;border:1px solid var(--border)}
.analysis-content td{padding:8px 12px;border:1px solid var(--border);color:var(--text-2)}
.analysis-content code{font-family:var(--mono);font-size:.8rem;background:var(--surface-2);padding:2px 6px;border-radius:4px;color:var(--text)}
.analysis-content hr{border:none;border-top:1px solid var(--border);margin:20px 0}

/* ── PDF SECTION ── */
.pdf-area{padding:20px 24px 24px}
.pdf-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;gap:12px;flex-wrap:wrap}
.pdf-vin{font-family:var(--mono);font-size:.78rem;color:var(--text-3);letter-spacing:.08em}
.pdf-cta{display:inline-flex;align-items:center;gap:8px;background:var(--red);color:#fff;padding:9px 20px;border-radius:8px;font-size:.84rem;font-weight:600;text-decoration:none;transition:background var(--transition);letter-spacing:.02em;white-space:nowrap}
.pdf-cta:hover{background:var(--red-dim)}
.pdf-frame-wrap{border-radius:8px;overflow:hidden;border:1px solid var(--border);background:#1c1c1c}
.pdf-frame{width:100%;height:72vh;min-height:480px;border:none;display:block}
.pdf-fallback{display:none;text-align:center;padding:40px 20px;color:var(--text-3);font-size:.88rem}
.pdf-fallback a{color:var(--red);font-weight:600;text-decoration:none}

/* ── NOT FOUND ── */
.not-found{text-align:center;padding:60px 24px}
.nf-icon{width:56px;height:56px;background:var(--surface-2);border:1px solid var(--border);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:1.5rem;margin:0 auto 20px}
.not-found h2{font-size:1.2rem;font-weight:700;letter-spacing:-.02em;margin-bottom:10px}
.not-found p{color:var(--text-2);font-size:.9rem;line-height:1.6;max-width:400px;margin:0 auto 8px}
.tg-btn{display:inline-flex;align-items:center;gap:8px;background:#2AABEE;color:#fff;padding:12px 22px;border-radius:var(--radius);font-size:.88rem;font-weight:600;text-decoration:none;transition:opacity var(--transition),transform var(--transition);margin-top:22px}
.tg-btn:hover{opacity:.88;transform:translateY(-1px)}

/* ── BMW EQUIPMENT ── */
.equip-meta{font-size:.78rem;color:var(--text-3);margin-bottom:24px;display:flex;align-items:center;gap:16px}
.equip-meta a{color:var(--red);text-decoration:none;font-weight:500}
.equip-meta a:hover{text-decoration:underline}
.equip-sep{color:var(--border-2)}

/* ── RETRY BUTTON ── */
.retry-btn{display:inline-flex;align-items:center;gap:8px;background:var(--surface-2);border:1px solid var(--border-2);color:var(--text-2);padding:11px 22px;border-radius:var(--radius);font-size:.88rem;font-weight:600;text-decoration:none;transition:var(--transition);margin-top:20px;font-family:var(--sans)}
.retry-btn:hover{color:var(--text);border-color:var(--text-3)}

/* ── FOOTER ── */
footer{border-top:1px solid var(--border);padding:18px 24px;text-align:center;font-size:.75rem;color:var(--text-3);letter-spacing:.03em}
footer span{color:var(--red)}

/* ── RESPONSIVE ── */
@media(max-width:540px){
  .hero{padding:48px 20px 40px}
  .hero h1{font-size:1.8rem}
  .search-box{flex-direction:column;border-radius:var(--radius)}
  .search-btn{padding:14px;border-radius:0}
  .tabs{overflow-x:auto}
  header{padding:0 16px}
}
"""

# ── HTML shell ────────────────────────────────────────────────────────────────
def html_shell(content: str, lang: str = "ro", vin: str = "") -> str:
    tr = T[lang]
    lang_links = "".join(
        f'<a href="?lang={l}&vin={vin}" class="lang-btn {"active" if l == lang else ""}">{n}</a>'
        for l, n in LANG_NAMES.items()
    )
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Feduk USA — {tr['title']}</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON_URI}"/>
<style>{CSS}</style>
</head>
<body>
<header>
  <a href="/?lang={lang}" class="logo">
    <div class="logo-icon">FU</div>
    <div>
      <span class="logo-name">FEDUK USA</span>
      <span class="logo-sub">Auto · America · Canada · Korea</span>
    </div>
  </a>
  <div class="lang-switcher">{lang_links}</div>
</header>

<div class="hero">
  <div class="hero-eyebrow">Feduk USA Car Platform</div>
  <h1>{tr['title']}</h1>
  <p>{tr['subtitle']}</p>
  <div class="search-wrap">
    <form method="get" action="/search" autocomplete="off">
      <input type="hidden" name="lang" value="{lang}"/>
      <div class="search-box">
        <input name="vin" type="text" placeholder="{tr['placeholder']}"
               value="{vin}" maxlength="17"
               autocapitalize="characters"
               oninput="this.value=this.value.toUpperCase()"/>
        <button type="submit" class="search-btn">{tr['btn_search']}</button>
      </div>
    </form>
  </div>
</div>

<main>{content}</main>

<footer>{tr['footer'].replace('Feduk USA','<span>Feduk USA</span>')}</footer>
</body>
</html>"""


# ── Analysis card ─────────────────────────────────────────────────────────────
def analysis_html(report, lang: str) -> str:
    tr = T[lang]
    bodies = ""
    for l in ("ro", "ru", "en"):
        text = getattr(report, f"ai_analysis_{l}") or ""
        body = md.markdown(text, extensions=["nl2br", "tables"]) if text else "<p style='color:var(--text-3)'>—</p>"
        active = "active" if l == lang else ""
        bodies += f'<div class="lang-body {active} analysis-content" id="ab-{l}">{body}</div>'

    pills = "".join(
        f'<button class="lang-pill {"active" if l == lang else ""}" onclick="switchLang(\'{l}\')">{n}</button>'
        for l, n in LANG_NAMES.items()
    )

    has_pdf = bool(report.pdf_file)
    if has_pdf:
        pdf_url = f"/pdf/{report.vin}"
        pdf_content = f"""
        <div class="pdf-area">
          <div class="pdf-toolbar">
            <span class="pdf-vin">Carfax · {report.vin}</span>
            <a href="{pdf_url}" download="carfax_{report.vin}.pdf" class="pdf-cta">
              ↓ &nbsp;{tr['btn_pdf']}
            </a>
          </div>
          <div class="pdf-frame-wrap">
            <iframe
              class="pdf-frame"
              src="{pdf_url}#toolbar=1&navpanes=0&scrollbar=1&view=FitH"
              title="Carfax {report.vin}"
              onload="this.nextElementSibling.style.display='none'"
              onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
            </iframe>
            <div class="pdf-fallback">
              Browserul tău nu poate afișa PDF-ul direct.
              <a href="{pdf_url}" target="_blank">Deschide PDF →</a>
            </div>
          </div>
        </div>"""
    else:
        pdf_content = '<div class="pdf-area"><p style="color:var(--text-3);font-size:.9rem;padding:40px;text-align:center">PDF indisponibil.</p></div>'

    return f"""
<div class="card">
  <div class="card-top">
    <span class="card-top-title">{tr['vin_label']}</span>
    <span class="vin-tag">{report.vin}</span>
  </div>
  <div class="tabs">
    <div class="tab active" onclick="switchTab('analysis',this)">{tr['tab_analysis']}</div>
    <div class="tab" onclick="switchTab('pdf',this)">{tr['tab_pdf']}</div>
  </div>
  <div class="tab-pane active" id="tab-analysis">
    <div class="lang-pills">{pills}</div>
    {bodies}
  </div>
  <div class="tab-pane" id="tab-pdf">{pdf_content}</div>
</div>
<script>
function switchTab(name,el){{
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}}
function switchLang(l){{
  document.querySelectorAll('.lang-pill').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.lang-body').forEach(b=>b.classList.remove('active'));
  document.querySelector('.lang-pill[onclick*="'+l+'"]').classList.add('active');
  document.getElementById('ab-'+l).classList.add('active');
}}
</script>"""


# ── Not-found card ────────────────────────────────────────────────────────────
def not_found_html(vin: str, lang: str) -> str:
    tr = T[lang]
    body_text = tr["not_found_body"].format(vin=vin)
    return f"""
<div class="card">
  <div class="not-found">
    <div class="nf-icon">🔍</div>
    <h2>{tr['not_found_title']}</h2>
    <p>{body_text}</p>
    <p>{tr['not_found_cta']}</p>
    <a href="https://t.me/fedukusa" target="_blank" class="tg-btn">
      ✈️ &nbsp;{tr['contact_btn']}
    </a>
  </div>
</div>"""


# ── BMW helpers ───────────────────────────────────────────────────────────────
def _bmw_has_real_data(bmw_equipment: str | None) -> bool:
    if not bmw_equipment or len(bmw_equipment.strip()) < 400:
        return False
    err_keywords = ("429", "too many requests", "rate limit", "no vehicle data",
                    "does not contain", "navigation elements", "eroare", "ошибка")
    low = bmw_equipment.lower()
    return not any(k in low for k in err_keywords)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, lang: str = "ro"):
    lang = lang if lang in T else "ro"
    return HTMLResponse(html_shell("", lang))


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, vin: str = "", lang: str = "ro"):
    lang = lang if lang in T else "ro"
    vin  = vin.strip().upper()

    if not vin:
        return HTMLResponse(html_shell("", lang))

    if not VIN_RE.match(vin):
        err = f'<p class="error-msg">{T[lang]["error_vin"]}</p>'
        return HTMLResponse(html_shell(err, lang, vin))

    async with AsyncSessionLocal() as session:
        from database import CarfaxReport
        result = await session.scalar(
            select(CarfaxReport).where(CarfaxReport.vin == vin)
        )

    content = analysis_html(result, lang) if result else not_found_html(vin, lang)
    return HTMLResponse(html_shell(content, lang, vin))


@app.get("/pdf/{vin}")
async def serve_pdf(vin: str):
    vin = vin.strip().upper()
    async with AsyncSessionLocal() as session:
        from database import CarfaxReport
        result = await session.scalar(
            select(CarfaxReport).where(CarfaxReport.vin == vin)
        )
    if not result or not result.pdf_file:
        return Response(content="PDF not found", status_code=404)
    # inline → renders in iframe/browser; the download button uses the `download` attribute
    return Response(
        content=bytes(result.pdf_file),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="carfax_{vin}.pdf"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@app.get("/bmw/{vin}/retry")
async def bmw_retry(vin: str, lang: str = "ro"):
    vin  = vin.strip().upper()
    lang = lang if lang in T else "ro"
    from database import CarfaxReport
    from bmw_lookup import fetch_bimmer_equipment
    from analyzer import synthesize_bmw_equipment
    async with AsyncSessionLocal() as session:
        record = await session.scalar(select(CarfaxReport).where(CarfaxReport.vin == vin))
        if record:
            bimmer = await fetch_bimmer_equipment(vin)
            if bimmer.found:
                equip_text = await synthesize_bmw_equipment(bimmer.raw_html_text, lang)
                if _bmw_has_real_data(equip_text):
                    record.bmw_equipment = equip_text
                    await session.commit()
    return RedirectResponse(url=f"/bmw/{vin}?lang={lang}", status_code=303)


@app.get("/bmw/{vin}", response_class=HTMLResponse)
async def bmw_equipment(vin: str, lang: str = "ro"):
    vin  = vin.strip().upper()
    lang = lang if lang in T else "ro"

    async with AsyncSessionLocal() as session:
        from database import CarfaxReport
        result = await session.scalar(
            select(CarfaxReport).where(CarfaxReport.vin == vin)
        )

    has_data = result and _bmw_has_real_data(result.bmw_equipment if result else None)

    if not has_data:
        content = f"""
<div class="card">
  <div class="card-top">
    <span class="card-top-title">⚙ BMW Equipment</span>
    <span class="vin-tag">{vin}</span>
  </div>
  <div class="not-found">
    <div class="nf-icon">⚙️</div>
    <h2>Equipment data unavailable</h2>
    <p>bimmer.work could not be reached or returned no data for this VIN.</p>
    <p style="color:var(--text-3);font-size:.85rem;margin-top:6px">
      Usually a temporary rate-limit — try again in a few seconds.
    </p>
    <a href="/bmw/{vin}/retry?lang={lang}" class="retry-btn">↺ &nbsp;Retry bimmer.work</a>
    <br><a href="/search?lang={lang}&vin={vin}" style="display:inline-block;margin-top:16px;color:var(--red);font-size:.85rem;text-decoration:none;font-weight:500">← Back to analysis</a>
  </div>
</div>"""
        return HTMLResponse(html_shell(content, lang, vin))

    equip_html = md.markdown(result.bmw_equipment, extensions=["nl2br", "tables"])
    content = f"""
<div class="card">
  <div class="card-top">
    <span class="card-top-title">⚙ BMW Equipment</span>
    <span class="vin-tag">{vin}</span>
  </div>
  <div class="tab-pane active">
    <div class="equip-meta">
      <a href="https://bimmer.work" target="_blank">bimmer.work</a>
      <span class="equip-sep">·</span>
      <a href="/search?lang={lang}&vin={vin}">← Back to analysis</a>
    </div>
    <div class="analysis-content">{equip_html}</div>
  </div>
</div>"""
    return HTMLResponse(html_shell(content, lang, vin))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("webapp:app", host="0.0.0.0", port=port, log_level="info")
