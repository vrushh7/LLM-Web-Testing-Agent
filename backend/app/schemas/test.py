from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class BrowserName(str, Enum):
    chromium = "chromium"
    firefox = "firefox"
    webkit = "webkit"


class StepAction(str, Enum):
    open_url = "open_url"
    click = "click"
    type = "type"
    search = "search"
    wait = "wait"
    scroll = "scroll"
    screenshot = "screenshot"
    verify_text = "verify_text"
    verify_element = "verify_element"
    add_to_cart = "add_to_cart"
    login = "login"
    hover = "hover"
    select_dropdown = "select_dropdown"
    press_key = "press_key"
    sort_results = "sort_results"
    filter_results = "filter_results"
    verify_url = "verify_url"
    open_product = "open_product"
    set_quantity = "set_quantity"
    buy_now = "buy_now"
    click_button = "click_button"
    signup = "signup"
    search_flights = "search_flights"
    search_hotels = "search_hotels"
    search_cabs = "search_cabs"


class TestStep(BaseModel):
    action: StepAction
    target: str | None = Field(default=None, max_length=500)
    value: Any | None = None
    timeout_ms: int | None = Field(default=None, ge=250, le=60000)
    assertion: str | None = Field(default=None, max_length=500)

    @field_validator("target")
    @classmethod
    def blank_target_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class TestRunCreate(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    base_url: str | None = Field(default=None, max_length=500)
    session_id: str | None = Field(default=None, max_length=80)
    save_session_name: str | None = Field(default=None, max_length=100)
    browser: BrowserName = BrowserName.chromium
    headless: bool | None = None
    max_retries: int | None = Field(default=None, ge=0, le=5)

    @field_validator("prompt")
    @classmethod
    def trim_prompt(cls, value: str) -> str:
        return value.strip()


class RunQueuedResponse(BaseModel):
    run_id: str
    status: str
    websocket_url: str


class StepResultRead(BaseModel):
    id: int
    step_index: int
    action: str
    target: str | None
    value: Any | None
    status: str
    message: str
    screenshot_url: str | None
    duration_ms: int
    started_at: str
    ended_at: str


class TestRunRead(BaseModel):
    id: str
    prompt: str
    base_url: str | None
    status: str
    browser: str
    session_id: str | None
    total_steps: int
    passed_steps: int
    failed_steps: int
    report_url: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    ended_at: str | None
    steps: list[StepResultRead] = []


class SessionRead(BaseModel):
    id: str
    name: str
    browser: str
    created_at: str
    last_used_at: str | None


class RunStatus(str, Enum):
    queued = "queued"
    planning = "planning"
    executing = "executing"
    passed = "passed"
    failed = "failed"
    cancelled = "cancelled"


class RunEvent(BaseModel):
    run_id: str
    type: Literal["status", "log", "step_started", "step_finished", "report"]
    message: str
    status: str | None = None
    step_index: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
