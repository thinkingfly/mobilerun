"""微信专用工具 — 仅负责打开微信，后续操作交给 Agent 视觉导航。

微信屏蔽了 Accessibility/UIAutomator 服务，ADB input tap 对微信的
列表项（弹窗菜单、通讯录条目等）完全无效。因此专用工具只负责用
start_app 打开微信，剩余操作由 Agent 在 vision_only 模式下自行完成。
"""

import logging
from typing import TYPE_CHECKING

from mobilerun.agent.action_result import ActionResult

if TYPE_CHECKING:
    from mobilerun.agent.action_context import ActionContext

logger = logging.getLogger("mobilerun")

WECHAT_PACKAGE = "com.tencent.mm"


async def wechat_open(*, ctx: "ActionContext") -> ActionResult:
    """打开微信 App 并返回到主页。

    微信屏蔽了 UIAutomator，ADB tap 对列表项无效。
    打开微信后，Agent 应在 vision_only 模式下通过截图识别自行操作。
    """
    driver = ctx.driver
    try:
        # 先按两次返回确保回到干净状态
        try:
            await driver.press_button("back")
        except Exception:
            pass
        try:
            await driver.press_button("back")
        except Exception:
            pass

        # 直接通过包名打开微信
        await driver.start_app(WECHAT_PACKAGE)
        return ActionResult(
            success=True,
            summary=(
                "已打开微信。微信屏蔽了 UIAutomator 和 ADB tap 对列表项的操作，"
                "请在 vision_only 模式下通过截图识别坐标，自行完成后续操作。"
                "提示：点击通讯录tab → 新的朋友 → 搜索框 → 输入手机号 → 添加好友。"
            ),
        )
    except Exception as e:
        return ActionResult(success=False, summary=f"打开微信失败: {e}")


async def wechat_add_friend(phone_number: str, *, ctx: "ActionContext") -> ActionResult:
    """打开微信并准备好添加好友流程。

    由于 ADB tap 对微信列表项无效，此工具只负责打开微信，
    后续操作需要 Agent 在 vision 模式下自行完成。
    """
    driver = ctx.driver
    try:
        # 按两次返回回到主页
        try:
            await driver.press_button("back")
        except Exception:
            pass
        try:
            await driver.press_button("back")
        except Exception:
            pass

        await driver.start_app(WECHAT_PACKAGE)
        return ActionResult(
            success=True,
            summary=(
                f"已打开微信。下一步需要添加好友 {phone_number}。"
                "请在 vision_only 模式下操作："
                "1) 点击底部「通讯录」tab → "
                "2) 点击「新的朋友」→ "
                "3) 点击搜索框 → "
                f"4) 输入 {phone_number} → "
                "5) 点击搜索结果 → "
                "6) 点击「添加到通讯录」。"
                "注意：微信列表项不支持 ADB tap，必须通过 vision 模式坐标点击。"
                "重要：如果搜索后直接进入聊天窗口（能看到输入框可以发消息），"
                "说明已是好友，立即调用 complete 结束任务。"
                "如果进入申请添加朋友页面并点击了发送按钮，"
                "立即调用 complete 结束任务，不要继续操作。"
                "如果点击「添加到通讯录」后出现确认提示，也调用 complete 结束任务。"
                "不要反复点击同一位置。"
            ),
        )
    except Exception as e:
        return ActionResult(success=False, summary=f"打开微信失败: {e}")
