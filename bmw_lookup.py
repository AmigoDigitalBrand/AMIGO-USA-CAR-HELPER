"""
BMW equipment lookup via bimmer.work (headless browser).
Only runs when the vehicle make contains 'BMW', 'MINI', 'ALPINA', or 'Rolls'.
"""
import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

BMW_BRANDS = {"bmw", "mini", "alpina", "rolls-royce", "rolls royce"}
BIMMER_URL = "https://bimmer.work/"


def is_bmw(make: str) -> bool:
    return any(b in make.lower() for b in BMW_BRANDS)


@dataclass
class BMWEquipmentResult:
    found: bool = False
    vin: str = ""
    page_url: str = ""          # final URL after form submit
    raw_html_text: str = ""     # visible text scraped from results page
    error: str = ""


async def fetch_bimmer_equipment(vin: str) -> BMWEquipmentResult:
    """
    Use Playwright to submit the VIN on bimmer.work and return
    all visible text from the results page.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("Playwright not installed. Add 'playwright' to requirements.txt")
        return BMWEquipmentResult(found=False, vin=vin, error="playwright not installed")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"],
        )
        page = await browser.new_page()
        try:
            logger.info("🔍 Opening bimmer.work for VIN %s", vin)
            await page.goto(BIMMER_URL, timeout=30_000, wait_until="domcontentloaded")

            # Fill VIN input — try common selectors
            for selector in ['input[name="vin"]', 'input[type="text"]',
                              'input[placeholder*="VIN"]', 'input[id*="vin"]', 'input']:
                try:
                    await page.fill(selector, vin, timeout=3_000)
                    logger.info("Filled VIN using selector: %s", selector)
                    break
                except Exception:
                    continue

            # Submit the form
            for selector in ['button[type="submit"]', 'input[type="submit"]',
                              'button:has-text("Submit")', 'button:has-text("Decode")',
                              'button:has-text("Search")', 'form button']:
                try:
                    await page.click(selector, timeout=3_000)
                    logger.info("Clicked submit using selector: %s", selector)
                    break
                except Exception:
                    continue

            # Wait for results to load
            await page.wait_for_load_state("networkidle", timeout=20_000)
            final_url = page.url

            # Extract all visible text
            text = await page.evaluate("""() => {
                // Remove script, style, nav, footer noise
                ['script','style','noscript'].forEach(tag =>
                    document.querySelectorAll(tag).forEach(el => el.remove())
                );
                return document.body.innerText;
            }""")

            if not text or len(text.strip()) < 100:
                return BMWEquipmentResult(found=False, vin=vin, error="empty page response")

            # Detect rate-limit / error pages before passing to Gemini
            text_lower = text[:1000].lower()
            if any(k in text_lower for k in ("429", "too many requests", "rate limit", "cloudflare", "access denied", "403 forbidden")):
                logger.warning("bimmer.work returned error page for VIN %s (rate limited?)", vin)
                return BMWEquipmentResult(found=False, vin=vin, error="rate limited or access denied")

            logger.info("✅ bimmer.work returned %d chars for VIN %s", len(text), vin)
            return BMWEquipmentResult(
                found=True,
                vin=vin,
                page_url=final_url,
                raw_html_text=text.strip()[:15_000],  # cap at 15k chars for Gemini
            )

        except PWTimeout:
            logger.warning("Timeout fetching bimmer.work for VIN %s", vin)
            return BMWEquipmentResult(found=False, vin=vin, error="timeout")
        except Exception as exc:
            logger.exception("bimmer.work fetch error for VIN %s", vin)
            return BMWEquipmentResult(found=False, vin=vin, error=str(exc))
        finally:
            await browser.close()
