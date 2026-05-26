from pathlib import Path

from playwright.async_api import Browser, Playwright, async_playwright

from app.core.config import settings


class BrowserPool:
    """Keeps browser processes warm so repeated test runs avoid launch latency."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browsers: dict[str, Browser] = {}

    async def _ensure_playwright(self) -> Playwright:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def get_browser(self, browser_name: str, headless: bool | None = None) -> Browser:
        headless_value = settings.BROWSER_HEADLESS if headless is None else headless
        key = f"{browser_name}:{headless_value}"
        existing = self._browsers.get(key)
        if existing and existing.is_connected():
            return existing

        playwright = await self._ensure_playwright()
        launcher = getattr(playwright, browser_name)
        browser = await launcher.launch(
            headless=headless_value,
            slow_mo=settings.SLOW_MO_MS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        self._browsers[key] = browser
        return browser

    async def new_context(
        self,
        browser_name: str,
        headless: bool | None,
        storage_state_path: str | None = None,
    ):
        browser = await self.get_browser(browser_name, headless)
        storage_state = str(Path(storage_state_path)) if storage_state_path else None
        return await browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1440, "height": 980},
            ignore_https_errors=True,
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
        )

    async def close(self) -> None:
        for browser in list(self._browsers.values()):
            if browser.is_connected():
                await browser.close()
        self._browsers.clear()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


browser_pool = BrowserPool()
