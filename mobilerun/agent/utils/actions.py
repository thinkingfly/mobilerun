"""Action functions for device interaction.

Each function receives ``ctx: ActionContext`` as a keyword argument and
interacts with the device via ``ctx.driver``, resolves UI elements via
``ctx.ui``, and accesses shared state via ``ctx.shared_state``.
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from mobilerun.agent.action_context import ActionContext

from mobilerun.agent.action_result import ActionResult
from mobilerun.agent.oneflows.app_starter_workflow import AppStarter

logger = logging.getLogger("mobilerun")

_MACRO_FOCUS_SETTLE_SECONDS = 0.5

# ---------------------------------------------------------------------------
# Repeated-click guard
# ---------------------------------------------------------------------------
# Tracks recent (x, y) click coordinates per agent to detect loops.
# Key: id(ctx.shared_state), Value: list of (x, y) tuples (most recent last).
_RECENT_CLICKS: dict[int, list[tuple[int, int]]] = {}
_CLICK_REPEAT_THRESHOLD = 3  # block after this many identical consecutive clicks
_CLICK_WINDOW = 30  # pixels — clicks within this radius count as "same spot"


def _is_repeated_click(ctx: "ActionContext", x: int, y: int) -> bool:
    """Return True if (x, y) is within _CLICK_WINDOW of the last N clicks."""
    key = id(ctx.shared_state)
    history = _RECENT_CLICKS.get(key, [])
    if len(history) < _CLICK_REPEAT_THRESHOLD:
        return False
    recent = history[-_CLICK_REPEAT_THRESHOLD:]
    return all(abs(rx - x) <= _CLICK_WINDOW and abs(ry - y) <= _CLICK_WINDOW for rx, ry in recent)


def _record_click(ctx: "ActionContext", x: int, y: int) -> None:
    """Record a click coordinate for repeat detection."""
    key = id(ctx.shared_state)
    history = _RECENT_CLICKS.setdefault(key, [])
    history.append((x, y))
    # Keep only the last 10 clicks
    if len(history) > 10:
        _RECENT_CLICKS[key] = history[-10:]


def _clear_click_history(ctx: "ActionContext") -> None:
    """Reset click history (called after a non-click action succeeds)."""
    key = id(ctx.shared_state)
    _RECENT_CLICKS.pop(key, None)


# ---------------------------------------------------------------------------
# Core UI actions
# ---------------------------------------------------------------------------


def _uses_screenshot_only_coordinates(ctx: "ActionContext") -> bool:
    return bool(getattr(ctx.state_provider, "requires_coordinate_tools", False))


def _screenshot_only_coordinate_error(ctx: "ActionContext") -> str:
    width = getattr(ctx.ui, "screen_width", None)
    height = getattr(ctx.ui, "screen_height", None)
    if width and height:
        return (
            f"Coordinates must be inside the screenshot size {width}x{height} "
            "in screenshot-only mode. Observe the screenshot and retry with "
            "pixel coordinates inside the image."
        )
    return (
        "Coordinates must be inside the screenshot bounds in screenshot-only mode. "
        "Observe the screenshot and retry with pixel coordinates inside the image."
    )


def _validate_screenshot_only_point(
    x: int | float, y: int | float, *, ctx: "ActionContext"
) -> None:
    if not _uses_screenshot_only_coordinates(ctx):
        return
    try:
        width = float(ctx.ui.screen_width)
        height = float(ctx.ui.screen_height)
        px = float(x)
        py = float(y)
    except TypeError as exc:
        raise ValueError(_screenshot_only_coordinate_error(ctx)) from exc
    except ValueError as exc:
        raise ValueError(_screenshot_only_coordinate_error(ctx)) from exc

    out_of_range = (
        width <= 0 or height <= 0 or px < 0 or px >= width or py < 0 or py >= height
    )
    if out_of_range:
        raise ValueError(_screenshot_only_coordinate_error(ctx))


def _convert_action_point(
    x: int | float, y: int | float, *, ctx: "ActionContext"
) -> tuple[int, int]:
    _validate_screenshot_only_point(x, y, ctx=ctx)
    abs_x, abs_y = ctx.ui.convert_point(x, y)
    return int(round(abs_x)), int(round(abs_y))


def _macro_recorder(ctx: "ActionContext"):
    return getattr(ctx, "macro_recorder", None)


def _record_macro_action(
    ctx: "ActionContext",
    action: dict,
    *,
    pre_ui=None,
) -> None:
    recorder = _macro_recorder(ctx)
    if recorder is None:
        return
    recorder.record_action(
        action,
        pre_ui=pre_ui if pre_ui is not None else getattr(ctx, "ui", None),
    )


async def _macro_pre_ui(ctx: "ActionContext"):
    if _macro_recorder(ctx) is None:
        return getattr(ctx, "ui", None)
    state_provider = getattr(ctx, "state_provider", None)
    if state_provider is None or not hasattr(state_provider, "get_state"):
        return getattr(ctx, "ui", None)
    try:
        return await state_provider.get_state()
    except Exception as e:
        logger.debug(f"Failed to refresh macro pre-state: {e}")
        return getattr(ctx, "ui", None)


async def _macro_pre_ui_after_focus_tap(ctx: "ActionContext"):
    if _macro_recorder(ctx) is not None:
        await asyncio.sleep(_MACRO_FOCUS_SETTLE_SECONDS)
    return await _macro_pre_ui(ctx)


def _driver_log_length(ctx: "ActionContext") -> int | None:
    log = getattr(getattr(ctx, "driver", None), "log", None)
    if isinstance(log, list):
        return len(log)
    return None


def _record_driver_log_delta(
    ctx: "ActionContext", before: int | None, *, pre_ui=None
) -> None:
    if before is None:
        return
    log = getattr(getattr(ctx, "driver", None), "log", None)
    if not isinstance(log, list):
        return
    for raw_action in log[before:]:
        _record_macro_action(ctx, dict(raw_action), pre_ui=pre_ui)


async def click(index: int, *, ctx: "ActionContext") -> ActionResult:
    """Click the element with the given index."""
    try:
        x, y = ctx.ui.get_element_coords(index)

        if _is_repeated_click(ctx, x, y):
            _clear_click_history(ctx)
            try:
                await ctx.driver.press_button("back")
            except Exception:
                pass
            return ActionResult(
                success=False,
                summary=(
                    f"Clicked index {index} at ({x}, {y}) — BLOCKED: same spot tapped "
                    f"{_CLICK_REPEAT_THRESHOLD}+ times. I pressed BACK for you. "
                    "Try a different approach: system_button, open_app, swipe, or different index."
                ),
            )

        pre_ui = await _macro_pre_ui(ctx)
        await ctx.driver.tap(x, y)
        _record_click(ctx, x, y)
        _record_macro_action(
            ctx,
            {"action_type": "tap", "x": x, "y": y},
            pre_ui=pre_ui,
        )

        info = ctx.ui.get_element_info(index)
        detail_parts = [
            f"Text: '{info.get('text', 'No text')}'",
            f"Class: {info.get('className', 'Unknown class')}",
            f"Type: {info.get('type', 'unknown')}",
        ]
        if info.get("child_texts"):
            detail_parts.append(f"Contains text: {' | '.join(info['child_texts'])}")
        detail_parts.append(f"Coordinates: ({x}, {y})")

        return ActionResult(
            success=True, summary=f"Clicked on {' | '.join(detail_parts)}"
        )
    except ValueError as e:
        return ActionResult(
            success=False, summary=f"Failed to click element at index {index}: {e}"
        )


async def long_press(index: int, *, ctx: "ActionContext") -> ActionResult:
    """Long press the element with the given index."""
    try:
        pre_ui = await _macro_pre_ui(ctx)
        x, y = ctx.ui.get_element_coords(index)
        await ctx.driver.swipe(x, y, x, y, 1000)
        _record_macro_action(
            ctx,
            {
                "action_type": "swipe",
                "start_x": x,
                "start_y": y,
                "end_x": x,
                "end_y": y,
                "duration_ms": 1000,
            },
            pre_ui=pre_ui,
        )
        return ActionResult(
            success=True, summary=f"Long pressed element at index {index} at ({x}, {y})"
        )
    except ValueError as e:
        return ActionResult(
            success=False, summary=f"Failed to long press element at index {index}: {e}"
        )


async def long_press_at(x: int, y: int, *, ctx: "ActionContext") -> ActionResult:
    """Long press at screen coordinates."""
    try:
        pre_ui = await _macro_pre_ui(ctx)
        abs_x, abs_y = _convert_action_point(x, y, ctx=ctx)
        await ctx.driver.swipe(abs_x, abs_y, abs_x, abs_y, 1000)
        _record_macro_action(
            ctx,
            {
                "action_type": "swipe",
                "start_x": abs_x,
                "start_y": abs_y,
                "end_x": abs_x,
                "end_y": abs_y,
                "duration_ms": 1000,
            },
            pre_ui=pre_ui,
        )
        return ActionResult(success=True, summary=f"Long pressed at ({abs_x}, {abs_y})")
    except Exception as e:
        return ActionResult(
            success=False, summary=f"Failed to long press at ({x}, {y}): {e}"
        )


async def click_at(x: int, y: int, *, ctx: "ActionContext") -> ActionResult:
    """Click at screen coordinates.

    Detects repeated clicks to the same spot and returns a failure to force
    the agent to try a different approach.  When triggered, automatically
    presses the BACK button to dismiss any keyboard or popup that may be
    blocking progress.
    """
    try:
        abs_x, abs_y = _convert_action_point(x, y, ctx=ctx)

        if _is_repeated_click(ctx, abs_x, abs_y):
            _clear_click_history(ctx)
            # Auto-press BACK to dismiss keyboard / popup
            try:
                await ctx.driver.press_button("back")
            except Exception:
                pass
            return ActionResult(
                success=False,
                summary=(
                    f"Tapped at ({abs_x}, {abs_y}) — BLOCKED: you have tapped this same "
                    f"spot {_CLICK_REPEAT_THRESHOLD}+ times with no effect. "
                    "I pressed BACK for you to dismiss any keyboard or popup. "
                    "You MUST now do something DIFFERENT: use open_app to launch an app, "
                    "swipe to scroll, system_button to navigate, or click a COMPLETELY "
                    "different area. Do NOT click near this position again."
                ),
            )

        pre_ui = await _macro_pre_ui(ctx)
        await ctx.driver.tap(abs_x, abs_y)
        _record_click(ctx, abs_x, abs_y)
        _record_macro_action(
            ctx,
            {"action_type": "tap", "x": abs_x, "y": abs_y},
            pre_ui=pre_ui,
        )
        return ActionResult(success=True, summary=f"Tapped at ({abs_x}, {abs_y})")
    except Exception as e:
        return ActionResult(success=False, summary=f"Failed to tap at ({x}, {y}): {e}")


async def click_area(
    x1: int, y1: int, x2: int, y2: int, *, ctx: "ActionContext"
) -> ActionResult:
    """Click center of area."""
    try:
        _validate_screenshot_only_point(x1, y1, ctx=ctx)
        _validate_screenshot_only_point(x2, y2, ctx=ctx)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        abs_x, abs_y = _convert_action_point(cx, cy, ctx=ctx)

        if _is_repeated_click(ctx, abs_x, abs_y):
            _clear_click_history(ctx)
            try:
                await ctx.driver.press_button("back")
            except Exception:
                pass
            return ActionResult(
                success=False,
                summary=(
                    f"Tapped area center ({abs_x}, {abs_y}) — BLOCKED: same spot tapped "
                    f"{_CLICK_REPEAT_THRESHOLD}+ times. I pressed BACK for you. "
                    "Try a different approach."
                ),
            )

        pre_ui = await _macro_pre_ui(ctx)
        await ctx.driver.tap(abs_x, abs_y)
        _record_click(ctx, abs_x, abs_y)
        _record_macro_action(
            ctx,
            {"action_type": "tap", "x": abs_x, "y": abs_y},
            pre_ui=pre_ui,
        )
        return ActionResult(
            success=True, summary=f"Tapped center of area at ({abs_x}, {abs_y})"
        )
    except Exception as e:
        return ActionResult(success=False, summary=f"Failed to tap area center: {e}")


async def type_text(
    text: str, index: int | None = None, clear: bool = False, *, ctx: "ActionContext"
) -> ActionResult:
    """Type text into an indexed element or the currently focused input."""
    try:
        _clear_click_history(ctx)
        pre_ui = await _macro_pre_ui(ctx)
        if index is not None and index != -1:
            x, y = ctx.ui.get_element_coords(index)
            await ctx.driver.tap(x, y)
            _record_macro_action(
                ctx,
                {"action_type": "tap", "x": x, "y": y},
                pre_ui=pre_ui,
            )
            pre_ui = await _macro_pre_ui_after_focus_tap(ctx)

        success = await ctx.driver.input_text(text, clear)
        if success:
            _record_macro_action(
                ctx,
                {"action_type": "input_text", "text": text, "clear": clear},
                pre_ui=pre_ui,
            )
            return ActionResult(
                success=True, summary=f"Text typed successfully (clear={clear})"
            )
        else:
            return ActionResult(
                success=False, summary="Failed to type text: input failed"
            )
    except Exception as e:
        return ActionResult(success=False, summary=f"Failed to type text: {e}")


async def type_text_direct(
    text: str, clear: bool = False, *, ctx: "ActionContext"
) -> ActionResult:
    """Type text into the currently focused input."""
    try:
        _clear_click_history(ctx)
        pre_ui = await _macro_pre_ui(ctx)
        success = await ctx.driver.input_text(text, clear)
        if success:
            _record_macro_action(
                ctx,
                {"action_type": "input_text", "text": text, "clear": clear},
                pre_ui=pre_ui,
            )
            return ActionResult(
                success=True, summary=f"Text typed successfully (clear={clear})"
            )
        return ActionResult(success=False, summary="Failed to type text: input failed")
    except Exception as e:
        return ActionResult(success=False, summary=f"Failed to type text: {e}")


async def system_button(button: str, *, ctx: "ActionContext") -> ActionResult:
    """Press a system button (back, home, or enter)."""
    try:
        _clear_click_history(ctx)
        pre_ui = await _macro_pre_ui(ctx)
        await ctx.driver.press_button(button)
        _record_macro_action(
            ctx,
            {"action_type": "button_press", "button": button},
            pre_ui=pre_ui,
        )
        return ActionResult(success=True, summary=f"Pressed {button.upper()} button")
    except ValueError as e:
        return ActionResult(success=False, summary=str(e))
    except Exception as e:
        return ActionResult(
            success=False,
            summary=f"Failed to press {button} button: {e.__class__.__name__}: {e}",
        )


async def swipe(
    coordinate: List[int],
    coordinate2: List[int],
    duration: float = 1.0,
    *,
    ctx: "ActionContext",
) -> ActionResult:
    """Swipe from one coordinate to another."""
    if not isinstance(coordinate, list) or len(coordinate) != 2:
        return ActionResult(
            success=False,
            summary=f"Failed: coordinate must be a list of 2 integers, got: {coordinate}",
        )
    if not isinstance(coordinate2, list) or len(coordinate2) != 2:
        return ActionResult(
            success=False,
            summary=f"Failed: coordinate2 must be a list of 2 integers, got: {coordinate2}",
        )

    try:
        _clear_click_history(ctx)
        pre_ui = await _macro_pre_ui(ctx)
        start_x, start_y = _convert_action_point(*coordinate, ctx=ctx)
        end_x, end_y = _convert_action_point(*coordinate2, ctx=ctx)
        duration_ms = int(duration * 1000)
        await ctx.driver.swipe(start_x, start_y, end_x, end_y, duration_ms=duration_ms)
        _record_macro_action(
            ctx,
            {
                "action_type": "swipe",
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "duration_ms": duration_ms,
            },
            pre_ui=pre_ui,
        )
        return ActionResult(
            success=True,
            summary=f"Swiped from ({start_x}, {start_y}) to ({end_x}, {end_y})",
        )
    except Exception as e:
        return ActionResult(success=False, summary=f"Failed to swipe: {e}")


_PACKAGE_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$")


def _is_package_name(text: str) -> bool:
    """Return True if *text* looks like an Android/iOS package name."""
    return bool(_PACKAGE_NAME_RE.match(text))


async def open_app(text: str, *, ctx: "ActionContext") -> ActionResult:
    """Open an app by its name or package name.

    If *text* looks like a fully-qualified package name (e.g.
    ``com.tencent.mm``), skip the LLM-based app matching and launch
    directly via ``start_app``.
    """
    if _is_package_name(text):
        # Direct package name — skip LLM matching
        logger.info(f"open_app: direct package name '{text}', launching directly")
        pre_ui = await _macro_pre_ui(ctx)
        driver_log_before = _driver_log_length(ctx)
        try:
            result = await ctx.driver.start_app(text)
            await asyncio.sleep(1)
            if isinstance(result, str) and result.lower().startswith("failed"):
                return ActionResult(success=False, summary=result)
            _record_driver_log_delta(ctx, driver_log_before, pre_ui=pre_ui)
            return ActionResult(success=True, summary=str(result))
        except Exception as e:
            return ActionResult(
                success=False,
                summary=f"Failed to open app '{text}': {e.__class__.__name__}: {e}",
            )

    if ctx.app_opener_llm is None:
        return ActionResult(
            success=False,
            summary="Failed: app_opener_llm not configured.",
        )

    workflow = AppStarter(
        driver=ctx.driver,
        llm=ctx.app_opener_llm,
        timeout=60,
        stream=ctx.streaming,
        verbose=False,
    )

    pre_ui = await _macro_pre_ui(ctx)
    driver_log_before = _driver_log_length(ctx)
    result = await workflow.run(app_description=text)
    await asyncio.sleep(1)

    if isinstance(result, str) and "could not open app" in result.lower():
        return ActionResult(success=False, summary=result)
    _record_driver_log_delta(ctx, driver_log_before, pre_ui=pre_ui)
    return ActionResult(success=True, summary=str(result))


async def open_bundle_id(
    bundle_id: str | None = None,
    app_id: str | None = None,
    *,
    ctx: "ActionContext",
) -> ActionResult:
    """Open an app by exact package name, app id, or iOS bundle identifier."""
    identifier = app_id or bundle_id
    if not identifier:
        return ActionResult(
            success=False,
            summary="Failed to open app: exact app identifier is required.",
        )

    hint = (
        "Maybe you got the wrong app identifier. You could try using swipes and "
        "search to find the app."
    )
    try:
        pre_ui = await _macro_pre_ui(ctx)
        result = await ctx.driver.start_app(identifier)
        await asyncio.sleep(1)
        if isinstance(result, str) and result.lower().startswith("failed"):
            return ActionResult(
                success=False,
                summary=f"Failed to open app '{identifier}': {result}\n{hint}",
            )
        _record_macro_action(
            ctx,
            {"action_type": "start_app", "package": identifier, "activity": None},
            pre_ui=pre_ui,
        )
        return ActionResult(success=True, summary=str(result))
    except Exception as e:
        return ActionResult(
            success=False,
            summary=f"Failed to open app '{identifier}': {e.__class__.__name__}: {e}\n{hint}",
        )


async def wait(duration: float = 1.0, *, ctx: "ActionContext") -> ActionResult:
    """Wait for a specified duration in seconds."""
    pre_ui = await _macro_pre_ui(ctx)
    await asyncio.sleep(duration)
    recorder = _macro_recorder(ctx)
    if recorder is not None:
        recorder.record_wait(duration, pre_ui=pre_ui)
    return ActionResult(success=True, summary=f"Waited for {duration} seconds")


# ---------------------------------------------------------------------------
# State / memory actions
# ---------------------------------------------------------------------------


async def complete(
    success: bool, reason: str = "", message: str = "", *, ctx: "ActionContext"
) -> ActionResult:
    """Mark the task as complete.

    Accepts both ``reason`` and ``message`` — FastAgent XML prompt uses
    ``message``, action signature uses ``reason``.
    """
    await ctx.shared_state.complete(success, reason=reason, message=message)
    return ActionResult(success=True, summary=ctx.shared_state.answer)


async def type_secret(
    secret_id: str, index: int, *, ctx: "ActionContext"
) -> ActionResult:
    """Type a secret credential into an input field without exposing the value."""
    if ctx.credential_manager is None:
        return ActionResult(
            success=False,
            summary="Failed to type secret: Credential manager not initialized. Enable credentials in config.yaml",
        )

    try:
        secret_value = await ctx.credential_manager.resolve_key(secret_id)
        pre_ui = await _macro_pre_ui(ctx)

        # Tap the element first if a specific index is given
        if index != -1:
            x, y = ctx.ui.get_element_coords(index)
            await ctx.driver.tap(x, y)
            _record_macro_action(
                ctx,
                {"action_type": "tap", "x": x, "y": y},
                pre_ui=pre_ui,
            )
            pre_ui = await _macro_pre_ui_after_focus_tap(ctx)

        ok = await ctx.driver.input_text(secret_value)
        if ok:
            _record_macro_action(
                ctx,
                {
                    "action_type": "type_secret",
                    "secret_id": secret_id,
                    "clear": False,
                },
                pre_ui=pre_ui,
            )
            return ActionResult(
                success=True,
                summary=f"Successfully typed secret '{secret_id}' into element {index}",
            )
        else:
            return ActionResult(
                success=False,
                summary=f"Failed to type secret '{secret_id}': input failed",
            )
    except Exception as e:
        logger.error(f"Failed to type secret '{secret_id}': {e}")
        available = (
            await ctx.credential_manager.get_keys() if ctx.credential_manager else []
        )
        return ActionResult(
            success=False,
            summary=f"Failed to type secret '{secret_id}': not found. Available: {available}",
        )
