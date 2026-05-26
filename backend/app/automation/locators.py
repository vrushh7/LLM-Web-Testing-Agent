import re
from collections.abc import Iterable

from playwright.async_api import Locator, Page


class LocatorResolutionError(RuntimeError):
    pass


def _normalized(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _looks_like_selector(target: str) -> bool:
    starts = ("#", ".", "[", "css=", "xpath=", "//", "input", "button", "a[", "select", "textarea")
    return target.strip().startswith(starts) or ">>" in target


def _selector_locator(page: Page, target: str) -> Locator:
    target = target.strip()
    if target.startswith("//"):
        return page.locator(f"xpath={target}")
    return page.locator(target)


async def first_visible(candidates: Iterable[Locator], timeout_ms: int = 1400) -> Locator:
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            locator = candidate.first
            await locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception as exc:
            last_error = exc
    raise LocatorResolutionError(str(last_error) if last_error else "No locator candidates matched")


async def resolve_locator(page: Page, target: str | None, action: str = "click", timeout_ms: int = 1400) -> Locator:
    """Resolve semantic names, text, roles, labels, and CSS selectors into a Playwright locator."""

    if not target:
        raise LocatorResolutionError(f"No target provided for {action}")

    raw = target.strip()
    key = _normalized(raw)
    escaped = re.escape(raw)
    safe_attr = raw.replace("\\", "\\\\").replace("'", "\\'")
    candidates: list[Locator] = []

    if _looks_like_selector(raw):
        candidates.append(_selector_locator(page, raw.replace("css=", "", 1)))

    if key in {"search", "searchbox", "search_box", "search_input"}:
        candidates.extend(
            [
                page.get_by_role("searchbox"),
                page.locator("input[type='search']"),
                page.locator("input[name*='search']"),
                page.locator("input[id*='search']"),
                page.locator("input[placeholder*='Search']"),
                page.locator("textarea[placeholder*='Search']"),
            ]
        )
    elif key in {"search_button", "search_submit", "searchbutton"}:
        candidates.extend(
            [
                page.locator("input[type='submit'][value*='Go']"),
                page.locator("input[type='submit'][aria-label*='Search']"),
                page.locator("#nav-search-submit-button"),
                page.get_by_role("button", name=re.compile("search|go", re.I)),
            ]
        )
    elif key in {"first_product", "first_result", "product", "product_result"}:
        candidates.extend(
            [
                page.locator("[data-component-type='s-search-result'] h2 a"),
                page.locator("[data-component-type='s-search-result'] a.a-link-normal.s-no-outline"),
                page.locator("a[href*='/dp/']"),
                page.locator("a[href*='/product/']"),
                page.locator(".product a, [data-testid*='product'] a"),
            ]
        )
    elif key in {"add_to_cart", "add_to_cart_button", "cart_button"}:
        candidates.extend(
            [
                page.locator("#add-to-cart-button"),
                page.locator("input[name='submit.add-to-cart']"),
                page.locator("#submit.add-to-cart"),
                page.locator("button[name='submit.add-to-cart']"),
                page.get_by_role("button", name=re.compile("^add\\s+to\\s+cart$", re.I)),
                page.get_by_text(re.compile("^add\\s+to\\s+cart$", re.I)),
            ]
        )
    elif key in {"buy_now", "buy_now_button"}:
        candidates.extend(
            [
                page.locator("#buy-now-button"),
                page.locator("input[name='submit.buy-now']"),
                page.get_by_role("button", name=re.compile("buy now|buy", re.I)),
                page.get_by_text(re.compile("buy now", re.I)),
            ]
        )
    elif key in {"quantity", "qty"}:
        candidates.extend(
            [
                page.locator("#quantity"),
                page.locator("select[name='quantity']"),
                page.get_by_label(re.compile("quantity|qty", re.I)),
                page.get_by_role("combobox", name=re.compile("quantity|qty", re.I)),
            ]
        )
    elif key in {"checkout", "checkout_button", "proceed_to_checkout"}:
        candidates.extend(
            [
                page.get_by_role("button", name=re.compile("checkout|proceed", re.I)),
                page.get_by_role("link", name=re.compile("checkout|proceed", re.I)),
                page.locator("input[name*='checkout']"),
            ]
        )
    elif key in {"sort", "sort_dropdown", "sort_results"}:
        candidates.extend(
            [
                page.locator("#s-result-sort-select"),
                page.locator("select[name='s']"),
                page.get_by_label(re.compile("sort", re.I)),
                page.locator("select").filter(has_text=re.compile("price|featured|review|new", re.I)),
            ]
        )
    elif key in {"brand_filter", "price_filter", "rating_filter", "category_filter", "filter"}:
        candidates.extend(
            [
                page.get_by_role("checkbox", name=re.compile(escaped, re.I)),
                page.get_by_role("link", name=re.compile(escaped, re.I)),
                page.get_by_text(re.compile(escaped, re.I)),
            ]
        )
    elif key in {"username", "email", "user"}:
        candidates.extend(
            [
                page.get_by_label(re.compile("email|username|user", re.I)),
                page.get_by_placeholder(re.compile("email|username|user", re.I)),
                page.locator("input[type='email']"),
                page.locator("input[name*='email'], input[name*='user']"),
            ]
        )
    elif key == "password":
        candidates.extend(
            [
                page.get_by_label(re.compile("password", re.I)),
                page.get_by_placeholder(re.compile("password", re.I)),
                page.locator("input[type='password']"),
            ]
        )
    elif key in {"login", "login_button", "signin", "sign_in", "submit"}:
        candidates.extend(
            [
                page.get_by_role("button", name=re.compile("log in|login|sign in|signin|submit|continue", re.I)),
                page.get_by_role("link", name=re.compile("log in|login|sign in|signin", re.I)),
                page.locator("button[type='submit'], input[type='submit']"),
            ]
        )

    candidates.extend(
        [
            page.get_by_role("button", name=re.compile(escaped, re.I)),
            page.get_by_role("link", name=re.compile(escaped, re.I)),
            page.get_by_label(re.compile(escaped, re.I)),
            page.get_by_placeholder(re.compile(escaped, re.I)),
            page.get_by_text(re.compile(escaped, re.I)),
            page.get_by_role("checkbox", name=re.compile(escaped, re.I)),
            page.locator(f"[aria-label*='{safe_attr}']"),
            page.locator(f"[data-testid*='{safe_attr}']"),
            page.locator(f"[name*='{safe_attr}']"),
            page.locator(f"[id*='{safe_attr}']"),
        ]
    )

    return await first_visible(candidates, timeout_ms=timeout_ms)
