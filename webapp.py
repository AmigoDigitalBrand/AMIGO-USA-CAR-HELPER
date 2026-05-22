import os
import re
import textwrap
from typing import Optional

import markdown as md
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
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

# ── Translations ─────────────────────────────────────────────────────────────
T = {
    "ro": {
        "title": "Verifică Mașina",
        "subtitle": "Introdu VIN-ul și vezi raportul complet + analiza experților noștri",
        "placeholder": "ex: 5UXTS1C00M9H70629",
        "btn_search": "Verifică VIN",
        "tab_analysis": "Analiza AMIGO",
        "tab_pdf": "Raport PDF",
        "btn_pdf": "Deschide Raportul PDF",
        "not_found_title": "Mașina nu a trecut analiza Feduk",
        "not_found_body": "VIN-ul <strong>{vin}</strong> nu a fost analizat încă de echipa noastră.",
        "not_found_cta": "Contactează-l pe Feduk direct pe Telegram pentru a solicita o analiză:",
        "contact_btn": "Scrie pe Telegram @fedukusa",
        "footer": "© 2026 Feduk USA · Auto din America, Canada, Korea",
        "vin_label": "VIN",
        "lang_note": "Analiză disponibilă în:",
        "error_vin": "VIN-ul trebuie să conțină exact 17 caractere alfanumerice.",
    },
    "ru": {
        "title": "Проверить Автомобиль",
        "subtitle": "Введите VIN и получите полный отчёт + анализ наших экспертов",
        "placeholder": "напр.: 5UXTS1C00M9H70629",
        "btn_search": "Проверить VIN",
        "tab_analysis": "Анализ AMIGO",
        "tab_pdf": "Отчёт PDF",
        "btn_pdf": "Открыть PDF Отчёт",
        "not_found_title": "Автомобиль не прошёл анализ Feduk",
        "not_found_body": "VIN <strong>{vin}</strong> ещё не был проанализирован нашей командой.",
        "not_found_cta": "Свяжитесь с Feduk напрямую в Telegram для запроса анализа:",
        "contact_btn": "Написать в Telegram @fedukusa",
        "footer": "© 2026 Feduk USA · Авто из Америки, Канады, Кореи",
        "vin_label": "VIN",
        "lang_note": "Анализ доступен на:",
        "error_vin": "VIN должен содержать ровно 17 буквенно-цифровых символов.",
    },
    "en": {
        "title": "Check the Car",
        "subtitle": "Enter the VIN and view the full report + our expert analysis",
        "placeholder": "e.g. 5UXTS1C00M9H70629",
        "btn_search": "Check VIN",
        "tab_analysis": "AMIGO Analysis",
        "tab_pdf": "PDF Report",
        "btn_pdf": "Open PDF Report",
        "not_found_title": "Car hasn't passed Feduk analysis",
        "not_found_body": "VIN <strong>{vin}</strong> has not been analysed by our team yet.",
        "not_found_cta": "Contact Feduk directly on Telegram to request an analysis:",
        "contact_btn": "Message @fedukusa on Telegram",
        "footer": "© 2026 Feduk USA · Cars from America, Canada, Korea",
        "vin_label": "VIN",
        "lang_note": "Analysis available in:",
        "error_vin": "VIN must be exactly 17 alphanumeric characters.",
    },
}

LANG_NAMES = {"ro": "🇷🇴 RO", "ru": "🇷🇺 RU", "en": "🇬🇧 EN"}

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)

