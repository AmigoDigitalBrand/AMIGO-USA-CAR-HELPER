import base64
import os
import re
import secrets
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import markdown as md
from fastapi import Cookie, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
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

# ── Admin Auth ───────────────────────────────────────────────────────────────
ADMIN_USER   = os.environ.get("ADMIN_USER",   "Feduk")
ADMIN_PASS   = os.environ.get("ADMIN_PASS",   "Password123!")
ADMIN_COOKIE = "amigo_admin"
_sessions: dict[str, datetime] = {}

def _create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = datetime.utcnow() + timedelta(hours=8)
    return token

def _valid_session(token: str | None) -> bool:
    if not token or token not in _sessions:
        return False
    if datetime.utcnow() > _sessions[token]:
        _sessions.pop(token, None)
        return False
    return True

# ── Favicon ───────────────────────────────────────────────────────────────────
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
_FAVICON_B64 = base64.b64encode(_FAVICON_SVG.encode()).decode()
FAVICON_URI  = f"data:image/svg+xml;base64,{_FAVICON_B64}"

# ── Translations ─────────────────────────────────────────────────────────────
T = {
    "ro": {
        "title": "Verifică Mașina",
        "subtitle": "Introdu VIN-ul sau numărul de telefon pentru raportul complet",
        "placeholder_vin": "ex: 5UXTS1C00M9H70629",
        "placeholder_phone": "ex: 069 123 456",
        "btn_search": "Verifică",
        "tab_vin": "🔑 VIN",
        "tab_phone": "📱 Telefon",
        "tab_analysis": "Analiza asistentului virtual lui Feduk",
        "tab_pdf": "Raport PDF",
        "tab_bmw": "⚙️ Echipare BMW",
        "tab_prices": "💰 Prețuri",
        "btn_pdf": "Deschide Raportul PDF",
        "not_found_title": "VIN-ul nu a fost analizat",
        "not_found_body": "VIN-ul <strong>{vin}</strong> nu a trecut prin analiza Feduk USA.",
        "not_found_cta": "Trimite raportul Carfax pe Telegram pentru o analiză completă:",
        "phone_not_found_title": "Număr negăsit",
        "phone_not_found_body": "Numărul <strong>{phone}</strong> nu este asociat cu nicio mașină.",
        "phone_select_title": "Mașinile tale",
        "phone_select_body": "Am găsit {n} mașini asociate cu <strong>{phone}</strong>. Selectează:",
        "contact_btn": "@fedukusa pe Telegram",
        "footer": "© 2026 Feduk USA · Auto din America, Canada, Korea",
        "vin_label": "VIN",
        "error_vin": "VIN-ul trebuie să conțină exact 17 caractere alfanumerice.",
        "error_phone": "Introdu un număr de telefon valid (min. 7 cifre).",
        "prices_title": "Defalcare Costuri",
        "prices_car": "🚗 Preț mașină",
        "prices_auction": "🔨 Taxă licitație",
        "prices_transfer": "📋 Comision transfer",
        "prices_shipping": "🚢 Transport SUA → Moldova",
        "prices_customs": "🛃 Devamare",
        "prices_broker": "👨‍⚖️ Broker vamal",
        "prices_total": "TOTAL",
        "prices_rate_note": "Curs live ·",
    },
    "ru": {
        "title": "Проверить Автомобиль",
        "subtitle": "Введите VIN или номер телефона для полного отчёта",
        "placeholder_vin": "напр.: 5UXTS1C00M9H70629",
        "placeholder_phone": "напр.: 069 123 456",
        "btn_search": "Проверить",
        "tab_vin": "🔑 VIN",
        "tab_phone": "📱 Телефон",
        "tab_analysis": "Анализ виртуального ассистента Feduk",
        "tab_pdf": "Отчёт PDF",
        "tab_bmw": "⚙️ Комплектация BMW",
        "tab_prices": "💰 Стоимость",
        "btn_pdf": "Открыть PDF Отчёт",
        "not_found_title": "VIN не найден в базе",
        "not_found_body": "VIN <strong>{vin}</strong> ещё не анализировался командой Feduk USA.",
        "not_found_cta": "Отправь Carfax в Telegram для получения полного анализа:",
        "phone_not_found_title": "Номер не найден",
        "phone_not_found_body": "Номер <strong>{phone}</strong> не привязан ни к одному автомобилю.",
        "phone_select_title": "Ваши автомобили",
        "phone_select_body": "Найдено {n} авто для <strong>{phone}</strong>. Выберите:",
        "contact_btn": "@fedukusa в Telegram",
        "footer": "© 2026 Feduk USA · Авто из Америки, Канады, Кореи",
        "vin_label": "VIN",
        "error_vin": "VIN должен содержать ровно 17 буквенно-цифровых символов.",
        "error_phone": "Введите корректный номер телефона (мин. 7 цифр).",
        "prices_title": "Разбивка расходов",
        "prices_car": "🚗 Цена автомобиля",
        "prices_auction": "🔨 Аукционный сбор",
        "prices_transfer": "📋 Комиссия за перевод",
        "prices_shipping": "🚢 Доставка США → Молдова",
        "prices_customs": "🛃 Таможенное оформление",
        "prices_broker": "👨‍⚖️ Таможенный брокер",
        "prices_total": "ИТОГО",
        "prices_rate_note": "Курс live ·",
    },
    "en": {
        "title": "Check the Car",
        "subtitle": "Enter VIN or phone number for the full report",
        "placeholder_vin": "e.g. 5UXTS1C00M9H70629",
        "placeholder_phone": "e.g. 069 123 456",
        "btn_search": "Check",
        "tab_vin": "🔑 VIN",
        "tab_phone": "📱 Phone",
        "tab_analysis": "Feduk Virtual Assistant Analysis",
        "tab_pdf": "PDF Report",
        "tab_bmw": "⚙️ BMW Equipment",
        "tab_prices": "💰 Pricing",
        "btn_pdf": "Open PDF Report",
        "not_found_title": "VIN not found",
        "not_found_body": "VIN <strong>{vin}</strong> has not been analysed by the Feduk USA team yet.",
        "not_found_cta": "Send your Carfax PDF on Telegram for a full analysis:",
        "phone_not_found_title": "Number not found",
        "phone_not_found_body": "Number <strong>{phone}</strong> is not associated with any car.",
        "phone_select_title": "Your Cars",
        "phone_select_body": "Found {n} cars for <strong>{phone}</strong>. Select one:",
        "contact_btn": "@fedukusa on Telegram",
        "footer": "© 2026 Feduk USA · Cars from America, Canada, Korea",
        "vin_label": "VIN",
        "error_vin": "VIN must be exactly 17 alphanumeric characters.",
        "error_phone": "Enter a valid phone number (min. 7 digits).",
        "prices_title": "Cost Breakdown",
        "prices_car": "🚗 Car price",
        "prices_auction": "🔨 Auction fee",
        "prices_transfer": "📋 Transfer commission",
        "prices_shipping": "🚢 Shipping USA → Moldova",
        "prices_customs": "🛃 Customs clearance",
        "prices_broker": "👨‍⚖️ Customs broker",
        "prices_total": "TOTAL",
        "prices_rate_note": "Live rate ·",
    },
}

LANG_NAMES = {"ro": "RO", "ru": "RU", "en": "EN"}
VIN_RE     = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$", re.IGNORECASE)

