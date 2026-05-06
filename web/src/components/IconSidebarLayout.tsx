/**
 * 侧栏切换按钮内嵌 SVG：左右分栏示意图标。
 */

export function IconSidebarLayout() {
  return (
    <svg
      className="sidebar-toggle-icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      aria-hidden
    >
      <rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
      <line x1="9" y1="4" x2="9" y2="20" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
