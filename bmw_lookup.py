"""
BMW equipment lookup via bimmer.work (headless browser).
Only runs when the vehicle make contains 'BMW', 'MINI', 'ALPINA', or 'Rolls'.

Confirmed via network analysis:
  - Form: POST https://bimmer.work/query.php  field: vin=<VIN>
  - Success URL pattern: https://bimmer.work/vin/<hash>/
  - Rate-limit URL:      https://bimmer.work/429/
"""
import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

BMW_BRANDS   = {"bmw", "mini", "alpina", "rolls-royce", "rolls royce"}
BIMMER_HOME  = "https://bimmer.work/"
_CHROME_UA   = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def is_bmw(make: str) -> bool:
    return any(b in make.lower() for b in BMW_BRANDS)


@dataclass
class BMWEquipmentResult:
    found:         bool = False
    vin:           str  = ""
    page_url:      str  = ""
    raw_html_text: str  = ""
    error:         str  = ""


async def fetch_bimmer_equipment(vin: str) -> BMWEquipmentResult:
    """
    Submit VIN to bimmer.work and return all visible text from the results page.
    Automatically retries once after 8 s on a 429 rate-limit response.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed. Add 'playwright' to requirements.txt")
        return BMWEquipmentResult(found=False, vin=vin, error="playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"],
        )
        # Use a real Chrome UA to reduce bot-detection / 429s
        context = await browser.new_context(user_agent=_CHROME_UA)
        page    = await context.new_page()
        try:
            result = await _do_fetch(page, vin)
            if not result.found and "429" in result.error:
                logger.info("429 on first attempt for VIN %s — waiting 8 s then retrying", vin)
                await asyncio.sleep(8)
                result = await _do_fetch(page, vin)
            return result
        except Exception as exc:
            logger.exception("bimmer.work fetch error for VIN %s", vin)
            return BMWEquipmentResult(found=False, vin=vin, error=str(exc))
        finally:
            await browser.close()


async def _do_fetch(page, vin: str) -> BMWEquipmentResult:
    from playwright.async_api import TimeoutError as PWTimeout

    try:
        logger.info("🔍 Opening bimmer.work for VIN %s", vin)
        await page.goto(BIMMER_HOME, timeout=30_000, wait_until="domcontentloaded")

        # Wait for the VIN input (known exact selector from DOM analysis)
        await page.wait_for_selector("input#vin", timeout=10_000)

        # Brief pause — lets any JS/reCAPTCHA initialise
        await asyncio.sleep(1.5)

        # Fill + submit using confirmed selectors
        await page.fill("input#vin", vin)
        await page.click('button[type="submit"]')

        # Wait for the page to navigate away from the homepage
        await page.wait_for_url(
            lambda url: url.rstrip("/") != BIMMER_HOME.rstrip("/"),
            timeout=20_000,
        )

        final_url = page.url
        logger.info("bimmer.work navigated to: %s", final_url)

        # Detect rate-limit page
        if "/429" in final_url:
            logger.warning("bimmer.work 429 rate-limit for VIN %s", vin)
            return BMWEquipmentResult(found=False, vin=vin, error="429 rate limited")

        # Wait for remaining content to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            pass  # partial content is still usable

        # Extract all visible text, stripping noise
        text = await page.evaluate("""() => {
            ['script','style','noscript','iframe'].forEach(tag =>
                document.querySelectorAll(tag).forEach(el => el.remove())
            );
            return document.body.innerText;
        }""")

        if not text or len(text.strip()) < 100:
            return BMWEquipmentResult(found=False, vin=vin, error="empty page response")

        # Secondary check: error keywords in first 1 000 chars
        low = text[:1000].lower()
        if any(k in low for k in ("429", "too many requests", "rate limit",
                                   "cloudflare", "access denied", "403 forbidden")):
            logger.warning("bimmer.work returned error/rate-limit page for VIN %s", vin)
            return BMWEquipmentResult(found=False, vin=vin, error="429 rate limited")

        logger.info("✅ bimmer.work returned %d chars for VIN %s", len(text), vin)
        return BMWEquipmentResult(
            found=True,
            vin=vin,
            page_url=final_url,
            raw_html_text=text.strip()[:15_000],
        )

    except PWTimeout:
        logger.warning("Timeout fetching bimmer.work for VIN %s", vin)
        return BMWEquipmentResult(found=False, vin=vin, error="timeout")