# ── CSS ───────────────────────────────────────────────────────────────────────
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
  --amber:#f59e0b;
  --blue:#3b82f6;
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
.header-right{display:flex;align-items:center;gap:12px}
.lang-switcher{display:flex;gap:2px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:3px}
.lang-btn{font-family:var(--sans);font-size:.75rem;font-weight:600;color:var(--text-3);background:none;border:none;cursor:pointer;padding:4px 10px;border-radius:6px;transition:var(--transition);text-decoration:none;letter-spacing:.04em}
.lang-btn:hover{color:var(--text);background:var(--border-2)}
.lang-btn.active{color:var(--text);background:var(--surface);box-shadow:0 1px 3px rgba(0,0,0,.4)}
.admin-header-btn{font-size:.75rem;font-weight:600;color:var(--text-3);text-decoration:none;padding:4px 12px;border-radius:6px;border:1px solid var(--border-2);transition:var(--transition)}
.admin-header-btn:hover{color:var(--text);border-color:var(--text-3)}

/* ── HERO ── */
.hero{padding:72px 24px 64px;text-align:center}
.hero-eyebrow{font-size:.72rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--red);margin-bottom:16px}
.hero h1{font-size:clamp(2rem,5vw,3.2rem);font-weight:700;letter-spacing:-.03em;line-height:1.1;color:var(--text);margin-bottom:14px}
.hero p{color:var(--text-2);font-size:1rem;margin-bottom:40px;max-width:480px;margin-left:auto;margin-right:auto;line-height:1.6}

