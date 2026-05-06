/**
 * 应用级常量：localStorage / sessionStorage 键名等。
 * 集中放置避免魔法字符串散落各处。
 */

/** 当前标签页对话身份，供 /api/sessions、/api/chat 关联服务端状态 */
export const DIALOG_KEY = "myclaw.session.dialogId";

/** 侧栏展开为 "1"，收起为 "0"；缺省视为展开 */
export const SIDEBAR_OPEN_KEY = "myclaw.ui.sidebarOpen";

/** 旧版键名，仅由 sessionDialog 迁移读取一次后删除 */
export const LEGACY_DIALOG_KEY = "claw0_s06_dialog_id";
export const LEGACY_SIDEBAR_OPEN_KEY = "claw0_sidebar_open";
