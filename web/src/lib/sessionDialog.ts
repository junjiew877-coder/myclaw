/**
 * 浏览器 tab 维度 dialog_id 与侧栏展开状态的 sessionStorage 读写。
 * 首次读取时若仅有旧键（claw0_*），会写入新键并删除旧键，完成一次性迁移。
 */

import {
  DIALOG_KEY,
  LEGACY_DIALOG_KEY,
  LEGACY_SIDEBAR_OPEN_KEY,
  SIDEBAR_OPEN_KEY,
} from "../constants";

export function loadDialogId(): string {
  try {
    let id = sessionStorage.getItem(DIALOG_KEY);
    if (!id) {
      id = sessionStorage.getItem(LEGACY_DIALOG_KEY);
      if (id) {
        sessionStorage.setItem(DIALOG_KEY, id);
        sessionStorage.removeItem(LEGACY_DIALOG_KEY);
      } else {
        id = crypto.randomUUID();
        sessionStorage.setItem(DIALOG_KEY, id);
      }
    }
    return id;
  } catch {
    return "web_session";
  }
}

export function loadSidebarOpen(): boolean {
  try {
    let raw = sessionStorage.getItem(SIDEBAR_OPEN_KEY);
    if (raw === null) {
      const legacy = sessionStorage.getItem(LEGACY_SIDEBAR_OPEN_KEY);
      if (legacy !== null) {
        const normalized = legacy === "0" ? "0" : "1";
        sessionStorage.setItem(SIDEBAR_OPEN_KEY, normalized);
        sessionStorage.removeItem(LEGACY_SIDEBAR_OPEN_KEY);
        raw = normalized;
      }
    }
    if (raw === null) return true;
    return raw !== "0";
  } catch {
    return true;
  }
}