/* ── SEARCH ── */
.search-wrap{max-width:540px;margin:0 auto}
.search-mode{display:flex;gap:4px;margin-bottom:12px;justify-content:center}
.search-mode-btn{font-family:var(--sans);font-size:.8rem;font-weight:600;padding:6px 18px;border-radius:20px;border:1px solid var(--border-2);background:none;color:var(--text-3);cursor:pointer;transition:var(--transition)}
.search-mode-btn.active{background:var(--red);border-color:var(--red);color:#fff}
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
.card-top{background:var(--surface-2);padding:16px 22px;display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--border);flex-wrap:wrap}
.card-top-title{font-size:.8rem;font-weight:600;color:var(--text-2);letter-spacing:.06em;text-transform:uppercase}
.vin-tag{font-family:var(--mono);font-size:.8rem;font-weight:500;background:var(--red);color:#fff;padding:3px 10px;border-radius:6px;letter-spacing:.06em;cursor:pointer;user-select:none;transition:background var(--transition)}
.vin-tag:hover{background:var(--red-dim)}
.vin-tag.copied{background:#16a34a}
.client-badge{font-size:.78rem;font-weight:500;color:var(--text-2);background:var(--surface);border:1px solid var(--border-2);padding:3px 10px;border-radius:6px;margin-left:auto}

/* ── TABS ── */
.tabs{display:flex;padding:0 22px;border-bottom:1px solid var(--border);gap:0;overflow-x:auto}
.tab{font-size:.82rem;font-weight:600;color:var(--text-3);padding:14px 16px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;transition:color var(--transition),border-color var(--transition);letter-spacing:.02em;user-select:none;white-space:nowrap}
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
.analysis-content ul,.analysis-content ol{padding-left:18px;margin-bottom:12px}
.analysis-content li{margin-bottom:6px;color:var(--text-2);font-size:.925rem}
.analysis-content strong{color:var(--text);font-weight:600}
.analysis-content table{width:100%;border-collapse:collapse;margin-bottom:16px;font-size:.875rem}
.analysis-content th{background:var(--surface-2);color:var(--text-2);font-weight:600;padding:8px 12px;text-align:left;border:1px solid var(--border)}
.analysis-content td{padding:8px 12px;border:1px solid var(--border);color:var(--text-2)}
.analysis-content code{font-family:var(--mono);font-size:.8rem;background:var(--surface-2);padding:2px 6px;border-radius:4px;color:var(--text)}
.analysis-content hr{border:none;border-top:1px solid var(--border);margin:20px 0}

/* ── PDF ── */
.pdf-area{padding:20px 24px 24px}
.pdf-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;gap:12px;flex-wrap:wrap}
.pdf-vin{font-family:var(--mono);font-size:.78rem;color:var(--text-3);letter-spacing:.08em}
.pdf-cta{display:inline-flex;align-items:center;gap:8px;background:var(--red);color:#fff;padding:9px 20px;border-radius:8px;font-size:.84rem;font-weight:600;text-decoration:none;transition:background var(--transition);letter-spacing:.02em;white-space:nowrap}
.pdf-cta:hover{background:var(--red-dim)}
.pdf-frame-wrap{border-radius:8px;overflow:hidden;border:1px solid var(--border);background:#1c1c1c}
.pdf-frame{width:100%;height:72vh;min-height:480px;border:none;display:block}
.pdf-fallback{display:none;text-align:center;padding:40px 20px;color:var(--text-3);font-size:.88rem}
.pdf-fallback a{color:var(--red);font-weight:600;text-decoration:none}

/* ── PRICING TAB ── */
.price-section{padding:4px 0 20px}
.price-section h3{font-size:.78rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--text-3);margin-bottom:16px}
.price-table{width:100%;border-collapse:collapse;margin-bottom:8px}
.price-table th{font-size:.75rem;font-weight:600;color:var(--text-3);letter-spacing:.06em;text-transform:uppercase;padding:8px 14px;text-align:right;border-bottom:1px solid var(--border)}
.price-table th:first-child{text-align:left}
.price-table td{padding:11px 14px;border-bottom:1px solid var(--border);font-size:.9rem;color:var(--text-2);text-align:right}
.price-table td:first-child{text-align:left;color:var(--text)}
.price-table tr:last-child td{border-bottom:none}
.price-table .total-row td{background:var(--surface-2);font-weight:700;font-size:.95rem;color:var(--text);border-top:2px solid var(--border-2)}
.price-usd{font-family:var(--mono);color:var(--text)}
.price-mdl,.price-eur{font-family:var(--mono);color:var(--text-2)}
.rates-note{font-size:.75rem;color:var(--text-3);margin-top:12px;display:flex;align-items:center;gap:6px}
.rates-dot{width:6px;height:6px;border-radius:50%;background:var(--green);display:inline-block;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* ── PHONE SELECTION ── */
.car-list{display:flex;flex-direction:column;gap:10px;margin-top:16px}
.car-list-item{display:flex;align-items:center;justify-content:space-between;background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:14px 18px;text-decoration:none;transition:border-color var(--transition),background var(--transition)}
.car-list-item:hover{border-color:var(--red);background:rgba(220,38,38,.06)}
.car-list-info{display:flex;flex-direction:column;gap:4px}
.car-list-name{font-size:.95rem;font-weight:600;color:var(--text)}
.car-list-vin{font-family:var(--mono);font-size:.78rem;color:var(--text-3)}
.car-list-arrow{color:var(--text-3);font-size:1.2rem}

/* ── NOT FOUND ── */
.not-found{text-align:center;padding:60px 24px}
.nf-icon{width:56px;height:56px;background:var(--surface-2);border:1px solid var(--border);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:1.5rem;margin:0 auto 20px}
.not-found h2{font-size:1.2rem;font-weight:700;letter-spacing:-.02em;margin-bottom:10px}
.not-found p{color:var(--text-2);font-size:.9rem;line-height:1.6;max-width:400px;margin:0 auto 8px}
.tg-btn{display:inline-flex;align-items:center;gap:8px;background:#2AABEE;color:#fff;padding:12px 22px;border-radius:var(--radius);font-size:.88rem;font-weight:600;text-decoration:none;transition:opacity var(--transition),transform var(--transition);margin-top:22px}
.tg-btn:hover{opacity:.88;transform:translateY(-1px)}

/* ── BMW EQUIP ── */
.equip-meta{font-size:.78rem;color:var(--text-3);margin-bottom:24px;display:flex;align-items:center;gap:16px}
.equip-meta a{color:var(--red);text-decoration:none;font-weight:500}
.equip-meta a:hover{text-decoration:underline}
.equip-sep{color:var(--border-2)}

/* ── RETRY BTN ── */
.retry-btn{display:inline-flex;align-items:center;gap:8px;background:var(--surface-2);border:1px solid var(--border-2);color:var(--text-2);padding:11px 22px;border-radius:var(--radius);font-size:.88rem;font-weight:600;text-decoration:none;transition:var(--transition);margin-top:20px;font-family:var(--sans)}
.retry-btn:hover{color:var(--text);border-color:var(--text-3)}

/* ── ADMIN PANEL ── */
.admin-nav{background:var(--surface-2);border-bottom:1px solid var(--border);padding:0 24px;display:flex;gap:0;overflow-x:auto}
.admin-nav-item{font-size:.82rem;font-weight:600;color:var(--text-3);padding:12px 16px;text-decoration:none;border-bottom:2px solid transparent;transition:var(--transition);white-space:nowrap}
.admin-nav-item:hover{color:var(--text)}
.admin-nav-item.active{color:var(--red);border-bottom-color:var(--red)}
.admin-main{max-width:1100px;width:100%;margin:0 auto;padding:32px 24px 64px}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:32px}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:6px}
.stat-label{font-size:.75rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--text-3)}
.stat-value{font-size:2rem;font-weight:700;letter-spacing:-.03em;color:var(--text)}
.stat-sub{font-size:.78rem;color:var(--text-3)}
.data-table{width:100%;border-collapse:collapse;font-size:.875rem}
.data-table th{background:var(--surface-2);color:var(--text-3);font-size:.72rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding:10px 14px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}
.data-table td{padding:12px 14px;border-bottom:1px solid var(--border);color:var(--text-2);vertical-align:middle}
.data-table tr:last-child td{border-bottom:none}
.data-table tr:hover td{background:rgba(255,255,255,.02)}
.data-table td a{color:var(--text);font-weight:600;text-decoration:none}
.data-table td a:hover{color:var(--red)}
.badge{display:inline-block;font-size:.7rem;font-weight:700;letter-spacing:.06em;padding:2px 8px;border-radius:20px;text-transform:uppercase}
.badge-green{background:rgba(34,197,94,.15);color:#22c55e;border:1px solid rgba(34,197,94,.25)}
.badge-gray{background:var(--surface-2);color:var(--text-3);border:1px solid var(--border)}
.badge-amber{background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.25)}
.section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:12px}
.section-title{font-size:1rem;font-weight:700;letter-spacing:-.01em}
.filter-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.filter-input{background:var(--surface-2);border:1px solid var(--border-2);border-radius:8px;padding:7px 14px;font-family:var(--sans);font-size:.82rem;color:var(--text);outline:none;transition:border-color var(--transition)}
.filter-input:focus{border-color:var(--red)}
.filter-select{background:var(--surface-2);border:1px solid var(--border-2);border-radius:8px;padding:7px 14px;font-family:var(--sans);font-size:.82rem;color:var(--text);outline:none;cursor:pointer}
.admin-form{display:flex;flex-direction:column;gap:20px}
.form-section{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:22px}
.form-section-title{font-size:.8rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--text-2);margin-bottom:18px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.form-group{display:flex;flex-direction:column;gap:6px}
.form-label{font-size:.78rem;font-weight:600;color:var(--text-2);letter-spacing:.04em}
.form-input,.form-textarea{background:var(--surface-2);border:1px solid var(--border-2);border-radius:8px;padding:10px 14px;font-family:var(--sans);font-size:.9rem;color:var(--text);outline:none;transition:border-color var(--transition)}
.form-input:focus,.form-textarea:focus{border-color:var(--red)}
.form-textarea{resize:vertical;min-height:80px}
.form-hint{font-size:.72rem;color:var(--text-3)}
.form-check{display:flex;align-items:center;gap:10px;cursor:pointer}
.form-check input{width:16px;height:16px;accent-color:var(--red);cursor:pointer}
.form-check span{font-size:.9rem;color:var(--text-2)}
.code-preview{font-family:var(--mono);font-size:.8rem;background:var(--surface-2);border:1px solid var(--border);border-radius:6px;padding:6px 12px;color:var(--amber);display:inline-block;margin-top:4px}
.btn-primary{background:var(--red);color:#fff;border:none;padding:11px 28px;border-radius:8px;font-family:var(--sans);font-size:.9rem;font-weight:600;cursor:pointer;transition:background var(--transition)}
.btn-primary:hover{background:var(--red-dim)}
.btn-secondary{background:var(--surface-2);color:var(--text-2);border:1px solid var(--border-2);padding:10px 22px;border-radius:8px;font-family:var(--sans);font-size:.9rem;font-weight:600;cursor:pointer;transition:var(--transition);text-decoration:none;display:inline-block}
.btn-secondary:hover{color:var(--text);border-color:var(--text-3)}
.btn-danger{background:rgba(220,38,38,.12);color:#f87171;border:1px solid rgba(220,38,38,.25);padding:10px 22px;border-radius:8px;font-family:var(--sans);font-size:.9rem;font-weight:600;cursor:pointer;transition:var(--transition)}
.btn-danger:hover{background:rgba(220,38,38,.25)}
.btn-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.admin-login-wrap{max-width:360px;margin:80px auto 0;padding:0 20px}
.admin-login-wrap .card{padding:32px}
.admin-login-title{font-size:1.3rem;font-weight:700;letter-spacing:-.02em;margin-bottom:6px}
.admin-login-sub{color:var(--text-3);font-size:.85rem;margin-bottom:28px}
.admin-login-err{background:rgba(220,38,38,.1);border:1px solid rgba(220,38,38,.25);color:#f87171;border-radius:8px;padding:10px 14px;font-size:.85rem;margin-bottom:18px}

/* ── FOOTER ── */
footer{border-top:1px solid var(--border);padding:18px 24px;text-align:center;font-size:.75rem;color:var(--text-3);letter-spacing:.03em}
footer span{color:var(--red)}

/* ── RESPONSIVE ── */
@media(max-width:600px){
  .hero{padding:48px 20px 40px}
  .hero h1{font-size:1.8rem}
  .search-box{flex-direction:column;border-radius:var(--radius)}
  .search-btn{padding:14px;border-radius:0}
  .tabs{overflow-x:auto}
  header{padding:0 16px}
  .form-row{grid-template-columns:1fr}
  .admin-main{padding:20px 16px 48px}
}
"""

# ── HTML shell ─────────────────────────────────────────────────────────────────
def html_shell(content: str, lang: str = "ro", vin: str = "",
               phone: str = "", search_mode: str = "vin",
               is_admin: bool = False) -> str:
    tr = T[lang]
    lang_links = "".join(
        f'<a href="?lang={l}&vin={vin}" class="lang-btn {"active" if l == lang else ""}">{n}</a>'
        for l, n in LANG_NAMES.items()
    )
    admin_link = ('<a href="/admin" class="admin-header-btn">⚙ Admin</a>'
                  if is_admin else
                  '<a href="/admin/login" class="admin-header-btn" style="opacity:.4">Admin</a>')

    vin_active   = "active" if search_mode == "vin"   else ""
    phone_active = "active" if search_mode == "phone" else ""
    vin_display   = "" if search_mode == "phone" else "flex"
    phone_display = "flex" if search_mode == "phone" else "none"

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
  <div class="header-right">
    <div class="lang-switcher">{lang_links}</div>
    {admin_link}
  </div>
</header>

<div class="hero">
  <div class="hero-eyebrow">Feduk USA Car Platform</div>
  <h1>{tr['title']}</h1>
  <p>{tr['subtitle']}</p>
  <div class="search-wrap">
    <div class="search-mode">
      <button class="search-mode-btn {vin_active}" onclick="setMode('vin')">{tr['tab_vin']}</button>
      <button class="search-mode-btn {phone_active}" onclick="setMode('phone')">{tr['tab_phone']}</button>
    </div>
    <form id="form-vin" method="get" action="/search" autocomplete="off" style="display:{vin_display}">
      <input type="hidden" name="lang" value="{lang}"/>
      <input type="hidden" name="mode" value="vin"/>
      <div class="search-box">
        <input name="vin" type="text" placeholder="{tr['placeholder_vin']}"
               value="{vin}" maxlength="17" autocapitalize="characters"
               oninput="this.value=this.value.toUpperCase()"/>
        <button type="submit" class="search-btn">{tr['btn_search']}</button>
      </div>
    </form>
    <form id="form-phone" method="get" action="/search" autocomplete="off" style="display:{phone_display}">
      <input type="hidden" name="lang" value="{lang}"/>
      <input type="hidden" name="mode" value="phone"/>
      <div class="search-box">
        <input name="phone" type="tel" placeholder="{tr['placeholder_phone']}"
               value="{phone}"/>
        <button type="submit" class="search-btn">{tr['btn_search']}</button>
      </div>
    </form>
  </div>
</div>

<main>{content}</main>

<footer>{tr['footer'].replace('Feduk USA','<span>Feduk USA</span>')}</footer>
<script>
function setMode(m){{
  document.querySelectorAll('.search-mode-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('form-vin').style.display   = m==='vin'   ? 'flex' : 'none';
  document.getElementById('form-phone').style.display = m==='phone' ? 'flex' : 'none';
  event.target.classList.add('active');
}}
function switchTab(name,el){{
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
}}
function switchLang(l){{
  document.querySelectorAll('.lang-pill').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.lang-body').forEach(b=>b.classList.remove('active'));
  document.querySelector('.lang-pill[onclick*="\''+l+'\'"]').classList.add('active');
  document.getElementById('ab-'+l).classList.add('active');
}}
function copyVin(el,vin){{
  navigator.clipboard.writeText(vin).then(()=>{{
    const prev=el.textContent;el.textContent='✓ Copied';el.classList.add('copied');
    setTimeout(()=>{{el.textContent=prev;el.classList.remove('copied');}},1800);
  }}).catch(()=>{{
    const r=document.createRange();r.selectNode(el);
    window.getSelection().removeAllRanges();window.getSelection().addRange(r);
    document.execCommand('copy');window.getSelection().removeAllRanges();
    el.textContent='✓ Copied';el.classList.add('copied');
    setTimeout(()=>{{el.textContent=vin;el.classList.remove('copied');}},1800);
  }});
}}
</script>
</body>
</html>"""


# ── BMW helper ────────────────────────────────────────────────────────────────
def _bmw_has_real_data(bmw_equipment: str | None) -> bool:
    if not bmw_equipment or len(bmw_equipment.strip()) < 400:
        return False
    err_kw = ("429","too many requests","rate limit","no vehicle data",
              "does not contain","navigation elements","eroare","ошибка")
    low = bmw_equipment.lower()
    return not any(k in low for k in err_kw)


# ── Pricing helper ───────────────────────────────────────────────────────────
def _has_prices(report) -> bool:
    if not getattr(report, "is_procured", False):
        return False
    return any(
        getattr(report, f"price_{k}_usd", None) not in (None, Decimal("0"), 0)
        for k in ("car","auction","transfer","shipping","customs","broker")
    )

def _fmt_usd(v) -> str:
    if v is None:
        return "—"
    return f"${float(v):,.0f}"

def _price_rows(report, tr: dict) -> str:
    items = [
        ("prices_car",      "car"),
        ("prices_auction",  "auction"),
        ("prices_transfer", "transfer"),
        ("prices_shipping", "shipping"),
        ("prices_customs",  "customs"),
        ("prices_broker",   "broker"),
    ]
    total = 0.0
    rows = ""
    for key, col in items:
        val = getattr(report, f"price_{col}_usd", None)
        if val is None:
            continue
        fv = float(val)
        total += fv
        rows += f"""<tr>
          <td>{tr[key]}</td>
          <td class="price-usd" data-usd="{fv}">{_fmt_usd(val)}</td>
          <td class="price-mdl" data-usd="{fv}">—</td>
          <td class="price-eur" data-usd="{fv}">—</td>
        </tr>"""
    rows += f"""<tr class="total-row">
      <td>{tr['prices_total']}</td>
      <td class="price-usd">${total:,.0f}</td>
      <td class="price-mdl total-mdl" data-usd="{total}">—</td>
      <td class="price-eur total-eur" data-usd="{total}">—</td>
    </tr>"""
    return rows

def pricing_tab_html(report, lang: str) -> str:
    tr = T[lang]
    rows = _price_rows(report, tr)
    return f"""
<div class="tab-pane" id="tab-prices">
  <div class="price-section">
    <h3>{tr['prices_title']}</h3>
    <table class="price-table">
      <thead>
        <tr>
          <th style="text-align:left">Cost</th>
          <th>USD</th><th>MDL</th><th>EUR</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="rates-note">
      <span class="rates-dot"></span>
      <span id="rates-note-text">{tr['prices_rate_note']} se încarcă...</span>
    </div>
  </div>
</div>
<script>
(function(){{
  fetch('https://open.er-api.com/v6/latest/USD')
    .then(r=>r.json())
    .then(d=>{{
      const mdl=d.rates&&d.rates.MDL||0;
      const eur=d.rates&&d.rates.EUR||0;
      if(!mdl||!eur)return;
      document.querySelectorAll('.price-mdl[data-usd]').forEach(el=>{{
        const v=parseFloat(el.dataset.usd);
        el.textContent=Math.round(v*mdl).toLocaleString('ro-MD')+' L';
      }});
      document.querySelectorAll('.price-eur[data-usd]').forEach(el=>{{
        const v=parseFloat(el.dataset.usd);
        el.textContent='€'+(v*eur).toLocaleString('de-DE',{{minimumFractionDigits:0,maximumFractionDigits:0}});
      }});
      const ts=new Date().toLocaleTimeString();
      document.getElementById('rates-note-text').textContent=
        '{tr["prices_rate_note"]} 1 USD = '+mdl.toFixed(2)+' MDL / '+eur.toFixed(4)+' EUR ('+ts+')';
    }})
    .catch(()=>{{
      document.getElementById('rates-note-text').textContent='Curs indisponibil momentan.';
    }});
}})();
</script>"""


# ── Analysis card ─────────────────────────────────────────────────────────────
def analysis_html(report, lang: str) -> str:
    tr = T[lang]
    bodies = ""
    for l in ("ro","ru","en"):
        text_val = getattr(report, f"ai_analysis_{l}") or ""
        body = (md.markdown(text_val, extensions=["nl2br","tables"])
                if text_val else "<p style='color:var(--text-3)'>—</p>")
        active = "active" if l == lang else ""
        bodies += f'<div class="lang-body {active} analysis-content" id="ab-{l}">{body}</div>'

    pills = "".join(
        f'<button class="lang-pill {"active" if l == lang else ""}" onclick="switchLang(\'{l}\')">{n}</button>'
        for l, n in LANG_NAMES.items()
    )

    # PDF tab
    has_pdf = bool(report.pdf_file)
    if has_pdf:
        pdf_url = f"/pdf/{report.vin}"
        pdf_content = f"""<div class="pdf-area">
          <div class="pdf-toolbar">
            <span class="pdf-vin">Carfax · {report.vin}</span>
            <a href="{pdf_url}" download="carfax_{report.vin}.pdf" class="pdf-cta">↓ &nbsp;{tr['btn_pdf']}</a>
          </div>
          <div class="pdf-frame-wrap">
            <iframe class="pdf-frame"
              src="{pdf_url}#toolbar=1&navpanes=0&scrollbar=1&view=FitH"
              title="Carfax {report.vin}"
              onload="this.nextElementSibling.style.display='none'"
              onerror="this.style.display='none';this.nextElementSibling.style.display='block'">
            </iframe>
            <div class="pdf-fallback">Browserul tău nu poate afișa PDF-ul direct.
              <a href="{pdf_url}" target="_blank">Deschide PDF →</a></div>
          </div></div>"""
    else:
        pdf_content = '<div class="pdf-area"><p style="color:var(--text-3);font-size:.9rem;padding:40px;text-align:center">PDF indisponibil.</p></div>'

    # BMW tab
    has_bmw = _bmw_has_real_data(getattr(report, "bmw_equipment", None))
    bmw_tab_btn  = ""
    bmw_tab_pane = ""
    if has_bmw:
        bmw_html = md.markdown(report.bmw_equipment, extensions=["nl2br","tables"])
        bmw_tab_btn  = f'<div class="tab" onclick="switchTab(\'bmw\',this)">{tr["tab_bmw"]}</div>'
        bmw_tab_pane = f'''<div class="tab-pane" id="tab-bmw">
    <div class="equip-meta">
      <a href="https://bimmer.work" target="_blank" rel="noopener">bimmer.work</a>
      <span class="equip-sep">·</span>
      <span style="color:var(--text-3)">VIN {report.vin}</span>
    </div>
    <div class="analysis-content">{bmw_html}</div>
  </div>'''

    # Pricing tab
    has_prices = _has_prices(report)
    price_tab_btn  = ""
    price_tab_pane = ""
    if has_prices:
        price_tab_btn  = f'<div class="tab" onclick="switchTab(\'prices\',this)">{tr["tab_prices"]}</div>'
        price_tab_pane = pricing_tab_html(report, lang)

    # Client badge
    client_name  = getattr(report, "client_name",  None) or ""
    client_phone = getattr(report, "client_phone", None) or ""
    client_badge = ""
    if client_name or client_phone:
        label = f"{client_name} · {client_phone}" if client_name and client_phone else (client_name or client_phone)
        client_badge = f'<span class="client-badge">👤 {label}</span>'

    return f"""
<div class="card">
  <div class="card-top">
    <span class="card-top-title">{tr['vin_label']}</span>
    <span class="vin-tag" title="Click to copy" onclick="copyVin(this,'{report.vin}')">{report.vin}</span>
    {client_badge}
  </div>
  <div class="tabs">
    <div class="tab active" onclick="switchTab('analysis',this)">{tr['tab_analysis']}</div>
    <div class="tab" onclick="switchTab('pdf',this)">{tr['tab_pdf']}</div>
    {bmw_tab_btn}
    {price_tab_btn}
  </div>
  <div class="tab-pane active" id="tab-analysis">
    <div class="lang-pills">{pills}</div>
    {bodies}
  </div>
  <div class="tab-pane" id="tab-pdf">{pdf_content}</div>
  {bmw_tab_pane}
  {price_tab_pane}
</div>"""


# ── Not-found card ────────────────────────────────────────────────────────────
def not_found_html(vin: str, lang: str) -> str:
    tr = T[lang]
    return f"""<div class="card"><div class="not-found">
    <div class="nf-icon">🔍</div>
    <h2>{tr['not_found_title']}</h2>
    <p>{tr['not_found_body'].format(vin=vin)}</p>
    <p>{tr['not_found_cta']}</p>
    <a href="https://t.me/fedukusa" target="_blank" class="tg-btn">✈️ &nbsp;{tr['contact_btn']}</a>
  </div></div>"""


# ── Admin HTML builders ───────────────────────────────────────────────────────
def admin_shell(content: str, active: str = "") -> str:
    nav_items = [
        ("/admin",       "dashboard", "📊 Dashboard"),
        ("/admin/cars",  "cars",      "🚗 Mașini"),
    ]
    nav = "".join(
        f'<a href="{url}" class="admin-nav-item {"active" if key==active else ""}">{label}</a>'
        for url, key, label in nav_items
    )
    return f"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Feduk USA — Admin</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON_URI}"/>
<style>{CSS}</style>
</head>
<body>
<header>
  <a href="/" class="logo">
    <div class="logo-icon">FU</div>
    <div><span class="logo-name">FEDUK USA</span><span class="logo-sub">Admin Panel</span></div>
  </a>
  <div class="header-right">
    <a href="/" class="admin-header-btn">← Site</a>
    <a href="/admin/logout" class="admin-header-btn">Logout</a>
  </div>
</header>
<nav class="admin-nav">{nav}</nav>
<div class="admin-main">{content}</div>
<footer style="border-top:1px solid var(--border);padding:18px 24px;text-align:center;font-size:.75rem;color:var(--text-3)">
  © 2026 <span style="color:var(--red)">Feduk USA</span> · Admin Panel
</footer>
</body>
</html>"""


def admin_login_page(error: str = "") -> str:
    err_html = f'<div class="admin-login-err">{error}</div>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Feduk USA — Login Admin</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON_URI}"/>
<style>{CSS}</style>
</head>
<body>
<header>
  <a href="/" class="logo">
    <div class="logo-icon">FU</div>
    <div><span class="logo-name">FEDUK USA</span><span class="logo-sub">Admin Login</span></div>
  </a>
</header>
<div class="admin-login-wrap">
  <div class="card" style="padding:32px">
    <div class="admin-login-title">Autentificare Admin</div>
    <div class="admin-login-sub">Acces restricționat — doar personal autorizat</div>
    {err_html}
    <form method="post" style="display:flex;flex-direction:column;gap:16px">
      <div class="form-group">
        <label class="form-label">Utilizator</label>
        <input name="username" class="form-input" type="text" autocomplete="username" required/>
      </div>
      <div class="form-group">
        <label class="form-label">Parolă</label>
        <input name="password" class="form-input" type="password" autocomplete="current-password" required/>
      </div>
      <button type="submit" class="btn-primary">Intră în admin →</button>
    </form>
  </div>
</div>
</body>
</html>"""


def admin_dashboard_html(stats: dict, recent: list) -> str:
    rows = ""
    for r in recent:
        proc = ('<span class="badge badge-green">Procurat</span>'
                if getattr(r, "is_procured", False)
                else '<span class="badge badge-gray">—</span>')
        client = getattr(r, "client_name", None) or "—"
        phone  = getattr(r, "client_phone", None) or "—"
        dt     = r.created_at.strftime("%d.%m.%Y") if r.created_at else "—"
        rows += f"""<tr>
          <td><a href="/admin/car/{r.vin}">{r.vin}</a></td>
          <td>{client}</td><td>{phone}</td>
          <td>{proc}</td><td>{dt}</td>
          <td><a href="/admin/car/{r.vin}" style="color:var(--red);font-size:.8rem">Edit →</a></td>
        </tr>"""

    content = f"""
<div class="stat-grid">
  <div class="stat-card">
    <div class="stat-label">Total analize</div>
    <div class="stat-value">{stats['total']}</div>
    <div class="stat-sub">rapoarte în sistem</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Procurate</div>
    <div class="stat-value" style="color:var(--green)">{stats['procured']}</div>
    <div class="stat-sub">mașini cumpărate</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Clienți unici</div>
    <div class="stat-value" style="color:var(--amber)">{stats['clients']}</div>
    <div class="stat-sub">numere de telefon</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Cu prețuri</div>
    <div class="stat-value" style="color:var(--blue)">{stats['priced']}</div>
    <div class="stat-sub">oferte complete</div>
  </div>
</div>
<div class="section-header">
  <span class="section-title">Ultimele 15 mașini</span>
  <a href="/admin/cars" class="btn-secondary" style="font-size:.82rem;padding:7px 16px">Vezi toate →</a>
</div>
<div class="card" style="overflow:auto">
  <table class="data-table">
    <thead><tr><th>VIN</th><th>Client</th><th>Telefon</th><th>Status</th><th>Data</th><th></th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
    return admin_shell(content, "dashboard")


def admin_cars_html(cars: list, filter_val: str, q: str) -> str:
    rows = ""
    for r in cars:
        proc = ('<span class="badge badge-green">Procurat</span>'
                if getattr(r, "is_procured", False)
                else '<span class="badge badge-gray">Neprocu­rat</span>')
        client = getattr(r, "client_name", None) or "—"
        phone  = getattr(r, "client_phone", None) or "—"
        code   = getattr(r, "client_code",  None) or "—"
        dt     = r.created_at.strftime("%d.%m.%Y") if r.created_at else "—"
        has_p  = _has_prices(r)
        price_badge = '<span class="badge badge-amber" style="margin-left:4px">$</span>' if has_p else ""
        rows += f"""<tr>
          <td><a href="/admin/car/{r.vin}">{r.vin}</a></td>
          <td>{client}</td><td>{phone}</td><td>{code}</td>
          <td>{proc}{price_badge}</td><td>{dt}</td>
          <td style="display:flex;gap:8px;flex-wrap:wrap">
            <a href="/admin/car/{r.vin}" style="color:var(--red);font-size:.8rem;font-weight:600">Edit →</a>
            <a href="/search?vin={r.vin}" target="_blank" style="color:var(--text-3);font-size:.78rem">View</a>
          </td>
        </tr>"""

    content = f"""
<div class="section-header">
  <span class="section-title">Toate mașinile ({len(cars)})</span>
  <form method="get" action="/admin/cars" class="filter-bar">
    <input name="q" class="filter-input" placeholder="Caută VIN / client / tel..."
           value="{q}" style="width:220px"/>
    <select name="f" class="filter-select" onchange="this.form.submit()">
      <option value="all"   {'selected' if filter_val=='all'      else ''}>Toate</option>
      <option value="proc"  {'selected' if filter_val=='proc'     else ''}>Procurate</option>
      <option value="noproc"{'selected' if filter_val=='noproc'   else ''}>Neprocurate</option>
      <option value="client"{'selected' if filter_val=='client'   else ''}>Cu client</option>
      <option value="priced"{'selected' if filter_val=='priced'   else ''}>Cu prețuri</option>
    </select>
    <button type="submit" class="btn-primary" style="padding:7px 18px;font-size:.82rem">Filtrează</button>
  </form>
</div>
<div class="card" style="overflow-x:auto">
  <table class="data-table">
    <thead><tr><th>VIN</th><th>Client</th><th>Telefon</th><th>Cod</th><th>Status</th><th>Data</th><th></th></tr></thead>
    <tbody>{rows if rows else '<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-3)">Niciun rezultat</td></tr>'}</tbody>
  </table>
</div>"""
    return admin_shell(content, "cars")


def admin_car_edit_html(report, saved: bool = False, error: str = "") -> str:
    def v(attr, default=""):
        val = getattr(report, attr, None)
        return str(val) if val not in (None, "") else default

    def checked(attr):
        return "checked" if getattr(report, attr, False) else ""

    def price_field(col: str, label: str) -> str:
        val = getattr(report, f"price_{col}_usd", None)
        val_str = str(float(val)) if val else ""
        return f"""<div class="form-group">
          <label class="form-label">{label}</label>
          <input name="price_{col}_usd" class="form-input" type="number" step="0.01" min="0"
                 placeholder="0.00" value="{val_str}"/>
        </div>"""

    saved_banner = ('<div style="background:rgba(34,197,94,.1);border:1px solid rgba(34,197,94,.25);'
                    'color:#22c55e;border-radius:8px;padding:10px 14px;font-size:.85rem;margin-bottom:16px">'
                    '✅ Salvat cu succes!</div>') if saved else ""
    err_banner = (f'<div style="background:rgba(220,38,38,.1);border:1px solid rgba(220,38,38,.25);'
                  f'color:#f87171;border-radius:8px;padding:10px 14px;font-size:.85rem;margin-bottom:16px">'
                  f'⚠️ {error}</div>') if error else ""

    client_code_val = v("client_code")

    content = f"""
<div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;flex-wrap:wrap">
  <a href="/admin/cars" class="btn-secondary" style="font-size:.82rem;padding:7px 16px">← Lista mașini</a>
  <a href="/search?vin={report.vin}" target="_blank" class="btn-secondary" style="font-size:.82rem;padding:7px 16px">🔗 Vizualizare publică</a>
  <span style="font-family:var(--mono);font-size:.85rem;color:var(--text-3)">{report.vin}</span>
</div>
{saved_banner}{err_banner}
<form method="post" class="admin-form">
  <div class="form-section">
    <div class="form-section-title">👤 Informații Client</div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Nume client</label>
        <input name="client_name" class="form-input" type="text"
               placeholder="ex: Ion Popescu" value="{v('client_name')}"
               oninput="updateCode()"/>
        <span class="form-hint">Numele complet al clientului</span>
      </div>
      <div class="form-group">
        <label class="form-label">Număr telefon</label>
        <input name="client_phone" class="form-input" type="tel"
               placeholder="ex: 069123456" value="{v('client_phone')}"
               oninput="updateCode()"/>
        <span class="form-hint">Numărul după care clientul poate căuta</span>
      </div>
    </div>
    <div class="form-group" style="margin-top:8px">
      <label class="form-label">Cod client (auto-generat)</label>
      <span class="code-preview" id="code-preview">{client_code_val or '—'}</span>
      <input type="hidden" name="client_code" id="client_code_input" value="{client_code_val}"/>
    </div>
  </div>

  <div class="form-section">
    <div class="form-section-title">🚗 Status Procurare</div>
    <label class="form-check" style="margin-bottom:16px">
      <input type="checkbox" name="is_procured" value="1" {checked('is_procured')}
             onchange="togglePrices(this.checked)"/>
      <span>Mașina a fost <strong>procurată</strong> (cumpărată la licitație)</span>
    </label>
    <div id="prices-section" style="display:{'block' if getattr(report,'is_procured',False) else 'none'}">
      <div style="font-size:.78rem;font-weight:600;letter-spacing:.06em;color:var(--text-3);margin-bottom:14px;text-transform:uppercase">Defalcare prețuri (în USD)</div>
      <div class="form-row">
        {price_field('car',      '🚗 Preț mașină')}
        {price_field('auction',  '🔨 Taxă licitație')}
      </div>
      <div class="form-row">
        {price_field('transfer', '📋 Comision transfer')}
        {price_field('shipping', '🚢 Transport SUA → Moldova')}
      </div>
      <div class="form-row">
        {price_field('customs',  '🛃 Devamare')}
        {price_field('broker',   '👨‍⚖️ Broker vamal')}
      </div>
    </div>
  </div>

  <div class="form-section">
    <div class="form-section-title">📝 Note Admin</div>
    <div class="form-group">
      <label class="form-label">Note interne (nu sunt vizibile publicului)</label>
      <textarea name="admin_notes" class="form-textarea" rows="4"
                placeholder="Observații, detalii negociere, etc.">{v('admin_notes')}</textarea>
    </div>
  </div>

  <div class="btn-row">
    <button type="submit" class="btn-primary">💾 Salvează</button>
    <a href="/admin/cars" class="btn-secondary">Anulează</a>
    <button type="button" class="btn-danger" onclick="confirmDelete('{report.vin}')">🗑 Șterge înregistrarea</button>
  </div>
</form>

<form id="delete-form" method="post" action="/admin/car/{report.vin}/delete" style="display:none"></form>

<script>
function togglePrices(on){{
  document.getElementById('prices-section').style.display=on?'block':'none';
}}
function updateCode(){{
  const name=(document.querySelector('[name=client_name]').value||'').trim().toUpperCase().replace(/\\s+/g,'_');
  const phone=(document.querySelector('[name=client_phone]').value||'').replace(/\\D/g,'');
  const last4=phone.slice(-4);
  const code=name&&last4?name+'-'+last4:(name||last4||'—');
  document.getElementById('code-preview').textContent=code;
  document.getElementById('client_code_input').value=code==='—'?'':code;
}}
function confirmDelete(vin){{
  if(confirm('Ești sigur că vrei să ștergi înregistrarea pentru '+vin+'? Această acțiune este ireversibilă!')){{
    document.getElementById('delete-form').submit();
  }}
}}
</script>"""
    return admin_shell(content, "cars")


# ── Public routes ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, lang: str = "ro"):
    lang = lang if lang in T else "ro"
    token = request.cookies.get(ADMIN_COOKIE)
    return HTMLResponse(html_shell("", lang, is_admin=_valid_session(token)))


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, vin: str = "", phone: str = "",
                 mode: str = "vin", lang: str = "ro"):
    lang  = lang if lang in T else "ro"
    vin   = vin.strip().upper()
    phone = phone.strip()
    token = request.cookies.get(ADMIN_COOKIE)
    is_admin = _valid_session(token)
    tr = T[lang]

    # ── Phone search ──────────────────────────────────────────────────────
    if mode == "phone" or (phone and not vin):
        if not phone:
            return HTMLResponse(html_shell("", lang, phone=phone, search_mode="phone", is_admin=is_admin))
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 7:
            err = f'<p class="error-msg">{tr["error_phone"]}</p>'
            return HTMLResponse(html_shell(err, lang, phone=phone, search_mode="phone", is_admin=is_admin))

        async with AsyncSessionLocal() as session:
            from database import CarfaxReport
            results = (await session.scalars(
                select(CarfaxReport).where(
                    CarfaxReport.client_phone.ilike(f"%{digits[-7:]}%")
                ).order_by(CarfaxReport.created_at.desc())
            )).all()

        if not results:
            content = f"""<div class="card"><div class="not-found">
              <div class="nf-icon">📱</div>
              <h2>{tr['phone_not_found_title']}</h2>
              <p>{tr['phone_not_found_body'].format(phone=phone)}</p>
              <p>{tr['not_found_cta']}</p>
              <a href="https://t.me/fedukusa" target="_blank" class="tg-btn">✈️ &nbsp;{tr['contact_btn']}</a>
            </div></div>"""
            return HTMLResponse(html_shell(content, lang, phone=phone, search_mode="phone", is_admin=is_admin))

        if len(results) == 1:
            return RedirectResponse(url=f"/search?vin={results[0].vin}&lang={lang}", status_code=303)

        # Multiple cars — show selection
        items = ""
        for r in results:
            make_info = ""
            if r.ai_analysis_ro:
                first_line = r.ai_analysis_ro.split("\n")[0][:80]
                make_info = first_line.replace("#","").strip()
            proc_badge = ' <span class="badge badge-green" style="font-size:.65rem">✓ Procurat</span>' if getattr(r,"is_procured",False) else ""
            items += f"""<a href="/search?vin={r.vin}&lang={lang}" class="car-list-item">
              <div class="car-list-info">
                <span class="car-list-name">{make_info or r.vin}{proc_badge}</span>
                <span class="car-list-vin">VIN: {r.vin}</span>
              </div>
              <span class="car-list-arrow">→</span>
            </a>"""

        content = f"""<div class="card">
          <div class="card-top">
            <span class="card-top-title">{tr['phone_select_title']}</span>
          </div>
          <div class="tab-pane active">
            <p style="color:var(--text-2);font-size:.9rem;margin-bottom:16px">
              {tr['phone_select_body'].format(n=len(results), phone=phone)}
            </p>
            <div class="car-list">{items}</div>
          </div>
        </div>"""
        return HTMLResponse(html_shell(content, lang, phone=phone, search_mode="phone", is_admin=is_admin))

    # ── VIN search ────────────────────────────────────────────────────────
    if not vin:
        return HTMLResponse(html_shell("", lang, is_admin=is_admin))
    if not VIN_RE.match(vin):
        err = f'<p class="error-msg">{tr["error_vin"]}</p>'
        return HTMLResponse(html_shell(err, lang, vin=vin, is_admin=is_admin))

    async with AsyncSessionLocal() as session:
        from database import CarfaxReport
        result = await session.scalar(select(CarfaxReport).where(CarfaxReport.vin == vin))

    content = analysis_html(result, lang) if result else not_found_html(vin, lang)
    return HTMLResponse(html_shell(content, lang, vin=vin, is_admin=is_admin))


@app.get("/pdf/{vin}")
async def serve_pdf(vin: str):
    vin = vin.strip().upper()
    async with AsyncSessionLocal() as session:
        from database import CarfaxReport
        result = await session.scalar(select(CarfaxReport).where(CarfaxReport.vin == vin))
    if not result or not result.pdf_file:
        return Response(content="PDF not found", status_code=404)
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
    return RedirectResponse(url=f"/search?vin={vin}&lang={lang}", status_code=303)


@app.get("/bmw/{vin}", response_class=HTMLResponse)
async def bmw_equipment(vin: str, lang: str = "ro"):
    # Legacy route — redirect to main search page
    return RedirectResponse(url=f"/search?vin={vin}&lang={lang}", status_code=301)


@app.get("/debug/bmw/{vin}")
async def debug_bmw(vin: str):
    vin = vin.strip().upper()
    try:
        from bmw_lookup import fetch_bimmer_equipment
        result = await fetch_bimmer_equipment(vin)
        return JSONResponse({
            "vin": vin,
            "found": result.found,
            "page_url": result.page_url,
            "error": result.error,
            "text_length": len(result.raw_html_text),
            "text_preview": result.raw_html_text[:800] if result.raw_html_text else "",
        })
    except Exception as exc:
        return JSONResponse({"vin": vin, "exception": str(exc),
                             "traceback": traceback.format_exc()}, status_code=500)


# ── Admin routes ──────────────────────────────────────────────────────────────
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_get(request: Request):
    if _valid_session(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse("/admin", status_code=303)
    return HTMLResponse(admin_login_page())


@app.post("/admin/login")
async def admin_login_post(
    username: str = Form(...),
    password: str = Form(...),
):
    if username == ADMIN_USER and password == ADMIN_PASS:
        token = _create_session()
        resp  = RedirectResponse("/admin", status_code=303)
        resp.set_cookie(ADMIN_COOKIE, token, httponly=True, samesite="lax", max_age=28800)
        return resp
    return HTMLResponse(admin_login_page(error="Credențiale incorecte. Încearcă din nou."))


@app.get("/admin/logout")
async def admin_logout(request: Request):
    token = request.cookies.get(ADMIN_COOKIE)
    _sessions.pop(token, None)
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not _valid_session(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse("/admin/login", status_code=303)

    from database import CarfaxReport
    async with AsyncSessionLocal() as session:
        total    = await session.scalar(func.count(CarfaxReport.id)) or 0
        procured = await session.scalar(
            func.count(CarfaxReport.id).filter(CarfaxReport.is_procured == True)) or 0
        clients  = await session.scalar(
            func.count(func.distinct(CarfaxReport.client_phone)).filter(
                CarfaxReport.client_phone.isnot(None))) or 0
        priced   = await session.scalar(
            func.count(CarfaxReport.id).filter(
                CarfaxReport.is_procured == True,
                CarfaxReport.price_car_usd.isnot(None))) or 0
        recent   = (await session.scalars(
            select(CarfaxReport).order_by(CarfaxReport.created_at.desc()).limit(15)
        )).all()

    stats = {"total": total, "procured": procured, "clients": clients, "priced": priced}
    return HTMLResponse(admin_dashboard_html(stats, recent))


@app.get("/admin/cars", response_class=HTMLResponse)
async def admin_cars(request: Request, f: str = "all", q: str = ""):
    if not _valid_session(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse("/admin/login", status_code=303)

    from database import CarfaxReport
    async with AsyncSessionLocal() as session:
        stmt = select(CarfaxReport)
        if f == "proc":
            stmt = stmt.where(CarfaxReport.is_procured == True)
        elif f == "noproc":
            stmt = stmt.where(CarfaxReport.is_procured == False)
        elif f == "client":
            stmt = stmt.where(CarfaxReport.client_phone.isnot(None))
        elif f == "priced":
            stmt = stmt.where(CarfaxReport.is_procured == True,
                               CarfaxReport.price_car_usd.isnot(None))
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(
                CarfaxReport.vin.ilike(like),
                CarfaxReport.client_name.ilike(like),
                CarfaxReport.client_phone.ilike(like),
                CarfaxReport.client_code.ilike(like),
            ))
        stmt  = stmt.order_by(CarfaxReport.created_at.desc())
        cars  = (await session.scalars(stmt)).all()

    return HTMLResponse(admin_cars_html(cars, f, q))


@app.get("/admin/car/{vin}", response_class=HTMLResponse)
async def admin_car_get(vin: str, request: Request, saved: str = ""):
    if not _valid_session(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse("/admin/login", status_code=303)
    vin = vin.strip().upper()
    from database import CarfaxReport
    async with AsyncSessionLocal() as session:
        record = await session.scalar(select(CarfaxReport).where(CarfaxReport.vin == vin))
    if not record:
        return RedirectResponse("/admin/cars", status_code=303)
    return HTMLResponse(admin_car_edit_html(record, saved=saved == "1"))


@app.post("/admin/car/{vin}")
async def admin_car_post(
    vin: str, request: Request,
    client_name:    str = Form(default=""),
    client_phone:   str = Form(default=""),
    client_code:    str = Form(default=""),
    is_procured:    str = Form(default=""),
    price_car_usd:      str = Form(default=""),
    price_auction_usd:  str = Form(default=""),
    price_transfer_usd: str = Form(default=""),
    price_shipping_usd: str = Form(default=""),
    price_customs_usd:  str = Form(default=""),
    price_broker_usd:   str = Form(default=""),
    admin_notes:    str = Form(default=""),
):
    if not _valid_session(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse("/admin/login", status_code=303)
    vin = vin.strip().upper()
    from database import CarfaxReport
    from decimal import Decimal, InvalidOperation

    def to_dec(s: str):
        s = s.strip()
        try:
            return Decimal(s) if s else None
        except InvalidOperation:
            return None

    procured = is_procured == "1"

    # Auto-generate client_code if name+phone provided but no code given
    if not client_code.strip() and client_name.strip():
        digits = re.sub(r"\D", "", client_phone)
        last4  = digits[-4:] if len(digits) >= 4 else digits
        code   = client_name.strip().upper().replace(" ", "_")
        client_code = f"{code}-{last4}" if last4 else code

    async with AsyncSessionLocal() as session:
        record = await session.scalar(select(CarfaxReport).where(CarfaxReport.vin == vin))
        if not record:
            return RedirectResponse("/admin/cars", status_code=303)
        record.client_name        = client_name.strip()   or None
        record.client_phone       = client_phone.strip()  or None
        record.client_code        = client_code.strip()   or None
        record.is_procured        = procured
        record.price_car_usd      = to_dec(price_car_usd)      if procured else None
        record.price_auction_usd  = to_dec(price_auction_usd)  if procured else None
        record.price_transfer_usd = to_dec(price_transfer_usd) if procured else None
        record.price_shipping_usd = to_dec(price_shipping_usd) if procured else None
        record.price_customs_usd  = to_dec(price_customs_usd)  if procured else None
        record.price_broker_usd   = to_dec(price_broker_usd)   if procured else None
        record.admin_notes        = admin_notes.strip()   or None
        await session.commit()

    return RedirectResponse(f"/admin/car/{vin}?saved=1", status_code=303)


@app.post("/admin/car/{vin}/delete")
async def admin_car_delete(vin: str, request: Request):
    if not _valid_session(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse("/admin/login", status_code=303)
    vin = vin.strip().upper()
    from database import CarfaxReport
    async with AsyncSessionLocal() as session:
        record = await session.scalar(select(CarfaxReport).where(CarfaxReport.vin == vin))
        if record:
            await session.delete(record)
            await session.commit()
    return RedirectResponse("/admin/cars", status_code=303)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("webapp:app", host="0.0.0.0", port=port, log_level="info")
