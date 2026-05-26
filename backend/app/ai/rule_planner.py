import re
from datetime import date, timedelta

from app.schemas.test import TestStep


ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def build_rule_based_plan(prompt: str, base_url: str | None, workflow_context: str | None = None) -> list[TestStep]:
    """Deterministic fallback for common workflows when cloud LLMs are busy.

    This is not a local LLM. It is a small rule planner that preserves low-cost
    availability for ecommerce, travel, button-clicking, and form workflows.
    """

    text = prompt.lower()
    context = (workflow_context or "").lower()
    steps: list[dict] = []

    if _is_travel_prompt(text):
        steps.extend(_travel_steps(prompt, text, base_url))
        return [TestStep.model_validate(step) for step in steps]

    site_url = _site_url(text, base_url, context)
    search_term = _search_term(prompt) or _search_term(workflow_context or "")

    if site_url:
        steps.append({"action": "open_url", "value": site_url})
    if search_term and _needs_search_context(text):
        steps.append({"action": "search", "target": "searchbox", "value": search_term})

    if "sort" in text or "low to high" in text or "high to low" in text:
        steps.append({"action": "sort_results", "target": "sort_dropdown", "value": _sort_value(text)})
        steps.append({"action": "screenshot", "target": "sorted_results", "value": "Sorted results evidence"})

    filter_value = _filter_value(prompt)
    if filter_value:
        steps.append({"action": "filter_results", "target": filter_value["target"], "value": filter_value["value"]})
        steps.append({"action": "screenshot", "target": "filtered_results", "value": "Filtered results evidence"})

    product_index = _product_index(text)
    if product_index and any(word in text for word in ["product", "cart", "buy"]):
        steps.append({"action": "open_product", "target": "product_result", "value": {"index": product_index}})

    quantity = _quantity(text)

    if "buy now" in text or re.search(r"\bbuy\b", text):
        if quantity:
            steps.append({"action": "set_quantity", "target": "quantity", "value": quantity})
        steps.append({"action": "buy_now", "target": "buy_now_button"})
        steps.append({"action": "verify_url", "value": "checkout"})
    elif "add" in text and "cart" in text:
        if not product_index:
            steps.append({"action": "open_product", "target": "product_result", "value": {"index": 1}})
        if quantity:
            steps.append({"action": "set_quantity", "target": "quantity", "value": quantity})
        steps.append({"action": "add_to_cart", "target": "add_to_cart_button"})
        steps.append({"action": "verify_element", "target": "checkout_button"})
        steps.append({"action": "screenshot", "target": "cart_confirmation", "value": "Cart confirmation evidence"})

    button_text = _button_text(prompt)
    if button_text:
        steps.append({"action": "click_button", "value": button_text})

    if "verify checkout" in text:
        steps.append({"action": "verify_element", "target": "checkout_button"})

    if not steps and base_url:
        steps.append({"action": "open_url", "value": base_url})

    return [TestStep.model_validate(step) for step in steps]


def _is_travel_prompt(text: str) -> bool:
    return (
        "make my trip" in text
        or "makemytrip" in text
        or re.search(r"\b(flights?|hotels?|cabs?|taxi|taxis)\b", text) is not None
    )


def _travel_steps(prompt: str, text: str, base_url: str | None) -> list[dict]:
    if re.search(r"\bhotels?\b", text):
        steps = [{"action": "open_url", "value": base_url or "https://www.makemytrip.com/flights/"}]
        steps.append({"action": "search_hotels", "value": _hotel_payload(prompt)})
    elif re.search(r"\b(cabs?|taxi|taxis)\b", text):
        steps = [{"action": "open_url", "value": base_url or "https://www.makemytrip.com/cabs/"}]
        steps.append({"action": "search_cabs", "value": _route_payload(prompt)})
    else:
        steps = [{"action": "open_url", "value": base_url or "https://www.makemytrip.com/flights/"}]
        steps.append({"action": "search_flights", "value": _flight_payload(prompt)})

    travel_sort = _travel_sort_value(text)
    if travel_sort:
        steps.append({"action": "sort_results", "target": "travel_sort", "value": travel_sort})

    travel_filter = _travel_filter_value(prompt)
    if travel_filter:
        steps.append({"action": "filter_results", "target": travel_filter["target"], "value": travel_filter["value"]})

    steps.append({"action": "screenshot", "target": "travel_search_results", "value": "Travel search evidence"})
    return steps


def _site_url(text: str, base_url: str | None, context: str) -> str | None:
    if base_url:
        return base_url
    url_match = re.search(r"https?://[^\s,]+", text)
    if url_match:
        return url_match.group(0)
    if "amazon" in text or "amazon" in context:
        return "https://www.amazon.in"
    if "make my trip" in text or "makemytrip" in text or "makemytrip" in context:
        return "https://www.makemytrip.com"
    return None


