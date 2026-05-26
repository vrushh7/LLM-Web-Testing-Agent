from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin

from playwright.async_api import BrowserContext, Page

from app.automation.browser_pool import browser_pool
from app.automation.locators import resolve_locator
from app.core.config import settings
from app.schemas.test import TestStep


@dataclass
class EngineOptions:
    run_id: str
    browser: str
    headless: bool | None
    session_state_path: str | None
    save_session_path: str | None
    max_retries: int


@dataclass
class StepRunResult:
    step_index: int
    action: str
    target: str | None
    value: Any | None
    status: str
    message: str
    screenshot_path: str | None
    duration_ms: int
    started_at: datetime
    ended_at: datetime


LogCallback = Callable[[str, dict[str, Any] | None], Awaitable[None]]
StepCallback = Callable[[StepRunResult], Awaitable[None]]


class PlaywrightEngine:
    """Interprets structured JSON steps with Playwright instead of executing AI code."""

    def __init__(self, on_log: LogCallback, on_step: StepCallback) -> None:
        self.on_log = on_log
        self.on_step = on_step

    async def execute(self, steps: list[TestStep], options: EngineOptions) -> tuple[int, int]:
        default_timeout = (
            settings.PRODUCTION_TIMEOUT_MS if settings.ENV == "production" else settings.DEFAULT_TIMEOUT_MS
        )
        context = await browser_pool.new_context(
            browser_name=options.browser,
            headless=options.headless,
            storage_state_path=options.session_state_path,
        )
        page = await context.new_page()
        page.set_default_timeout(default_timeout)

        passed = 0
        failed = 0
        try:
            for index, step in enumerate(steps, start=1):
                await self.on_log(
                    f"Step {index}: {step.action.value}",
                    {"step_index": index, "step": step.model_dump(mode="json")},
                )
                result = await self._run_step_with_retries(page, step, index, options)
                await self.on_step(result)
                if result.status == "passed":
                    passed += 1
                else:
                    failed += 1
                    break

            if options.save_session_path:
                await self._save_storage_state(context, options.save_session_path)
                await self.on_log("Saved browser session state", {"path": options.save_session_path})
        finally:
            await context.close()

        return passed, failed

    async def _run_step_with_retries(
        self,
        page: Page,
        step: TestStep,
        index: int,
        options: EngineOptions,
    ) -> StepRunResult:
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        screenshot_path: str | None = None
        last_error: Exception | None = None

        for attempt in range(options.max_retries + 1):
            try:
                if attempt:
                    await self.on_log(f"Retrying step {index} (attempt {attempt + 1})", None)
                    await page.wait_for_timeout(600)
                message, screenshot_path = await self._execute_action(page, step, options.run_id, index)
                if settings.EVIDENCE_SCREENSHOTS and screenshot_path is None:
                    screenshot_path = await self._screenshot(page, options.run_id, index, "evidence")
                message = await self._with_page_evidence(page, message)
                ended_at = datetime.now(timezone.utc)
                return StepRunResult(
                    step_index=index,
                    action=step.action.value,
                    target=step.target,
                    value=step.value,
                    status="passed",
                    message=message,
                    screenshot_path=screenshot_path,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    started_at=started_at,
                    ended_at=ended_at,
                )
            except Exception as exc:
                last_error = exc

        screenshot_path = await self._capture_failure(page, options.run_id, index)
        ended_at = datetime.now(timezone.utc)
        return StepRunResult(
            step_index=index,
            action=step.action.value,
            target=step.target,
            value=step.value,
            status="failed",
            message=str(last_error),
            screenshot_path=screenshot_path,
            duration_ms=int((time.perf_counter() - started) * 1000),
            started_at=started_at,
            ended_at=ended_at,
        )

    async def _execute_action(self, page: Page, step: TestStep, run_id: str, index: int) -> tuple[str, str | None]:
        default_timeout = (
            settings.PRODUCTION_TIMEOUT_MS if settings.ENV == "production" else settings.DEFAULT_TIMEOUT_MS
        )
        timeout = step.timeout_ms or default_timeout
        action = step.action.value
        if action != "open_url":
            await self._handle_common_interstitials(page)

        if action == "open_url":
            url = self._normalize_url(str(step.value or step.target or ""))
            url = self._normalize_mmt_entry_url(url)
            await page.goto(url, wait_until="commit", timeout=timeout)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=min(timeout, 12000))
            except Exception:
                pass
            try:
                await page.wait_for_load_state("networkidle", timeout=min(timeout, 5000))
            except Exception:
                pass
            await self._handle_common_interstitials(page)
            return f"Opened {url}", None

        if action == "click":
            locator = await resolve_locator(page, step.target, action="click")
            await locator.click(timeout=timeout)
            await self._settle_page(page, timeout)
            return f"Clicked {step.target}", None

        if action == "click_button":
            label = str(step.value or step.target or "")
            if not label:
                raise ValueError("click_button requires visible button text")
            await self._click_visible_text_or_button(page, label, timeout)
            await self._settle_page(page, timeout)
            return f"Clicked button '{label}'", None

        if action == "type":
            locator = await resolve_locator(page, step.target, action="type")
            await locator.fill(str(step.value or ""), timeout=timeout)
            return f"Typed into {step.target}", None

        if action == "search":
            locator = await resolve_locator(page, step.target or "searchbox", action="search")
            await locator.fill(str(step.value or ""), timeout=timeout)
            await locator.press("Enter", timeout=timeout)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)
            await self._settle_page(page, timeout)
            return f"Searched for {step.value}", None

        if action == "wait":
            if step.target:
                locator = await resolve_locator(page, step.target, action="wait")
                await locator.wait_for(state="visible", timeout=timeout)
                return f"Waited for {step.target}", None
            await page.wait_for_timeout(int(step.value or 1000))
            return "Waited", None

        if action == "scroll":
            amount = int(step.value or 900)
            await page.mouse.wheel(0, amount)
            await page.wait_for_timeout(350)
            return f"Scrolled {amount}px", None

        if action == "screenshot":
            path = await self._screenshot(page, run_id, index, "manual")
            return "Captured screenshot", path

        if action == "verify_text":
            text = str(step.value or step.target or "")
            if not text:
                raise ValueError("verify_text requires text in value or target")
            await page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=timeout)
            return f"Verified text: {text}", None

        if action == "verify_element":
            locator = await resolve_locator(page, step.target or str(step.value or ""), action="verify_element")
            await locator.wait_for(state="visible", timeout=timeout)
            return f"Verified element {step.target or step.value}", None

        if action == "add_to_cart":
            locator = await self._resolve_add_to_cart(page, timeout)
            await locator.click(timeout=timeout)
            await self._settle_page(page, timeout)
            await self._confirm_cart_state(page)
            return "Added item to cart and observed cart or checkout confirmation", None

        if action == "open_product":
            index = self._index_from_value(step.value)
            await self._open_product(page, index, timeout)
            await self._settle_page(page, timeout)
            return f"Opened product result #{index}", None

        if action == "set_quantity":
            quantity = int(step.value or 1)
            await self._set_quantity(page, quantity, timeout)
            return f"Set quantity to {quantity}", None

        if action == "buy_now":
            locator = await resolve_locator(page, step.target or "buy_now_button", action="buy_now", timeout_ms=3000)
            await locator.click(timeout=timeout)
            await self._settle_page(page, timeout)
            return "Clicked Buy Now", None

        if action == "login":
            await self._login(page, step.value, timeout)
            return "Submitted login form", None

        if action == "signup":
            await self._signup(page, step.value, timeout)
            return "Submitted signup form", None

        if action == "hover":
            locator = await resolve_locator(page, step.target, action="hover")
            await locator.hover(timeout=timeout)
            return f"Hovered {step.target}", None

        if action == "select_dropdown":
            locator = await resolve_locator(page, step.target, action="select_dropdown")
            await locator.select_option(str(step.value), timeout=timeout)
            await self._settle_page(page, timeout)
            return f"Selected {step.value} in {step.target}", None

        if action == "press_key":
            key = str(step.value or "Enter")
            if step.target:
                locator = await resolve_locator(page, step.target, action="press_key")
                await locator.press(key, timeout=timeout)
            else:
                await page.keyboard.press(key)
            return f"Pressed {key}", None

        if action == "sort_results":
            if self._is_mmt_page(page):
                await self._apply_mmt_sort(page, str(step.value or step.target or "recommended"), timeout)
                await self._settle_page(page, timeout)
                return f"Sorted MakeMyTrip results by {step.value or step.target}", None
            sort_value = self._sort_value(str(step.value or "featured"))
            locator = await resolve_locator(page, step.target or "sort_dropdown", action="sort_results")
            try:
                await locator.select_option(value=sort_value, timeout=timeout)
            except Exception:
                await locator.select_option(label=self._sort_label(str(step.value or "featured")), timeout=timeout)
            await self._settle_page(page, timeout)
            return f"Sorted results by {step.value or sort_value}", None

        if action == "filter_results":
            value = str(step.value or step.target or "").strip()
            if not value:
                raise ValueError("filter_results requires a visible filter value")
            await self._apply_filter(page, step.target, value, timeout)
            await self._settle_page(page, timeout)
            return f"Applied filter {step.target or 'filter'} = {value}", None

        if action == "verify_url":
            expected = str(step.value or step.target or "")
            if expected not in page.url:
                raise AssertionError(f"Expected URL to contain {expected}, got {page.url}")
            return f"Verified URL contains {expected}", None

        if action == "search_flights":
            await self._search_flights(page, step.value if isinstance(step.value, dict) else {}, timeout)
            return "Executed flight search workflow", None

        if action == "search_hotels":
            await self._search_hotels(page, step.value if isinstance(step.value, dict) else {}, timeout)
            return "Executed hotel search workflow", None

        if action == "search_cabs":
            await self._search_cabs(page, step.value if isinstance(step.value, dict) else {}, timeout)
            return "Executed cab search workflow", None

        raise ValueError(f"Unsupported action: {action}")

    async def _open_product(self, page: Page, index: int, timeout: int) -> None:
        index = max(1, index)
        for page_turn in range(4):
            for _ in range(6):
                product = await self._extract_product_href(page, index)
                if product:
                    href = urljoin(page.url, product["href"])
                    await self.on_log(
                        f"Opening product #{index}: {product.get('text', href)[:120]}",
                        {"href": href, "product_text": product.get("text")},
                    )
                    await page.goto(href, wait_until="domcontentloaded", timeout=timeout)
                    return
                await page.mouse.wheel(0, 1100)
                await page.wait_for_timeout(400)

            next_candidates = [
                page.get_by_role("link", name=re.compile("next|next page", re.I)),
                page.get_by_text(re.compile("next", re.I)),
                page.locator("a.s-pagination-next"),
            ]
            clicked_next = False
            for candidate in next_candidates:
                try:
                    await candidate.first.click(timeout=1800)
                    await self._settle_page(page, timeout)
                    clicked_next = True
                    break
                except Exception:
                    continue
            if not clicked_next:
                break
        raise AssertionError(f"Could not find product result #{index} across visible result pages")

    async def _extract_product_href(self, page: Page, index: int) -> dict[str, str] | None:
        return await page.evaluate(
            """
            (targetIndex) => {
              const selectors = [
                "[data-component-type='s-search-result'] a[data-type='productTitle']",
                "[data-component-type='s-search-result'] h2 a",
                "[data-component-type='s-search-result'] a.a-link-normal.s-no-outline",
                "[data-component-type='s-search-result'] a[href*='/dp/']",
                "a[data-type='productTitle']",
                "a[href*='/dp/']"
              ];
              const seen = new Set();
              const products = [];
              for (const selector of selectors) {
                for (const anchor of document.querySelectorAll(selector)) {
                  const href = anchor.href || anchor.getAttribute('href');
                  const text = (anchor.innerText || anchor.textContent || anchor.getAttribute('aria-label') || '').trim();
                  const rect = anchor.getBoundingClientRect();
                  const key = href + '|' + text;
                  if (!href || seen.has(key)) continue;
                  if (rect.width < 20 || rect.height < 8) continue;
                  if (!/\\/dp\\/|\\/gp\\/product\\//.test(href) && !anchor.matches("[data-type='productTitle']")) continue;
                  if (text.length < 4 && !anchor.matches("[data-type='productTitle']")) continue;
                  seen.add(key);
                  products.push({ href, text: text || anchor.getAttribute('title') || 'Product result' });
                }
              }
              return products[targetIndex - 1] || null;
            }
            """,
            index,
        )

    async def _set_quantity(self, page: Page, quantity: int, timeout: int) -> None:
        quantity = max(1, min(quantity, 30))
        is_amazon = self._is_amazon_page(page)
        cart_context = await self._open_amazon_cart_for_quantity(page, timeout) if is_amazon else False

        if cart_context and await self._set_amazon_full_cart_quantity(page, quantity, timeout):
            await self._settle_page(page, timeout)
            if await self._verify_quantity(page, quantity):
                return

        if await self._set_amazon_custom_quantity(page, quantity, timeout):
            await self._settle_page(page, timeout)
            if not is_amazon or await self._verify_quantity(page, quantity):
                return

        if await self._set_native_quantity_select(page, quantity, timeout):
            await self._settle_page(page, timeout)
            if not is_amazon or await self._verify_quantity(page, quantity):
                return

        if await self._set_quantity_with_stepper(page, quantity, timeout):
            await self._settle_page(page, timeout)
            if not is_amazon or await self._verify_quantity(page, quantity):
                return

        if is_amazon and await self._verify_quantity(page, quantity):
            return

        raise AssertionError(f"Quantity control was not visible or could not be verified as {quantity}")

    async def _open_amazon_cart_for_quantity(self, page: Page, timeout: int) -> bool:
        if not self._is_amazon_page(page):
            return False

        url = page.url.lower()
        if ("/cart" in url or "/gp/cart" in url) and "smart-wagon" not in url:
            return True

        side_cart = await self._first_visible_optional(
            page,
            [
                page.locator("#ewc-content"),
                page.locator("[id*='ewc-content']"),
                page.get_by_text(re.compile("subtotal|go to cart", re.I)),
            ],
            timeout_ms=700,
        )
        if "smart-wagon" not in url and side_cart is None:
            return False

        go_to_cart = await self._first_visible_optional(
            page,
            [
                page.locator("#ewc-content a:has-text('Go to Cart')"),
                page.locator("#ewc-content a:has-text('Cart')"),
                page.locator(".ewc-go-to-cart a"),
                page.get_by_role("link", name=re.compile(r"^go to cart$|^cart$", re.I)),
                page.locator("#nav-cart"),
            ],
            timeout_ms=2500,
        )
        if go_to_cart is not None:
            try:
                await go_to_cart.click(timeout=timeout)
            except Exception:
                await go_to_cart.click(timeout=timeout, force=True)
            await self._settle_page(page, timeout)

        if ("/cart" in page.url.lower() or "/gp/cart" in page.url.lower()) and "smart-wagon" not in page.url.lower():
            return True

        try:
            await page.locator("#nav-cart").click(timeout=2200)
            await self._settle_page(page, timeout)
        except Exception:
            pass
        return ("/cart" in page.url.lower() or "/gp/cart" in page.url.lower()) and "smart-wagon" not in page.url.lower()

    async def _set_amazon_full_cart_quantity(self, page: Page, quantity: int, timeout: int) -> bool:
        selectors = [
            "#sc-active-cart select[name='quantity']",
            "[data-name='Active Items'] select[name='quantity']",
            ".sc-list-item select[name='quantity']",
            ".sc-action-quantity select[name='quantity']",
            "#ewc-content select[name='quantity']",
            "select[name='quantity']",
        ]
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                await locator.wait_for(state="attached", timeout=1200)
                try:
                    await locator.select_option(value=str(quantity), timeout=timeout, force=True)
                except Exception:
                    await locator.select_option(label=str(quantity), timeout=timeout, force=True)
                await page.wait_for_timeout(1000)
                if await self._verify_quantity(page, quantity):
                    return True
            except Exception:
                continue

        if await self._set_amazon_custom_quantity(page, quantity, timeout):
            await page.wait_for_timeout(1000)
            if await self._verify_quantity(page, quantity):
                return True

        if await self._set_quantity_with_stepper(page, quantity, timeout):
            await page.wait_for_timeout(1000)
            return await self._verify_quantity(page, quantity)

        return False

    async def _set_native_quantity_select(self, page: Page, quantity: int, timeout: int) -> bool:
        try:
            locator = await resolve_locator(page, "quantity", action="set_quantity", timeout_ms=2500)
            try:
                await locator.select_option(label=str(quantity), timeout=timeout)
            except Exception:
                await locator.select_option(value=str(quantity), timeout=timeout)
            await self._settle_page(page, timeout)
            return True
        except Exception:
            return False

    async def _set_amazon_custom_quantity(self, page: Page, quantity: int, timeout: int) -> bool:
        option_index = max(quantity - 1, 0)
        selectors = [
            "#sc-active-cart .sc-action-quantity .a-dropdown-prompt",
            "#sc-active-cart [data-action='quantity'] .a-dropdown-prompt",
            "#sc-active-cart [data-action='a-dropdown-button']",
            "#ewc-content .sc-action-quantity .a-dropdown-prompt",
            "#ewc-content [data-action='quantity'] .a-dropdown-prompt",
            "#quantity",
            "select[name='quantity']",
            "#ppd .a-dropdown-prompt",
            "#ppd [data-action='a-dropdown-button']",
            ".sc-action-quantity .a-dropdown-prompt",
            "[data-action='a-dropdown-button']",
        ]
        opened = False
        for selector in selectors:
            try:
                await page.locator(selector).first.click(timeout=1200, force=True)
                opened = True
                await page.wait_for_timeout(250)
                break
            except Exception:
                continue
        if not opened:
            return False

        option_selectors = [
            f".a-popover a#quantity_{option_index}",
            f".a-popover a[data-value*='\"{quantity}\"']",
            f".a-popover li:has-text('{quantity}')",
            f".a-popover a:has-text('{quantity}')",
            f"#quantity_{option_index}",
        ]
        for selector in option_selectors:
            try:
                await page.locator(selector).first.click(timeout=1600, force=True)
                await page.wait_for_timeout(500)
                return True
            except Exception:
                continue
        return bool(
            await page.evaluate(
                """
                (quantity) => {
                  const expected = String(quantity);
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                      && rect.height > 0
                      && rect.right > 0
                      && rect.bottom > 0
                      && rect.left < window.innerWidth
                      && rect.top < window.innerHeight
                      && style.display !== "none"
                      && style.visibility !== "hidden";
                  };
                  const options = Array.from(document.querySelectorAll(".a-popover a, .a-popover li, [role='option'], a, li"))
                    .filter(visible)
                    .filter((element) => {
                      const text = (element.innerText || element.textContent || "").trim();
                      const value = element.getAttribute("data-value") || element.getAttribute("value") || "";
                      return text === expected || value.includes(`"${expected}"`) || value === expected;
                    });
                  if (!options.length) return false;
                  options[0].click();
                  return true;
                }
                """,
                quantity,
            )
        )

    async def _set_quantity_with_stepper(self, page: Page, quantity: int, timeout: int) -> bool:
        current = await self._read_quantity_hint(page)
        if current is None or current < 1:
            current = 1
        delta = quantity - current
        if delta == 0:
            return True
        direction = "increase" if delta > 0 else "decrease"
        for _ in range(abs(delta)):
            clicked = await self._click_quantity_stepper(page, direction, timeout)
            if not clicked:
                return False
            await page.wait_for_timeout(450)
        return True

    async def _read_quantity_hint(self, page: Page) -> int | None:
        value = await page.evaluate(
            """
            () => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0
                  && rect.height > 0
                  && rect.right > 0
                  && rect.bottom > 0
                  && rect.left < window.innerWidth
                  && rect.top < window.innerHeight
                  && style.display !== "none"
                  && style.visibility !== "hidden";
              };
              const direct = document.querySelector(
                "#sc-active-cart select[name='quantity'], [data-name='Active Items'] select[name='quantity'], .sc-action-quantity select[name='quantity'], #quantity, select[name='quantity']"
              );
              if (direct && direct.value && /^\\d+$/.test(direct.value)) return Number(direct.value);
              const quantityElements = Array.from(document.querySelectorAll(".sc-action-quantity, [data-action='quantity'], input, select, span, div"))
                .filter(visible)
                .filter((element) => /quantity|qty/i.test(
                  `${element.getAttribute("aria-label") || ""} ${element.getAttribute("name") || ""} ${element.id || ""} ${element.className || ""}`
                ));
              for (const element of quantityElements) {
                const raw = (element.value || element.innerText || element.textContent || "").trim();
                const match = raw.match(/(?:Quantity is\\s*)?(\\d+)$/i) || raw.match(/^(\\d+)$/);
                if (match) return Number(match[1] || match[0]);
              }
              return null;
            }
            """
        )
        return int(value) if isinstance(value, (int, float)) else None

    async def _click_quantity_stepper(self, page: Page, direction: str, timeout: int) -> bool:
        if direction == "increase":
            candidates = [
                page.locator("#sc-active-cart [aria-label*='Increase quantity' i], #ewc-content [aria-label*='Increase quantity' i]"),
                page.locator("#sc-active-cart [data-action*='increment' i], #ewc-content [data-action*='increment' i]"),
                page.locator("[aria-label*='Increase quantity' i], [aria-label*='increment' i]"),
                page.locator("[data-action*='increment' i], [data-a-selector*='increment' i]"),
                page.get_by_role("button", name=re.compile(r"increase|increment|\+", re.I)),
                page.get_by_text(re.compile(r"^\+$")),
            ]
            js_pattern = r"increase|increment|plus|^\+$"
        else:
            candidates = [
                page.locator("#sc-active-cart [aria-label*='Decrease quantity' i], #ewc-content [aria-label*='Decrease quantity' i]"),
                page.locator("#sc-active-cart [data-action*='decrement' i], #ewc-content [data-action*='decrement' i]"),
                page.locator("[aria-label*='Decrease quantity' i], [aria-label*='decrement' i]"),
                page.locator("[data-action*='decrement' i], [data-a-selector*='decrement' i]"),
                page.get_by_role("button", name=re.compile(r"decrease|decrement|\-", re.I)),
                page.get_by_text(re.compile(r"^\-$")),
            ]
            js_pattern = r"decrease|decrement|minus|^\-$"

        control = await self._first_visible_optional(page, candidates, timeout_ms=1200)
        if control is not None:
            try:
                await control.click(timeout=timeout)
            except Exception:
                await control.click(timeout=timeout, force=True)
            return True

        return bool(
            await page.evaluate(
                """
                (pattern) => {
                  const matcher = new RegExp(pattern, "i");
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                      && rect.height > 0
                      && rect.right > 0
                      && rect.bottom > 0
                      && rect.left < window.innerWidth
                      && rect.top < window.innerHeight
                      && style.display !== "none"
                      && style.visibility !== "hidden";
                  };
                  const roots = Array.from(document.querySelectorAll("#sc-active-cart, [data-name='Active Items'], #ewc-content, .sc-action-quantity"));
                  if (!roots.length) roots.push(document.body);
                  const element = roots.flatMap((root) => Array.from(root.querySelectorAll("button, input, a, span, div")))
                    .filter(visible)
                    .find((candidate) => matcher.test([
                      candidate.innerText,
                      candidate.textContent,
                      candidate.value,
                      candidate.getAttribute("aria-label"),
                      candidate.getAttribute("data-action"),
                      candidate.getAttribute("data-a-selector"),
                      candidate.className
                    ].filter(Boolean).join(" ")));
                  if (!element) return false;
                  element.click();
                  return true;
                }
                """,
                js_pattern,
            )
        )

    async def _verify_quantity(self, page: Page, quantity: int) -> bool:
        return bool(
            await page.evaluate(
                """
                (quantity) => {
                  const expected = String(quantity);
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                      && rect.height > 0
                      && rect.right > 0
                      && rect.bottom > 0
                      && rect.left < window.innerWidth
                      && rect.top < window.innerHeight
                      && style.display !== "none"
                      && style.visibility !== "hidden";
                  };

                  const roots = Array.from(document.querySelectorAll(
                    "#sc-active-cart, [data-name='Active Items'], #ewc-content, #ppd, .sc-action-quantity, #quantity"
                  ));
                  if (!roots.length) roots.push(document.body);
                  for (const root of roots) {
                    const selects = Array.from(root.querySelectorAll("select[name='quantity'], #quantity"))
                      .filter((element) => element instanceof HTMLSelectElement || element.id === "quantity");
                    for (const select of selects) {
                      const selectedText = select.selectedOptions?.[0]?.textContent?.trim();
                      if (String(select.value) === expected || selectedText === expected) return true;
                    }

                    const selector = root === document.body
                      ? ".sc-action-quantity, [data-action='quantity'], .a-dropdown-prompt, [aria-label*='Quantity' i], [aria-label*='quantity' i]"
                      : ".sc-action-quantity, [data-action='quantity'], .a-dropdown-prompt, [aria-label*='Quantity' i], [aria-label*='quantity' i], span, div";
                    const candidates = Array.from(root.querySelectorAll(selector)).filter(visible);
                    for (const candidate of candidates) {
                      const label = candidate.getAttribute("aria-label") || "";
                      const text = (candidate.innerText || candidate.textContent || "").replace(/\\s+/g, " ").trim();
                      if (label.match(new RegExp(`quantity\\\\D+${expected}\\\\b`, "i"))) return true;
                      if (text === expected) return true;
                      if (text.match(new RegExp(`quantity is\\\\s*${expected}\\\\b`, "i"))) return true;
                    }
                  }
                  return false;
                }
                """,
                quantity,
            )
        )

    async def _resolve_add_to_cart(self, page: Page, timeout: int):
        try:
            return await resolve_locator(page, "add_to_cart_button", action="add_to_cart", timeout_ms=2200)
        except Exception:
            if await self._page_has_unavailable_cart_state(page):
                raise AssertionError(await self._cart_unavailable_message(page))
            try:
                product = await resolve_locator(page, "first_product", action="click", timeout_ms=2200)
                await product.click(timeout=timeout)
                await self._settle_page(page, timeout)
                return await resolve_locator(page, "add_to_cart_button", action="add_to_cart", timeout_ms=5000)
            except Exception as exc:
                if await self._page_has_unavailable_cart_state(page):
                    raise AssertionError(await self._cart_unavailable_message(page)) from exc
                raise

    async def _page_has_unavailable_cart_state(self, page: Page) -> bool:
        patterns = [
            "currently unavailable",
            "no featured offers available",
            "cannot be shipped",
            "out of stock",
            "choose a different delivery location",
        ]
        for text in patterns:
            try:
                await page.get_by_text(re.compile(re.escape(text), re.I)).first.wait_for(state="visible", timeout=500)
                return True
            except Exception:
                continue
        return False

    async def _cart_unavailable_message(self, page: Page) -> str:
        signals = [
            "No featured offers available",
            "This item cannot be shipped to your selected delivery location",
            "Currently unavailable",
            "Out of stock",
        ]
        found = []
        for signal in signals:
            try:
                locator = page.get_by_text(re.compile(re.escape(signal), re.I)).first
                await locator.wait_for(state="visible", timeout=500)
                found.append(signal)
            except Exception:
                continue
        suffix = "; ".join(found) if found else "No Add to Cart control was visible"
        return f"Add-to-cart is unavailable for this product: {suffix}"

    async def _confirm_cart_state(self, page: Page) -> None:
        candidates = [
            page.get_by_text(re.compile("added to cart|added to basket|cart", re.I)),
            page.get_by_role("link", name=re.compile("cart|basket|checkout", re.I)),
            page.get_by_role("button", name=re.compile("checkout|cart|basket", re.I)),
        ]
        for candidate in candidates:
            try:
                await candidate.first.wait_for(state="visible", timeout=2500)
                return
            except Exception:
                continue
        raise AssertionError("Add-to-cart click finished, but no visible cart or checkout confirmation was found")

    async def _click_visible_text_or_button(self, page: Page, label: str, timeout: int) -> None:
        escaped = re.escape(label)
        candidates = [
            page.get_by_role("button", name=re.compile(escaped, re.I)),
            page.get_by_role("link", name=re.compile(escaped, re.I)),
            page.get_by_text(re.compile(escaped, re.I)),
            page.locator(f"button:has-text('{label}')"),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=2500)
        if locator is None:
            raise AssertionError(f"Could not find visible button or link labelled '{label}'")
        await locator.click(timeout=timeout)

    async def _signup(self, page: Page, value: Any, timeout: int) -> None:
        fields = value if isinstance(value, dict) else {}
        if not fields:
            raise ValueError("Signup requires explicitly provided fields")
        await self._click_if_visible(page, ["sign up", "signup", "create account", "register"], timeout_ms=1800)
        for key, field_value in fields.items():
            if field_value is None:
                continue
            locator = await resolve_locator(page, str(key), action="signup", timeout_ms=2500)
            await locator.fill(str(field_value), timeout=timeout)
        await self._click_if_visible(page, ["sign up", "create account", "register", "submit", "continue"], timeout_ms=2500)
        await self._settle_page(page, timeout)

    async def _search_flights(self, page: Page, value: dict[str, Any], timeout: int) -> None:
        departure_date = self._safe_string(value.get("departure_date"))
        return_date = self._safe_string(value.get("return_date"))
        adults = int(value.get("adults") or 1)
        cabin = str(value.get("cabin") or "Economy")

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                if attempt:
                    await self.on_log("Retrying MakeMyTrip flight search through the classic widget", None)
                await self._prepare_mmt_surface(page, "flights", timeout)
                if return_date:
                    await self._click_if_visible(page, ["Round Trip", "Roundtrip"], timeout_ms=2200)
                else:
                    await self._click_if_visible(page, ["One Way"], timeout_ms=1400)
                await self._fill_travel_route(page, value.get("from"), value.get("to"), timeout)
                await self._confirm_mmt_departure_date(page, departure_date, "Departure")
                if return_date:
                    await self._confirm_mmt_departure_date(page, return_date, "Return")
                await self._set_travelers_and_class(page, adults, cabin, timeout)
                await self._click_mmt_search(page, timeout)
                await self._settle_page(page, timeout)
                if await self._mmt_page_is_bare_ok(page):
                    raise AssertionError("MakeMyTrip returned a bare 200-OK page after Search")
                await self._wait_for_mmt_results(page, "flights", timeout)
                if "makemytrip.com/flight/search" not in page.url:
                    raise AssertionError(f"Flight search did not reach MakeMyTrip results page: {page.url}")
                if departure_date:
                    expected = self._mmt_url_date(departure_date)
                    if expected and expected not in page.url:
                        raise AssertionError(
                            f"Flight search completed, but MakeMyTrip URL does not confirm departure date {departure_date}: {page.url}"
                        )
                if return_date:
                    expected = self._mmt_url_date(return_date)
                    if expected and expected not in page.url:
                        raise AssertionError(
                            f"Flight search completed, but MakeMyTrip URL does not confirm return date {return_date}: {page.url}"
                        )
                if adults > 1 and f"paxType=A-{adults}" not in page.url:
                    raise AssertionError(
                        f"Flight search completed, but MakeMyTrip URL does not confirm {adults} adults: {page.url}"
                    )
                return
            except Exception as exc:
                last_error = exc
                if attempt < 2 and (await self._mmt_page_is_bare_ok(page) or "200-OK" in str(exc)):
                    await self._reset_mmt_to_classic(page, "flights", timeout)
                    continue
                raise
        if last_error:
            raise last_error

    async def _search_hotels(self, page: Page, value: dict[str, Any], timeout: int) -> None:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                if attempt:
                    await self.on_log("Retrying MakeMyTrip hotel search through the classic widget", None)
                await self._prepare_mmt_surface(page, "hotels", timeout)
                location = value.get("location")
                if location:
                    await self._fill_mmt_hotel_location(page, str(location), timeout)
                checkin_date = self._safe_string(value.get("checkin_date") or value.get("check_in_date"))
                checkout_date = self._safe_string(value.get("checkout_date") or value.get("check_out_date"))
                if checkin_date:
                    await self._confirm_mmt_hotel_date(page, checkin_date, "Check-In")
                if checkout_date:
                    await self._confirm_mmt_hotel_date(page, checkout_date, "Check-Out")
                await self._set_hotel_rooms_guests(
                    page,
                    rooms=int(value.get("rooms") or 1),
                    adults=int(value.get("adults") or 2),
                    children=int(value.get("children") or 0),
                    timeout=timeout,
                )
                await self._click_mmt_search(page, timeout)
                await self._settle_page(page, timeout)
                if await self._mmt_page_is_bare_ok(page):
                    raise AssertionError("MakeMyTrip returned a bare 200-OK page after hotel Search")
                await self._wait_for_mmt_results(page, "hotels", timeout)
                return
            except Exception as exc:
                last_error = exc
                if attempt < 2 and (await self._mmt_page_is_bare_ok(page) or "200-OK" in str(exc)):
                    await self._reset_mmt_to_classic(page, "hotels", timeout)
                    continue
                raise
        if last_error:
            raise last_error

    async def _search_cabs(self, page: Page, value: dict[str, Any], timeout: int) -> None:
        await self._prepare_mmt_surface(page, "cabs", timeout)
        await self._fill_travel_route(page, value.get("from"), value.get("to"), timeout)
        await self._click_mmt_search(page, timeout)
        await self._settle_page(page, timeout)
        await self._wait_for_mmt_results(page, "cabs", timeout)

    async def _prepare_mmt_surface(self, page: Page, flow: str, timeout: int) -> None:
        if await self._mmt_page_is_bare_ok(page):
            await self._reset_mmt_to_classic(page, flow, timeout)
        await self._close_common_popups(page)
        await self._click_mmt_classic_search(page)
        await self._select_mmt_nav_tab(page, flow, timeout)
        await self._close_common_popups(page)
        await self._click_mmt_classic_search(page)

    async def _reset_mmt_to_classic(self, page: Page, flow: str, timeout: int) -> None:
        try:
            await page.context.clear_cookies()
        except Exception:
            pass
        try:
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=min(timeout, 5000))
        except Exception:
            pass
        await page.goto("https://www.makemytrip.com/flights/", wait_until="domcontentloaded", timeout=timeout)
        await self._settle_page(page, timeout)
        await self._close_common_popups(page)
        await self._click_mmt_classic_search(page)
        await self._select_mmt_nav_tab(page, flow, timeout)

    async def _select_mmt_nav_tab(self, page: Page, flow: str, timeout: int) -> None:
        labels = {
            "flights": ["Flights", "Flight"],
            "hotels": ["Hotels", "Hotel"],
            "cabs": ["Cabs", "Cab"],
        }.get(flow, [flow.title()])

        if flow == "flights" and "flights" in page.url.lower() and not await self._mmt_page_is_bare_ok(page):
            return
        if flow == "hotels" and "hotels" in page.url.lower() and not await self._mmt_page_is_bare_ok(page):
            return
        if flow == "cabs" and "cabs" in page.url.lower() and not await self._mmt_page_is_bare_ok(page):
            return

        for label in labels:
            clicked = await page.evaluate(
                """
                (label) => {
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                      && rect.height > 0
                      && rect.right > 0
                      && rect.bottom > 0
                      && rect.left < window.innerWidth
                      && rect.top < window.innerHeight
                      && style.display !== "none"
                      && style.visibility !== "hidden";
                  };
                  const wanted = label.toLowerCase();
                  const candidates = Array.from(document.querySelectorAll(".chHeaderWrapper a, .chHeaderWrapper span, a, span, li"))
                    .filter(visible)
                    .filter((element) => (element.innerText || element.textContent || "").trim().toLowerCase() === wanted);
                  if (!candidates.length) return false;
                  candidates[0].click();
                  return true;
                }
                """,
                label,
            )
            if clicked:
                await self._settle_page(page, timeout)
                return

        if not await self._click_if_visible(page, labels, timeout_ms=2500):
            raise AssertionError(f"Could not switch MakeMyTrip to {flow}")
        await self._settle_page(page, timeout)

    async def _click_mmt_classic_search(self, page: Page) -> bool:
        labels = [
            "Back to Classic Search",
            "Classic Search",
        ]
        for label in labels:
            locator = await self._first_visible_optional(
                page,
                [
                    page.get_by_role("button", name=re.compile(re.escape(label), re.I)),
                    page.get_by_role("link", name=re.compile(re.escape(label), re.I)),
                    page.get_by_text(re.compile(re.escape(label), re.I)),
                ],
                timeout_ms=900,
            )
            if locator is not None:
                try:
                    await locator.click(timeout=1800)
                except Exception:
                    await locator.click(timeout=1800, force=True)
                await page.wait_for_timeout(900)
                return True
        return bool(
            await page.evaluate(
                """
                () => {
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                      && rect.height > 0
                      && rect.right > 0
                      && rect.bottom > 0
                      && rect.left < window.innerWidth
                      && rect.top < window.innerHeight
                      && style.display !== "none"
                      && style.visibility !== "hidden";
                  };
                  const element = Array.from(document.querySelectorAll("button, a, div, span"))
                    .filter(visible)
                    .find((candidate) => /back to classic search|classic search/i.test(candidate.innerText || candidate.textContent || ""));
                  if (!element) return false;
                  element.click();
                  return true;
                }
                """
            )
        )

    async def _fill_travel_route(self, page: Page, source: Any, destination: Any, timeout: int) -> None:
        if source:
            await self._fill_mmt_city_field(page, "from", str(source), timeout)
        if destination:
            await self._fill_mmt_city_field(page, "to", str(destination), timeout)

    async def _fill_mmt_city_field(self, page: Page, field: str, value: str, timeout: int) -> None:
        field_selectors = {
            "from": ["[data-cy='fromCity']", "label[for='fromCity']", "#fromCity"],
            "to": ["[data-cy='toCity']", "label[for='toCity']", "#toCity"],
        }
        input_selectors = {
            "from": ["input[placeholder*='From']", "input[placeholder*='FROM']", "input.react-autosuggest__input"],
            "to": ["input[placeholder*='To']", "input[placeholder*='TO']", "input.react-autosuggest__input"],
        }

        await self._close_common_popups(page)
        for selector in field_selectors[field]:
            try:
                await page.locator(selector).first.click(timeout=2200)
                await page.wait_for_timeout(450)
                break
            except Exception:
                continue
        else:
            raise AssertionError(f"Could not open MakeMyTrip {field} city field")

        input_locator = await self._first_visible_optional(
            page,
            [page.locator(selector) for selector in input_selectors[field]],
            timeout_ms=2500,
        )
        if input_locator is None:
            raise AssertionError(f"Could not find MakeMyTrip {field} city input")

        await input_locator.fill(value, timeout=timeout)
        await page.wait_for_timeout(900)
        await self._select_suggestion(page, value, timeout)

    async def _fill_generic_travel_field(self, page: Page, labels: list[str], value: str, timeout: int) -> None:
        for label in labels:
            try:
                await page.get_by_text(re.compile(f"^{re.escape(label)}$", re.I)).first.click(timeout=1800)
                await page.wait_for_timeout(350)
                input_locator = await self._first_visible_optional(
                    page,
                    [
                        page.locator("input[type='text']"),
                        page.get_by_placeholder(re.compile("from|to|city|destination|search", re.I)),
                        page.get_by_role("textbox"),
                    ],
                    timeout_ms=2000,
                )
                if input_locator:
                    await input_locator.fill(value, timeout=timeout)
                    await page.wait_for_timeout(900)
                    await self._select_suggestion(page, value, timeout)
                    return
            except Exception:
                continue
        raise AssertionError(f"Could not fill travel field {labels[0]} with {value}")

    async def _fill_mmt_hotel_location(self, page: Page, value: str, timeout: int) -> None:
        await self._close_common_popups(page)
        current_value = await page.evaluate(
            """
            () => {
              const field = document.querySelector("#city, [data-cy='city']");
              return field ? String(field.value || field.innerText || field.textContent || "").trim() : "";
            }
            """
        )
        if current_value and value.lower() in current_value.lower():
            return
        field = await self._first_visible_optional(
            page,
            [
                page.locator("[data-cy='HotelSearchWidget_316']"),
                page.locator("#city"),
                page.locator(".selectHtlCity"),
                page.get_by_text(re.compile("City, Property Name Or Location", re.I)),
            ],
            timeout_ms=3500,
        )
        if field is None:
            raise AssertionError("Could not find MakeMyTrip hotel city field")
        try:
            await field.click(timeout=timeout)
        except Exception:
            await field.click(timeout=timeout, force=True)
        await page.wait_for_timeout(500)

        input_locator = await self._first_visible_optional(
            page,
            [
                page.locator("input:not([readonly])[placeholder*='City' i]"),
                page.locator("input:not([readonly])[placeholder*='Property' i]"),
                page.locator("input:not([readonly])[type='text']"),
                page.locator("input[placeholder*='City' i]"),
                page.locator("input[placeholder*='Property' i]"),
            ],
            timeout_ms=2500,
        )
        if input_locator is None:
            raise AssertionError("Could not find MakeMyTrip hotel city input")
        await input_locator.fill(value, timeout=timeout)
        await page.wait_for_timeout(1000)
        await self._select_suggestion(page, value, timeout)

    async def _confirm_mmt_hotel_date(self, page: Page, target_date: str, field_label: str) -> None:
        await self._open_mmt_hotel_date_field(page, field_label)
        selected = await self._select_mmt_calendar_date(page, target_date)
        if not selected:
            raise AssertionError(f"Could not select MakeMyTrip hotel {field_label} date {target_date}")
        await page.wait_for_timeout(600)

    async def _open_mmt_hotel_date_field(self, page: Page, field_label: str) -> None:
        is_checkout = "out" in field_label.lower()
        candidates = [
            page.locator("[data-cy='HotelSearchWidget_318']" if is_checkout else "[data-cy='HotelSearchWidget_317']"),
            page.get_by_text(re.compile("Check-Out" if is_checkout else "Check-In", re.I)),
            page.locator(".hsw_inputBox.dates").nth(1 if is_checkout else 0),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=2200)
        if locator is None:
            raise AssertionError(f"Could not find MakeMyTrip hotel {field_label} field")
        try:
            await locator.click(timeout=1800)
        except Exception:
            await locator.click(timeout=1800, force=True)
        await page.wait_for_timeout(500)

    async def _set_hotel_rooms_guests(
        self,
        page: Page,
        rooms: int,
        adults: int,
        children: int,
        timeout: int,
    ) -> None:
        rooms = max(1, min(int(rooms or 1), 4))
        adults = max(1, min(int(adults or 2), 20))
        children = max(0, min(int(children or 0), 12))

        opened = await self._open_mmt_hotel_guests_panel(page, timeout)
        if not opened:
            await self.on_log("MakeMyTrip hotel room/guest selector was not visible; continuing with defaults", None)
            return

        changed = await page.evaluate(
            """
            ({ rooms, adults, children }) => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0
                  && rect.height > 0
                  && rect.right > 0
                  && rect.bottom > 0
                  && rect.left < window.innerWidth
                  && rect.top < window.innerHeight
                  && style.display !== "none"
                  && style.visibility !== "hidden";
              };
              const all = Array.from(document.querySelectorAll("button, span, div, p")).filter(visible);
              const readText = (el) => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
              const rowFor = (labelPattern) => {
                const label = all.find((element) => labelPattern.test(readText(element)));
                if (!label) return null;
                const rect = label.getBoundingClientRect();
                const nearby = all
                  .map((element) => ({ element, rect: element.getBoundingClientRect(), text: readText(element) }))
                  .filter((item) => Math.abs(item.rect.top - rect.top) < 42 && item.rect.left > rect.left)
                  .sort((a, b) => a.rect.left - b.rect.left);
                return nearby;
              };
              const currentValue = (row, fallback) => {
                if (!row) return fallback;
                const numeric = row.find((item) => /^\\d+$/.test(item.text));
                return numeric ? Number(numeric.text) : fallback;
              };
              const clickControl = (row, direction) => {
                if (!row) return false;
                const wanted = direction > 0 ? /^(\\+|add)$/i : /^(-|remove)$/i;
                const candidates = row.filter((item) => wanted.test(item.text) || wanted.test(item.element.getAttribute("aria-label") || ""));
                const control = direction > 0 ? candidates[candidates.length - 1] : candidates[0];
                if (!control) return false;
                control.element.click();
                return true;
              };
              const setRow = (labelPattern, target, fallback) => {
                let row = rowFor(labelPattern);
                if (!row) return false;
                let current = currentValue(row, fallback);
                let guard = 0;
                while (current !== target && guard < 20) {
                  if (!clickControl(row, target > current ? 1 : -1)) return false;
                  current += target > current ? 1 : -1;
                  guard += 1;
                  row = rowFor(labelPattern);
                }
                return true;
              };
              const roomOk = setRow(/^Room\\b/i, rooms, 1);
              const adultOk = setRow(/^Adults?\\b/i, adults, 2);
              const childOk = setRow(/^Children\\b/i, children, 0);
              return { roomOk, adultOk, childOk };
            }
            """,
            {"rooms": rooms, "adults": adults, "children": children},
        )
        if not any(changed.values()):
            await self.on_log("Could not directly adjust hotel rooms/guests; keeping visible defaults", changed)

        if not await self._apply_mmt_travelers(page):
            await self._click_if_visible(page, ["Done", "Apply"], timeout_ms=1600)
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        await self.on_log(f"Requested MakeMyTrip hotel guests: {rooms} room(s), {adults} adult(s), {children} child(ren)", None)

    async def _open_mmt_hotel_guests_panel(self, page: Page, timeout: int) -> bool:
        if await self._first_visible_optional(
            page,
            [
                page.get_by_text(re.compile("^Room$", re.I)),
                page.get_by_text(re.compile("^Adults$", re.I)),
                page.get_by_text(re.compile("^Children$", re.I)),
            ],
            timeout_ms=600,
        ):
            return True
        locator = await self._first_visible_optional(
            page,
            [
                page.locator("[data-cy='HotelSearchWidget_319']"),
                page.locator(".roomGuests"),
                page.get_by_text(re.compile("Rooms & Guests", re.I)),
            ],
            timeout_ms=2600,
        )
        if locator is None:
            return False
        try:
            await locator.click(timeout=timeout)
        except Exception:
            await locator.click(timeout=timeout, force=True)
        await page.wait_for_timeout(600)
        return await self._first_visible_optional(
            page,
            [
                page.get_by_text(re.compile("^Room$", re.I)),
                page.get_by_text(re.compile("^Adults$", re.I)),
                page.get_by_text(re.compile("^Children$", re.I)),
            ],
            timeout_ms=1600,
        ) is not None

    async def _confirm_mmt_departure_date(
        self,
        page: Page,
        target_date: str | None = None,
        field_label: str = "Departure",
    ) -> None:
        calendar = await self._first_visible_optional(
            page,
            [
                page.locator(".DayPicker"),
                page.locator(".datePickerContainer"),
                page.locator("[class*='DayPicker']"),
            ],
            timeout_ms=900,
        )
        if calendar is None:
            if not target_date:
                return
            await self._open_mmt_calendar_field(page, field_label)
            calendar = await self._first_visible_optional(
                page,
                [
                    page.locator(".DayPicker"),
                    page.locator(".datePickerContainer"),
                    page.locator("[class*='DayPicker']"),
                ],
                timeout_ms=1800,
            )
            if calendar is None:
                raise AssertionError(f"Could not open MakeMyTrip {field_label} calendar")

        if target_date:
            selected = await self._select_mmt_calendar_date(page, target_date)
            if selected:
                await page.wait_for_timeout(500)
                return
            raise AssertionError(f"Could not select MakeMyTrip calendar date {target_date}")

        selected = await self._first_visible_optional(
            page,
            [
                page.locator(".DayPicker-Day--selected"),
                page.locator("[aria-selected='true']"),
                page.locator(".dateInnerCell.selected"),
                page.locator(".selected .dateInnerCell"),
            ],
            timeout_ms=900,
        )
        if selected is not None:
            try:
                await selected.click(timeout=1800)
            except Exception:
                await selected.click(timeout=1800, force=True)
            await page.wait_for_timeout(500)
            if not await self._mmt_calendar_is_open(page):
                return

        clicked = await page.evaluate(
            """
            () => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
              };
              const calendar = document.querySelector(".DayPicker, .datePickerContainer, [class*='DayPicker']");
              if (!calendar || !visible(calendar)) return false;
              const cells = Array.from(calendar.querySelectorAll("[aria-disabled='false'], [role='button'], .DayPicker-Day, div, p"))
                .filter(visible)
                .filter((element) => {
                  const text = (element.innerText || element.textContent || "").trim();
                  const className = String(element.className || "");
                  return /^\\d{1,2}(\\s|$)/.test(text) && !/disabled|outside/i.test(className);
                });
              const selected = cells.find((element) => {
                const className = String(element.className || "");
                return /selected/i.test(className) || element.getAttribute("aria-selected") === "true";
              });
              const target = selected || cells[0];
              if (!target) return false;
              target.click();
              return true;
            }
            """
        )
        await page.wait_for_timeout(500)
        if not clicked or await self._mmt_calendar_is_open(page):
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(350)

    async def _open_mmt_calendar_field(self, page: Page, field_label: str) -> None:
        label = "Return" if field_label.lower().startswith("return") else "Departure"
        candidates = [
            page.locator("[data-cy='return']" if label == "Return" else "[data-cy='departure']"),
            page.get_by_text(re.compile(label, re.I)),
            page.locator(f"label:has-text('{label}')"),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=1400)
        if locator is None:
            raise AssertionError(f"Could not find MakeMyTrip {label} date field")
        try:
            await locator.click(timeout=1800)
        except Exception:
            await locator.click(timeout=1800, force=True)
        await page.wait_for_timeout(450)

    async def _select_mmt_calendar_date(self, page: Page, target_date: str) -> bool:
        for _ in range(14):
            clicked = await page.evaluate(
                """
                (isoDate) => {
                  const target = new Date(`${isoDate}T00:00:00`);
                  if (Number.isNaN(target.getTime())) return false;
                  const monthNames = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                  ];
                  const monthLabel = `${monthNames[target.getMonth()]} ${target.getFullYear()}`;
                  const day = String(target.getDate());
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0
                      && rect.height > 0
                      && rect.right > 0
                      && rect.bottom > 0
                      && rect.left < window.innerWidth
                      && rect.top < window.innerHeight
                      && style.display !== "none"
                      && style.visibility !== "hidden";
                  };

                  const directPatterns = [
                    isoDate,
                    monthLabel,
                    `${monthNames[target.getMonth()]} ${target.getDate()} ${target.getFullYear()}`,
                    `${target.getDate()} ${monthNames[target.getMonth()]} ${target.getFullYear()}`
                  ];
                  const direct = Array.from(document.querySelectorAll("[aria-label], [data-date], [data-testid], [data-cy]"))
                    .filter(visible)
                    .find((element) => {
                      const haystack = [
                        element.getAttribute("aria-label"),
                        element.getAttribute("data-date"),
                        element.getAttribute("data-testid"),
                        element.getAttribute("data-cy")
                      ].filter(Boolean).join(" ");
                      return directPatterns.some((pattern) => haystack.includes(pattern))
                        && new RegExp(`(^|\\\\D)${day}($|\\\\D)`).test((element.innerText || element.textContent || day).trim());
                    });
                  if (direct) {
                    direct.click();
                    return true;
                  }

                  const allVisible = Array.from(document.querySelectorAll("div, p, span, button, td"))
                    .filter(visible)
                    .map((element) => ({
                      element,
                      rect: element.getBoundingClientRect(),
                      text: (element.innerText || element.textContent || "").replace(/\\s+/g, " ").trim(),
                      className: String(element.className || "")
                    }));
                  const monthHeaders = allVisible
                    .filter((item) => item.text === monthLabel || item.text.includes(monthLabel))
                    .sort((a, b) => a.rect.top - b.rect.top);
                  if (!monthHeaders.length) return false;
                  const cells = allVisible
                    .filter((item) => {
                      const first = item.text.split(/\\s+/)[0];
                      return first === day && !/disabled|outside/i.test(item.className);
                    })
                    .map((item) => {
                      const header = monthHeaders
                        .filter((candidate) => candidate.rect.top < item.rect.top)
                        .sort((a, b) => {
                          const aScore = Math.abs((a.rect.left + a.rect.width / 2) - (item.rect.left + item.rect.width / 2)) + Math.abs(item.rect.top - a.rect.top) / 4;
                          const bScore = Math.abs((b.rect.left + b.rect.width / 2) - (item.rect.left + item.rect.width / 2)) + Math.abs(item.rect.top - b.rect.top) / 4;
                          return aScore - bScore;
                        })[0];
                      return { ...item, header };
                    })
                    .filter((item) => item.header);
                  const targetCell = cells.find((item) => !/price|fare/i.test(item.className)) || cells[0];
                  if (targetCell) {
                    targetCell.element.click();
                    return true;
                  }
                  return false;
                }
                """,
                target_date,
            )
            if clicked:
                return True
            direction = await self._mmt_calendar_direction(page, target_date)
            moved = await self._click_mmt_prev_month(page) if direction == "prev" else await self._click_mmt_next_month(page)
            if not moved:
                return False
            await page.wait_for_timeout(350)
        return False

    async def _mmt_calendar_direction(self, page: Page, target_date: str) -> str:
        return str(
            await page.evaluate(
                """
                (isoDate) => {
                  const target = new Date(`${isoDate}T00:00:00`);
                  const monthNames = {
                    january: 0, february: 1, march: 2, april: 3, may: 4, june: 5,
                    july: 6, august: 7, september: 8, october: 9, november: 10, december: 11
                  };
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
                  };
                  const months = Array.from(document.querySelectorAll("div, p, span"))
                    .filter(visible)
                    .map((element) => (element.innerText || element.textContent || "").replace(/\\s+/g, " ").trim())
                    .map((text) => text.match(/\\b(January|February|March|April|May|June|July|August|September|October|November|December)\\s+(20\\d{2})\\b/i))
                    .filter(Boolean)
                    .map((match) => new Date(Number(match[2]), monthNames[match[1].toLowerCase()], 1).getTime())
                    .sort((a, b) => a - b);
                  if (!months.length) return "next";
                  const targetMonth = new Date(target.getFullYear(), target.getMonth(), 1).getTime();
                  return targetMonth < months[0] ? "prev" : "next";
                }
                """,
                target_date,
            )
        )

    async def _click_mmt_next_month(self, page: Page) -> bool:
        candidates = [
            page.locator(".DayPicker-NavButton--next"),
            page.locator("[aria-label*='Next' i]"),
            page.locator(".datePickerContainer").get_by_text(re.compile(r"^>$|next", re.I)),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=700)
        if locator is not None:
            try:
                await locator.click(timeout=1200)
            except Exception:
                await locator.click(timeout=1200, force=True)
            return True
        return bool(
            await page.evaluate(
                """
                () => {
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
                  };
                  const element = Array.from(document.querySelectorAll("button, span, div"))
                    .filter(visible)
                    .find((candidate) => /next|>|›|→/i.test(
                      `${candidate.innerText || ""} ${candidate.textContent || ""} ${candidate.getAttribute("aria-label") || ""} ${candidate.className || ""}`
                    ));
                  if (!element) return false;
                  element.click();
                  return true;
                }
                """
            )
        )

    async def _click_mmt_prev_month(self, page: Page) -> bool:
        candidates = [
            page.locator(".DayPicker-NavButton--prev"),
            page.locator("[aria-label*='Previous' i]"),
            page.locator("[aria-label*='Prev' i]"),
            page.locator(".datePickerContainer").get_by_text(re.compile(r"^<$|previous|prev", re.I)),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=700)
        if locator is not None:
            try:
                await locator.click(timeout=1200)
            except Exception:
                await locator.click(timeout=1200, force=True)
            return True
        return bool(
            await page.evaluate(
                """
                () => {
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
                  };
                  const element = Array.from(document.querySelectorAll("button, span, div"))
                    .filter(visible)
                    .find((candidate) => /previous|prev|<|‹|←/i.test(
                      `${candidate.innerText || ""} ${candidate.textContent || ""} ${candidate.getAttribute("aria-label") || ""} ${candidate.className || ""}`
                    ));
                  if (!element) return false;
                  element.click();
                  return true;
                }
                """
            )
        )

    async def _mmt_calendar_is_open(self, page: Page) -> bool:
        marker = await self._first_visible_optional(
            page,
            [
                page.locator(".DayPicker"),
                page.locator(".datePickerContainer"),
                page.locator("[class*='DayPicker']"),
            ],
            timeout_ms=500,
        )
        return marker is not None

    async def _select_suggestion(self, page: Page, value: str, timeout: int) -> None:
        city = value.split(",")[0].strip()
        candidates = [
            page.get_by_text(re.compile(re.escape(city), re.I)),
            page.locator("li, [role='option'], .react-autosuggest__suggestion").filter(has_text=re.compile(re.escape(city), re.I)),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=3500)
        if locator:
            await locator.click(timeout=timeout)
        else:
            await page.keyboard.press("Enter")

    async def _set_travelers_and_class(self, page: Page, adults: int, cabin: str, timeout: int) -> None:
        opened = await self._open_mmt_travelers_panel(page)
        if not opened:
            await self.on_log("MakeMyTrip traveler selector was not visible; continuing with default passengers", None)
            return

        adults = max(1, min(int(adults or 1), 9))
        if not await self._select_mmt_adult_count(page, adults):
            await self.on_log(f"Could not directly select {adults} adult(s); keeping the visible traveler default", None)

        if cabin and not await self._select_mmt_cabin(page, cabin):
            await self.on_log(f"Could not directly select cabin '{cabin}'; keeping the visible cabin default", None)

        if not await self._apply_mmt_travelers(page):
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(350)
        await self.on_log(f"Requested MakeMyTrip travelers: {adults} adult(s), cabin {cabin}", None)

    async def _open_mmt_travelers_panel(self, page: Page) -> bool:
        if await self._mmt_travelers_panel_is_open(page):
            return True

        async def click_center(selector: str) -> bool:
            locator = page.locator(selector).first
            try:
                await locator.wait_for(state="visible", timeout=1800)
                await locator.click(timeout=1800, force=True, position={"x": 90, "y": 70})
                return True
            except Exception:
                return False

        attempts = [
            lambda: click_center("[data-cy='flightTraveller']"),
            lambda: click_center("[data-cy='travellers']"),
            lambda: click_center(".flightTravllers"),
            lambda: page.evaluate(
                """
                () => {
                  const element = document.querySelector("[data-cy='flightTraveller'], [data-cy='travellers'], .flightTravllers");
                  if (!element) return false;
                  const rect = element.getBoundingClientRect();
                  element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: rect.left + 90, clientY: rect.top + 70 }));
                  element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, clientX: rect.left + 90, clientY: rect.top + 70 }));
                  element.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: rect.left + 90, clientY: rect.top + 70 }));
                  return true;
                }
                """
            ),
        ]

        for attempt in attempts:
            try:
                await attempt()
                await page.wait_for_timeout(500)
                if await self._mmt_travelers_panel_is_open(page):
                    return True
            except Exception:
                continue
        return False

    async def _mmt_travelers_panel_is_open(self, page: Page) -> bool:
        marker = await self._first_visible_optional(
            page,
            [
                page.locator("[data-cy='adultRange']"),
                page.locator("[data-cy='adults-1']"),
                page.locator("[data-cy='travelClass-0']"),
                page.locator("[data-cy='travellerApplyBtn']"),
            ],
            timeout_ms=700,
        )
        return marker is not None

    async def _select_mmt_adult_count(self, page: Page, adults: int) -> bool:
        return bool(
            await page.evaluate(
                """
                (adults) => {
                  const wanted = String(Math.max(1, Math.min(Number(adults) || 1, 9)));
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
                  };

                  const directSelectors = [
                    `[data-cy='adults-${wanted}']`,
                    `[data-cy='adult-${wanted}']`,
                    `[data-cy='traveller-adults-${wanted}']`,
                    `[data-testid='adults-${wanted}']`
                  ];
                  for (const selector of directSelectors) {
                    const element = document.querySelector(selector);
                    if (element && visible(element)) {
                      element.click();
                      return true;
                    }
                  }

                  const adultLabel = Array.from(document.querySelectorAll("p, div, span, label"))
                    .filter(visible)
                    .find((element) => /ADULTS|Adults/i.test(element.textContent || ""));
                  const labelRect = adultLabel ? adultLabel.getBoundingClientRect() : { top: 0, left: 0 };
                  const panel = adultLabel?.closest(".appendBottom20, .guestCounterWrap, .travellers, .flightTravllers")
                    || adultLabel?.parentElement?.parentElement
                    || document.body;
                  const candidates = Array.from(panel.querySelectorAll("li, button, span"))
                    .filter(visible)
                    .filter((element) => (element.innerText || element.textContent || "").trim() === wanted)
                    .map((element) => {
                      const rect = element.getBoundingClientRect();
                      return {
                        element,
                        score: Math.abs(rect.top - labelRect.top) + Math.abs(rect.left - labelRect.left) / 5
                      };
                    })
                    .sort((a, b) => a.score - b.score);

                  if (candidates.length) {
                    candidates[0].element.click();
                    return true;
                  }
                  return false;
                }
                """,
                adults,
            )
        )

    async def _select_mmt_cabin(self, page: Page, cabin: str) -> bool:
        cabin_value = cabin.strip().lower()
        labels: list[str]
        if "business" in cabin_value:
            labels = ["Business"]
        elif "first" in cabin_value:
            labels = ["First Class", "First"]
        elif "premium" in cabin_value:
            labels = ["Premium Economy", "Economy/Premium Economy"]
        else:
            labels = ["Economy/Premium Economy", "Economy"]

        return bool(
            await page.evaluate(
                """
                (labels) => {
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
                  };
                  const normalizedLabels = labels.map((label) => label.toLowerCase());
                  const candidates = Array.from(document.querySelectorAll("[data-cy^='travelClass'], li, button, span"))
                    .filter(visible)
                    .filter((element) => {
                      const text = (element.innerText || element.textContent || "").trim().toLowerCase();
                      return normalizedLabels.some((label) => text === label || text.includes(label));
                    });
                  if (!candidates.length) return false;
                  candidates[0].click();
                  return true;
                }
                """,
                labels,
            )
        )

    async def _apply_mmt_travelers(self, page: Page) -> bool:
        locator = await self._first_visible_optional(
            page,
            [
                page.locator("[data-cy*='apply' i]"),
                page.locator("button:has-text('APPLY'), button:has-text('Apply')"),
                page.locator(".primaryBtn:has-text('APPLY'), .primaryBtn:has-text('Apply')"),
                page.get_by_text(re.compile("^Apply$|^APPLY$|^Done$", re.I)),
            ],
            timeout_ms=1800,
        )
        if locator is not None:
            try:
                await locator.click(timeout=1800)
            except Exception:
                await locator.click(timeout=1800, force=True)
            await page.wait_for_timeout(350)
            return True

        return bool(
            await page.evaluate(
                """
                () => {
                  const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
                  };
                  const element = Array.from(document.querySelectorAll("button, a, span, div"))
                    .filter(visible)
                    .find((candidate) => /^(APPLY|Apply|Done)$/i.test((candidate.innerText || candidate.textContent || "").trim()));
                  if (!element) return false;
                  element.click();
                  return true;
                }
                """
            )
        )

    async def _click_mmt_search(self, page: Page, timeout: int) -> None:
        await self._apply_mmt_travelers(page)
        await self._click_mmt_classic_search(page)
        candidates = [
            page.locator("[data-cy='submit']"),
            page.locator("#hsw_search_button"),
            page.locator(".widgetSearchBtn"),
            page.locator("a.primaryBtn:has-text('Search'), button.primaryBtn:has-text('Search')"),
            page.get_by_role("button", name=re.compile("^search$", re.I)),
            page.get_by_role("link", name=re.compile("^search$", re.I)),
            page.get_by_text(re.compile("^search$", re.I)),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=4500)
        if locator is None:
            raise AssertionError("Could not find MakeMyTrip Search button")
        try:
            await locator.scroll_into_view_if_needed(timeout=1800)
            await locator.click(timeout=timeout)
        except Exception:
            box = await locator.bounding_box()
            if not box:
                raise
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await page.mouse.down()
            await page.wait_for_timeout(80)
            await page.mouse.up()
        await page.wait_for_timeout(1200)

    async def _wait_for_mmt_results(self, page: Page, flow: str, timeout: int) -> None:
        if await self._mmt_page_is_bare_ok(page):
            raise AssertionError("MakeMyTrip returned a bare 200-OK response instead of rendering results")

        if flow == "flights":
            candidates = [
                page.locator(".listingCard, .listingCardWrap, [class*='listingCard']"),
                page.get_by_text(re.compile("Flights from|Popular Filters|CHEAPEST|FASTEST|View Prices|VIEW PRICES|No flights|Flight Details", re.I)),
                page.locator("[data-testid*='listing' i], [data-cy*='listing' i]"),
            ]
        elif flow == "hotels":
            candidates = [
                page.get_by_text(re.compile("popular filters|sort by|price per night|hotel|view rooms|properties|showing|no hotels", re.I)),
                page.locator("[class*='hotelCard'], [class*='listing'], [data-testid*='hotel' i], [data-cy*='hotel' i]"),
            ]
        else:
            candidates = [
                page.get_by_text(re.compile("cab|taxi|popular filters|sort by|book now|select", re.I)),
                page.locator("[class*='cab'], [class*='listing'], [data-testid*='cab' i]"),
            ]

        marker = await self._first_visible_optional(page, candidates, timeout_ms=min(timeout, 12000))
        if marker is None:
            if await self._mmt_page_is_bare_ok(page):
                raise AssertionError("MakeMyTrip returned a bare 200-OK response instead of rendering results")
            raise AssertionError(f"MakeMyTrip {flow} search did not render a recognizable results UI")

    async def _mmt_page_is_bare_ok(self, page: Page) -> bool:
        try:
            text = (await page.locator("body").inner_text(timeout=1200)).strip()
        except Exception:
            return False
        compact = re.sub(r"\s+", " ", text)
        return compact in {"200-OK", "Pretty-print 200-OK"} or compact.startswith("Pretty-print 200-OK")

    async def _close_common_popups(self, page: Page) -> None:
        await self._close_mmt_login_modal(page)
        candidates = [
            page.get_by_role("button", name=re.compile("close|dismiss|later|not now", re.I)),
            page.locator("[aria-label*='close' i], .close, .modalClose, .commonModal__close"),
            page.get_by_text(re.compile("skip|not now|maybe later", re.I)),
        ]
        for candidate in candidates:
            try:
                await candidate.first.click(timeout=900)
                await page.wait_for_timeout(250)
            except Exception:
                continue
        await self._close_mmt_login_modal(page)

    async def _close_mmt_login_modal(self, page: Page) -> bool:
        if not self._is_mmt_page(page):
            return False
        for _ in range(2):
            modal = await self._first_visible_optional(
                page,
                [
                    page.locator("[data-cy='outsideModal']"),
                    page.locator(".modalLogin"),
                    page.locator(".imageSliderModal"),
                ],
                timeout_ms=500,
            )
            if modal is None:
                return False
            box = await modal.bounding_box()
            viewport = page.viewport_size or {"width": 1440, "height": 980}
            if box:
                x = min(viewport["width"] - 16, box["x"] + box["width"] + 28)
                y = max(16, box["y"] + 16)
            else:
                x = min(viewport["width"] - 16, 1195)
                y = 220
            try:
                await page.mouse.click(x, y)
                await page.wait_for_timeout(500)
            except Exception:
                pass
            still_open = await self._first_visible_optional(
                page,
                [
                    page.locator("[data-cy='outsideModal']"),
                    page.locator(".modalLogin"),
                    page.locator(".imageSliderModal"),
                ],
                timeout_ms=350,
            )
            if still_open is None:
                return True
        return False

    async def _click_if_visible(self, page: Page, labels: list[str], timeout_ms: int = 1500) -> bool:
        for label in labels:
            locator = await self._first_visible_optional(
                page,
                [
                    page.get_by_role("button", name=re.compile(re.escape(label), re.I)),
                    page.get_by_role("link", name=re.compile(re.escape(label), re.I)),
                    page.get_by_text(re.compile(re.escape(label), re.I)),
                ],
                timeout_ms=timeout_ms,
            )
            if locator:
                try:
                    await locator.click(timeout=timeout_ms)
                except Exception:
                    try:
                        await locator.click(timeout=timeout_ms, force=True)
                    except Exception:
                        continue
                await page.wait_for_timeout(250)
                return True
        return False

    async def _first_visible_optional(self, page: Page, candidates, timeout_ms: int = 1400):
        for candidate in candidates:
            try:
                locator = candidate.first
                await locator.wait_for(state="visible", timeout=timeout_ms)
                return locator
            except Exception:
                continue
        return None

    @staticmethod
    def _index_from_value(value: Any) -> int:
        if isinstance(value, dict):
            return int(value.get("index") or 1)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return 1

    async def _apply_filter(self, page: Page, target: str | None, value: str, timeout: int) -> None:
        escaped = re.escape(value)
        if self._is_mmt_page(page):
            if await self._apply_mmt_filter(page, target, value, timeout):
                return
            raise AssertionError(f"MakeMyTrip filter '{value}' was not visible in the current results")
        if target == "price_filter" and value.isdigit():
            try:
                price_link = page.get_by_text(re.compile(f"under.*{escaped}|below.*{escaped}", re.I)).first
                await price_link.click(timeout=timeout)
                return
            except Exception:
                pass
        locator = await resolve_locator(page, value, action="filter_results", timeout_ms=2200)
        try:
            await locator.check(timeout=timeout)
        except Exception:
            await locator.click(timeout=timeout)

    async def _apply_mmt_sort(self, page: Page, value: str, timeout: int) -> None:
        normalized = value.lower().replace("-", " ").replace("_", " ")
        if any(term in normalized for term in ["low", "cheap", "price asc"]):
            labels = ["CHEAPEST", "Cheapest", "Price - Low to High", "Lowest Price", "Price"]
        elif any(term in normalized for term in ["high", "price desc"]):
            labels = ["Price - High to Low", "Highest Price", "Price"]
        elif any(term in normalized for term in ["fast", "duration", "short"]):
            labels = ["FASTEST", "Fastest", "Duration"]
        elif "depart" in normalized:
            labels = ["Departure", "Departure Time"]
        elif "arriv" in normalized:
            labels = ["Arrival", "Arrival Time"]
        else:
            labels = ["YOU MAY PREFER", "Recommended", "Popularity"]

        for label in labels:
            label_pattern = f"^{re.escape(label)}" if label.lower() == "price" else f"^{re.escape(label)}$"
            locator = await self._first_visible_optional(
                page,
                [
                    page.get_by_role("button", name=re.compile(re.escape(label), re.I)),
                    page.get_by_text(re.compile(label_pattern, re.I)),
                    page.locator("button, span, div").filter(has_text=re.compile(label_pattern, re.I)),
                ],
                timeout_ms=1800,
            )
            if locator is not None:
                try:
                    await locator.click(timeout=timeout)
                except Exception:
                    await locator.click(timeout=timeout, force=True)
                await page.wait_for_timeout(900)
                return
        raise AssertionError(f"Could not find MakeMyTrip sort control for '{value}'")

    async def _apply_mmt_filter(self, page: Page, target: str | None, value: str, timeout: int) -> bool:
        escaped = re.escape(value)
        candidates = [
            page.get_by_role("checkbox", name=re.compile(escaped, re.I)),
            page.get_by_role("button", name=re.compile(escaped, re.I)),
            page.get_by_text(re.compile(f"^{escaped}$", re.I)),
            page.locator("label, span, p, div").filter(has_text=re.compile(escaped, re.I)),
        ]
        locator = await self._first_visible_optional(page, candidates, timeout_ms=2200)
        if locator is None:
            return False
        try:
            await locator.check(timeout=timeout)
        except Exception:
            try:
                await locator.click(timeout=timeout)
            except Exception:
                await locator.click(timeout=timeout, force=True)
        await page.wait_for_timeout(800)
        return True

    async def _settle_page(self, page: Page, timeout: int) -> None:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=min(timeout, 7000))
        except Exception:
            pass
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout, 5000))
        except Exception:
            pass
        await page.wait_for_timeout(450)

    async def _handle_common_interstitials(self, page: Page) -> None:
        """Handle non-auth public gates that block the page, without bypassing security."""

        candidates = [
            page.get_by_role("button", name=re.compile("continue shopping|continue", re.I)),
            page.get_by_text(re.compile("continue shopping", re.I)),
        ]
        for candidate in candidates:
            try:
                locator = candidate.first
                await locator.wait_for(state="visible", timeout=700)
                await locator.click(timeout=1500)
                await self._settle_page(page, 5000)
                return
            except Exception:
                continue

    async def _with_page_evidence(self, page: Page, message: str) -> str:
        try:
            title = await page.title()
        except Exception:
            title = ""
        url = page.url
        details = []
        if title:
            details.append(f"title='{title[:90]}'")
        if url:
            details.append(f"url={url[:180]}")
        return f"{message} | Evidence: {'; '.join(details)}" if details else message

    @staticmethod
    def _is_amazon_page(page: Page) -> bool:
        return "amazon." in page.url.lower()

    @staticmethod
    def _is_mmt_page(page: Page) -> bool:
        return "makemytrip.com" in page.url.lower()

    @staticmethod
    def _sort_value(value: str) -> str:
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        mapping = {
            "price_low_to_high": "price-asc-rank",
            "low_to_high": "price-asc-rank",
            "lowest": "price-asc-rank",
            "price_high_to_low": "price-desc-rank",
            "high_to_low": "price-desc-rank",
            "highest": "price-desc-rank",
            "customer_review": "review-rank",
            "reviews": "review-rank",
            "newest": "date-desc-rank",
            "featured": "relevanceblender",
        }
        return mapping.get(normalized, value)

    @staticmethod
    def _sort_label(value: str) -> str:
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        if "low" in normalized:
            return "Price: Low to High"
        if "high" in normalized:
            return "Price: High to Low"
        if "review" in normalized:
            return "Avg. Customer Review"
        if "new" in normalized:
            return "Newest Arrivals"
        return "Featured"

    async def _login(self, page: Page, value: Any, timeout: int) -> None:
        credentials = value if isinstance(value, dict) else {}
        username = credentials.get("username") or credentials.get("email")
        password = credentials.get("password")
        if not username or not password:
            raise ValueError("Login requires username/email and password in the prompt or a saved session")

        user_locator = await resolve_locator(page, "username", action="type")
        await user_locator.fill(str(username), timeout=timeout)
        password_locator = await resolve_locator(page, "password", action="type")
        await password_locator.fill(str(password), timeout=timeout)
        button = await resolve_locator(page, "login_button", action="click")
        await button.click(timeout=timeout)
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)

    async def _save_storage_state(self, context: BrowserContext, path: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(target))

    async def _capture_failure(self, page: Page, run_id: str, index: int) -> str | None:
        try:
            return await self._screenshot(page, run_id, index, "failure")
        except Exception:
            return None

    async def _screenshot(self, page: Page, run_id: str, index: int, label: str) -> str:
        filename = f"{run_id}-step-{index}-{label}.png"
        path = settings.SCREENSHOTS_DIR / filename
        await page.screenshot(path=str(path), full_page=True)
        return str(path)

    @staticmethod
    def _normalize_url(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("open_url requires a URL")
        if value.startswith(("http://", "https://")):
            return value
        return f"https://{value}"

    @staticmethod
    def _normalize_mmt_entry_url(value: str) -> str:
        lowered = value.lower()
        if "makemytrip.com" not in lowered:
            return value
        safe_landing_paths = ("/flights", "/flight/")
        if any(path in lowered for path in safe_landing_paths) and "/flight/search" not in lowered:
            return value
        return "https://www.makemytrip.com/flights/"

    @staticmethod
    def _safe_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _mmt_url_date(value: str) -> str | None:
        try:
            parsed = datetime.fromisoformat(value).date()
        except ValueError:
            return None
        return parsed.strftime("%d/%m/%Y")

    @staticmethod
    def _safe_value(value: Any) -> str:
        try:
            return json.dumps(value)
        except TypeError:
            return str(value)