# ── HTML shell ────────────────────────────────────────────────────────────────
def html_shell(content: str, lang: str = "ro", vin: str = "") -> str:
    t = T[lang]
    lang_links = " · ".join(
        f'<a href="?lang={l}&vin={vin}" class="lang-link {"active" if l == lang else ""}">{n}</a>'
        for l, n in LANG_NAMES.items()
    )
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Feduk USA — {t['title']}</title>
<style>
  :root {{
    --red:#C8102E; --red-dark:#9b0c22; --black:#0f0f0f; --white:#fff;
    --gray:#f5f5f5; --border:#e0e0e0; --text:#1a1a1a; --muted:#666;
    --radius:12px; --shadow:0 4px 24px rgba(0,0,0,.10);
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--gray);color:var(--text);min-height:100vh;display:flex;flex-direction:column}}
  /* ── Header ── */
  header{{background:var(--black);padding:16px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}}
  .logo{{display:flex;align-items:center;gap:14px;text-decoration:none}}
  .logo-text{{color:var(--white)}}
  .logo-text strong{{display:block;font-size:1.3rem;letter-spacing:.04em;color:var(--red)}}
  .logo-text span{{font-size:.78rem;color:#aaa;letter-spacing:.05em}}
  .lang-switcher{{display:flex;gap:8px;align-items:center}}
  .lang-link{{color:#aaa;text-decoration:none;font-size:.82rem;font-weight:600;padding:4px 10px;border-radius:20px;transition:.2s}}
  .lang-link:hover,.lang-link.active{{background:var(--red);color:var(--white)}}
  /* ── Hero ── */
  .hero{{background:linear-gradient(135deg,var(--black) 60%,#1a0005 100%);padding:60px 24px 50px;text-align:center}}
  .hero h1{{color:var(--white);font-size:clamp(1.6rem,4vw,2.4rem);margin-bottom:12px}}
  .hero p{{color:#bbb;font-size:1rem;margin-bottom:32px}}
  /* ── Search form ── */
  .search-box{{max-width:560px;margin:0 auto;display:flex;gap:0;border-radius:var(--radius);overflow:hidden;box-shadow:0 0 0 3px rgba(200,16,46,.4)}}
  .search-box input{{flex:1;padding:16px 20px;font-size:1rem;border:none;outline:none;background:var(--white);color:var(--text)}}
  .search-box button{{background:var(--red);color:var(--white);border:none;padding:16px 28px;font-size:1rem;font-weight:700;cursor:pointer;transition:.2s;white-space:nowrap}}
  .search-box button:hover{{background:var(--red-dark)}}
  .error-msg{{color:#ff6b6b;font-size:.88rem;margin-top:10px;text-align:center}}
  /* ── Main content ── */
  main{{flex:1;max-width:900px;width:100%;margin:40px auto;padding:0 20px}}
  /* ── Card ── */
  .card{{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden;margin-bottom:24px}}
  .card-header{{background:var(--black);color:var(--white);padding:16px 24px;display:flex;align-items:center;gap:12px}}
  .card-header .vin-badge{{background:var(--red);color:var(--white);font-weight:700;padding:4px 12px;border-radius:20px;font-size:.85rem;letter-spacing:.08em}}
  /* ── Tabs ── */
  .tabs{{display:flex;border-bottom:2px solid var(--border)}}
  .tab{{padding:14px 24px;cursor:pointer;font-weight:600;color:var(--muted);border-bottom:3px solid transparent;margin-bottom:-2px;transition:.2s;user-select:none}}
  .tab.active{{color:var(--red);border-bottom-color:var(--red)}}
  .tab-content{{display:none;padding:28px}}
  .tab-content.active{{display:block}}
  /* ── Analysis ── */
  .analysis-langs{{display:flex;gap:8px;margin-bottom:20px}}
  .alang{{padding:6px 16px;border-radius:20px;border:2px solid var(--border);cursor:pointer;font-size:.85rem;font-weight:600;transition:.2s}}
  .alang.active{{background:var(--red);color:var(--white);border-color:var(--red)}}
  .analysis-body{{display:none;line-height:1.75;color:var(--text)}}
  .analysis-body.active{{display:block}}
  .analysis-body h2{{font-size:1.1rem;color:var(--red);margin:20px 0 8px;}}
  .analysis-body h3{{font-size:1rem;margin:16px 0 6px}}
  .analysis-body p{{margin-bottom:12px}}
  .analysis-body ul{{padding-left:20px;margin-bottom:12px}}
  .analysis-body li{{margin-bottom:6px}}
  .analysis-body strong{{color:var(--black)}}
  /* ── PDF section ── */
  .pdf-section{{text-align:center;padding:40px 24px}}
  .pdf-icon{{font-size:3rem;margin-bottom:16px}}
  .pdf-btn{{display:inline-flex;align-items:center;gap:10px;background:var(--red);color:var(--white);padding:14px 32px;border-radius:var(--radius);font-size:1rem;font-weight:700;text-decoration:none;transition:.2s;margin-top:12px}}
  .pdf-btn:hover{{background:var(--red-dark);transform:translateY(-1px)}}
  /* ── Not found ── */
  .not-found{{text-align:center;padding:50px 24px}}
  .not-found-icon{{font-size:3rem;margin-bottom:20px}}
  .not-found h2{{font-size:1.4rem;margin-bottom:12px;color:var(--black)}}
  .not-found p{{color:var(--muted);margin-bottom:8px;line-height:1.6}}
  .tg-btn{{display:inline-flex;align-items:center;gap:10px;background:#229ED9;color:var(--white);padding:14px 28px;border-radius:var(--radius);font-size:1rem;font-weight:700;text-decoration:none;transition:.2s;margin-top:20px}}
  .tg-btn:hover{{opacity:.9;transform:translateY(-1px)}}
  /* ── Footer ── */
  footer{{background:var(--black);color:#666;text-align:center;padding:18px;font-size:.82rem;margin-top:auto}}
  footer span{{color:var(--red)}}
  @media(max-width:520px){{
    .search-box{{flex-direction:column;border-radius:var(--radius)}}
    .search-box input,.search-box button{{border-radius:0}}
    .tabs{{overflow-x:auto}}
  }}
</style>
</head>
<body>
<header>
  <a href="/?lang={lang}" class="logo">
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
      <rect width="40" height="40" rx="8" fill="#C8102E"/>
      <text x="7" y="28" font-size="22" font-weight="900" fill="white" font-family="Arial">FU</text>
    </svg>
    <div class="logo-text">
      <strong>FEDUK USA</strong>
      <span>Auto din America, Canada, Korea</span>
    </div>
  </a>
  <div class="lang-switcher">{lang_links}</div>
</header>

<section class="hero">
  <h1>{t['title']}</h1>
  <p>{t['subtitle']}</p>
  <form method="get" action="/search">
    <input type="hidden" name="lang" value="{lang}"/>
    <div class="search-box">
      <input name="vin" type="text" placeholder="{t['placeholder']}"
             value="{vin}" maxlength="17" autocomplete="off" autocapitalize="characters"
             oninput="this.value=this.value.toUpperCase()"/>
      <button type="submit">{t['btn_search']}</button>
    </div>
  </form>
</section>

<main>{content}</main>

<footer>{t['footer'].replace('Feduk USA', '<span>Feduk USA</span>')}</footer>
</body>
</html>"""


def analysis_html(report, lang: str) -> str:
    t = T[lang]
    bodies = ""
    for l in ("ro", "ru", "en"):
        text = getattr(report, f"ai_analysis_{l}") or ""
        html_body = md.markdown(text, extensions=["nl2br"]) if text else "<p>—</p>"
        active = "active" if l == lang else ""
        bodies += f'<div class="analysis-body {active}" id="ab-{l}">{html_body}</div>'

    lang_btns = "".join(
        f'<div class="alang {"active" if l == lang else ""}" onclick="switchLang(\'{l}\')">{n}</div>'
        for l, n in LANG_NAMES.items()
    )

    has_pdf = bool(report.pdf_file)
    pdf_tab_content = ""
    if has_pdf:
        t_pdf = T[lang]
        pdf_tab_content = f"""
        <div class="pdf-section">
          <div class="pdf-icon">📄</div>
          <p style="color:var(--muted);margin-bottom:4px">{t_pdf['vin_label']}: <strong>{report.vin}</strong></p>
          <a href="/pdf/{report.vin}" target="_blank" class="pdf-btn">
            📥 {t_pdf['btn_pdf']}
          </a>
        </div>"""
    else:
        pdf_tab_content = '<div class="pdf-section"><p style="color:var(--muted)">PDF indisponibil.</p></div>'

    return f"""
<div class="card">
  <div class="card-header">
    <span>{T[lang]['vin_label']}</span>
    <span class="vin-badge">{report.vin}</span>
  </div>
  <div class="tabs">
    <div class="tab active" onclick="switchTab('analysis',this)">{T[lang]['tab_analysis']}</div>
    <div class="tab" onclick="switchTab('pdf',this)">{T[lang]['tab_pdf']}</div>
  </div>
  <div class="tab-content active" id="tab-analysis">
    <div class="analysis-langs">{lang_btns}</div>
    {bodies}
  </div>
  <div class="tab-content" id="tab-pdf">{pdf_tab_content}</div>
</div>
<script>
function switchTab(name, el) {{
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}}
function switchLang(l) {{
  document.querySelectorAll('.alang').forEach(a=>a.classList.remove('active'));
  document.querySelectorAll('.analysis-body').forEach(a=>a.classList.remove('active'));
  document.querySelector('.alang[onclick="switchLang(\\''+l+'\\')"]').classList.add('active');
  document.getElementById('ab-'+l).classList.add('active');
}}
</script>"""


def not_found_html(vin: str, lang: str) -> str:
    t = T[lang]
    body_text = t["not_found_body"].format(vin=vin)
    return f"""
<div class="card">
  <div class="not-found">
    <div class="not-found-icon">🔍</div>
    <h2>{t['not_found_title']}</h2>
    <p>{body_text}</p>
    <p>{t['not_found_cta']}</p>
    <a href="https://t.me/fedukusa" target="_blank" class="tg-btn">
      ✈️ {t['contact_btn']}
    </a>
  </div>
</div>"""


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, lang: str = "ro"):
    lang = lang if lang in T else "ro"
    return HTMLResponse(html_shell("", lang))


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, vin: str = "", lang: str = "ro"):
    lang = lang if lang in T else "ro"
    vin = vin.strip().upper()

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

    if not result:
        content = not_found_html(vin, lang)
    else:
        content = analysis_html(result, lang)

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

    return Response(
        content=bytes(result.pdf_file),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="carfax_{vin}.pdf"'},
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("webapp:app", host="0.0.0.0", port=port, log_level="info")