def _needs_search_context(text: str) -> bool:
    return any(word in text for word in ["search", "product", "cart", "sort", "filter", "buy"])


def _search_term(prompt: str | None) -> str | None:
    if not prompt:
        return None
    patterns = [
        r"search(?: for)? ([^,.]+)",
        r"find ([^,.]+)",
        r"look for ([^,.]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            value = re.sub(r"\b(and|then|sort|filter|add|verify|open|buy)\b.*$", "", value, flags=re.IGNORECASE).strip()
            if value:
                return value
    if "iphone 16" in prompt.lower():
        return "iPhone 16"
    return None


def _product_index(text: str) -> int | None:
    for word, number in ORDINALS.items():
        if f"{word} product" in text:
            return number
    match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+product\b", text)
    if match:
        return max(1, int(match.group(1)))
    if "product" in text:
        return 1
    return None


def _quantity(text: str) -> int | None:
    patterns = [
        r"\bquantity\s+(\d+)\b",
        r"\bquantity\s+(?:to|as|of)\s+(\d+)\b",
        r"\bqty\s+(\d+)\b",
        r"\bqty\s+(?:to|as|of)\s+(\d+)\b",
        r"\b(\d+)\s+(?:items|pieces|pcs|units)\b",
        r"\badd\s+(\d+)\s+(?:of|items|pieces|pcs|units)\b",
        r"\badd\s+(\d+)\b",
        r"\bset\s+(?:quantity|qty)\s+(?:to|as)?\s*(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 30:
                return value
    return None


def _sort_value(text: str) -> str:
    if "high to low" in text or "highest" in text or "descending" in text:
        return "price_high_to_low"
    if "low to high" in text or "lowest" in text or "ascending" in text:
        return "price_low_to_high"
    if "review" in text or "rating" in text:
        return "customer_review"
    if "new" in text:
        return "newest"
    return "featured"


def _travel_sort_value(text: str) -> str | None:
    if "sort" not in text and not any(term in text for term in ["cheapest", "fastest", "low to high", "high to low"]):
        return None
    if "cheapest" in text or "low to high" in text or "lowest" in text:
        return "cheapest"
    if "high to low" in text or "highest" in text:
        return "price_high_to_low"
    if "fastest" in text or "shortest" in text or "duration" in text:
        return "fastest"
    return "recommended"


def _travel_filter_value(prompt: str) -> dict[str, str] | None:
    text = prompt.lower()
    if "non stop" in text or "non-stop" in text or "direct flight" in text:
        return {"target": "travel_filter", "value": "Non Stop"}
    airline_match = re.search(r"(?:airline|flight by|carrier)\s+([a-zA-Z ][a-zA-Z &.-]+)", prompt, re.IGNORECASE)
    if airline_match:
        value = re.sub(r"\b(and|then|sort|filter|search|book)\b.*$", "", airline_match.group(1), flags=re.IGNORECASE).strip()
        if value:
            return {"target": "travel_filter", "value": value}
    filter_match = re.search(r"filter(?: by)?\s+([^,.]+)", prompt, re.IGNORECASE)
    if filter_match:
        value = re.sub(r"\b(and|then|sort|search|book)\b.*$", "", filter_match.group(1), flags=re.IGNORECASE).strip()
        if value:
            return {"target": "travel_filter", "value": value}
    return None


def _filter_value(prompt: str) -> dict[str, str] | None:
    text = prompt.lower()
    brand_match = re.search(r"(?:brand|by|from)\s+([a-z0-9][a-z0-9 &-]+)", prompt, re.IGNORECASE)
    if "apple" in text:
        return {"target": "brand_filter", "value": "Apple"}
    if brand_match and "filter" in text:
        return {"target": "brand_filter", "value": brand_match.group(1).strip()}
    price_match = re.search(r"(under|below|less than)\s+(?:rs\.?|inr|₹|\$)?\s*([0-9,]+)", prompt, re.IGNORECASE)
    if price_match:
        return {"target": "price_filter", "value": price_match.group(2).replace(",", "")}
    if "4 star" in text or "four star" in text:
        return {"target": "rating_filter", "value": "4 Stars"}
    return None


def _button_text(prompt: str) -> str | None:
    match = re.search(r"click (?:the )?(.+?) button", prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _route_payload(prompt: str) -> dict[str, str]:
    match = re.search(
        r"from\s+([a-zA-Z ]+?)\s+to\s+([a-zA-Z ]+?)(?:$|,|\s+for\b|\s+with\b|\s+on\b|\s+sort\b|\s+filter\b|\s+airline\b|\s+carrier\b)",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return {"from": match.group(1).strip(), "to": match.group(2).strip()}
    return {}


def _flight_payload(prompt: str) -> dict:
    payload = _route_payload(prompt)
    adults_match = re.search(r"(\d+)\s+adults?", prompt, re.IGNORECASE)
    cabin_match = re.search(r"\b(economy|premium economy|business|first class)\b", prompt, re.IGNORECASE)
    departure_date = _extract_date(prompt, ["depart", "departure", "leaving", "on", "for"], allow_unscoped=True)
    return_date = _extract_date(prompt, ["return", "returning", "back"], allow_unscoped=False)
    if adults_match:
        payload["adults"] = int(adults_match.group(1))
    if cabin_match:
        payload["cabin"] = cabin_match.group(1).title()
    if departure_date:
        payload["departure_date"] = departure_date
    if return_date:
        payload["return_date"] = return_date
    return payload


def _hotel_payload(prompt: str) -> dict:
    location = None
    match = re.search(
        r"(?:hotel|hotels|stay|stays)\s+(?:in|at|for)\s+([a-zA-Z ]+?)(?:$|,|\s+for\b|\s+with\b|\s+from\b|\s+on\b|\s+check)",
        prompt,
        re.IGNORECASE,
    )
    if match:
        location = match.group(1).strip()
    adults_match = re.search(r"(\d+)\s+adults?", prompt, re.IGNORECASE)
    rooms_match = re.search(r"(\d+)\s+rooms?", prompt, re.IGNORECASE)
    children_match = re.search(r"(\d+)\s+children?", prompt, re.IGNORECASE)
    checkin_date = _extract_date(prompt, ["checkin", "check-in", "from", "on"], allow_unscoped=True)
    checkout_date = _extract_date(prompt, ["checkout", "check-out", "until", "to"], allow_unscoped=False)
    nights_match = re.search(r"(\d+)\s+nights?", prompt, re.IGNORECASE)
    payload: dict = {}
    if location:
        payload["location"] = location
    if adults_match:
        payload["adults"] = int(adults_match.group(1))
    if rooms_match:
        payload["rooms"] = int(rooms_match.group(1))
    if children_match:
        payload["children"] = int(children_match.group(1))
    if checkin_date:
        payload["checkin_date"] = checkin_date
    if checkout_date:
        payload["checkout_date"] = checkout_date
    elif checkin_date and nights_match:
        payload["checkout_date"] = (date.fromisoformat(checkin_date) + timedelta(days=int(nights_match.group(1)))).isoformat()
    return payload


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _extract_date(prompt: str, cues: list[str], allow_unscoped: bool) -> str | None:
    text = prompt.lower()
    today = date.today()
    if any(cue in text for cue in cues):
        if "day after tomorrow" in text:
            return (today + timedelta(days=2)).isoformat()
        if "tomorrow" in text:
            return (today + timedelta(days=1)).isoformat()
        if "today" in text:
            return today.isoformat()

    cue_pattern = "|".join(re.escape(cue) for cue in cues)
    scoped = re.search(
        rf"\b(?:{cue_pattern})(?:\s+date)?(?:\s+on|\s+for|\s+to)?\s+([a-zA-Z0-9, /\-]+)",
        prompt,
        re.IGNORECASE,
    )
    candidates = [scoped.group(1)] if scoped else []
    if allow_unscoped:
        candidates.append(prompt)
    for candidate in candidates:
        parsed = _parse_date_fragment(candidate, today)
        if parsed:
            return parsed.isoformat()
    return None


def _parse_date_fragment(value: str, today: date) -> date | None:
    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", value)
    if numeric:
        day = int(numeric.group(1))
        month = int(numeric.group(2))
        year = _year_from_text(numeric.group(3), today)
        return _future_date(year, month, day, today)

    month_names = "|".join(MONTHS)
    day_month = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})(?:\s+(\d{{2,4}}))?\b", value, re.I)
    if day_month:
        day = int(day_month.group(1))
        month = MONTHS[day_month.group(2).lower()]
        year = _year_from_text(day_month.group(3), today)
        return _future_date(year, month, day, today)

    month_day = re.search(rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{2,4}}))?\b", value, re.I)
    if month_day:
        month = MONTHS[month_day.group(1).lower()]
        day = int(month_day.group(2))
        year = _year_from_text(month_day.group(3), today)
        return _future_date(year, month, day, today)
    return None


def _year_from_text(value: str | None, today: date) -> int:
    if not value:
        return today.year
    year = int(value)
    return 2000 + year if year < 100 else year


def _future_date(year: int, month: int, day: int, today: date) -> date | None:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if parsed < today and year == today.year:
        try:
            return date(year + 1, month, day)
        except ValueError:
            return parsed
    return parsed
