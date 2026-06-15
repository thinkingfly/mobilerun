import { clsx } from 'clsx';

const statusColors: Record<string, string> = {
  online: 'bg-accent-green/15 text-accent-green',
  offline: 'bg-accent-red/15 text-accent-red',
  busy: 'bg-accent-yellow/15 text-accent-yellow',
  idle: 'bg-text-muted/15 text-text-muted',
  working: 'bg-accent-blue/15 text-accent-blue',
  error: 'bg-accent-red/15 text-accent-red',
  pending: 'bg-text-muted/15 text-text-muted',
  running: 'bg-accent-blue/15 text-accent-blue',
  completed: 'bg-accent-green/15 text-accent-green',
  cancelled: 'bg-accent-red/15 text-accent-red',
  failed: 'bg-accent-red/15 text-accent-red',
  enabled: 'bg-accent-green/15 text-accent-green',
  disabled: 'bg-text-muted/15 text-text-muted',
  executing: 'bg-accent-blue/15 text-accent-blue',
};

// 活跃状态：带辉光效果
const activeStates = new Set(['running', 'online', 'executing', 'working']);

const dotColors: Record<string, string> = {
  online: 'bg-accent-green',
  offline: 'bg-accent-red',
  busy: 'bg-accent-yellow',
  idle: 'bg-text-muted',
  working: 'bg-accent-blue',
  error: 'bg-accent-red',
  pending: 'bg-text-muted',
  running: 'bg-accent-blue',
  completed: 'bg-accent-green',
  cancelled: 'bg-accent-red',
  failed: 'bg-accent-red',
  enabled: 'bg-accent-green',
  disabled: 'bg-text-muted',
  executing: 'bg-accent-blue',
};

// 英文状态 → 中文标签
const labelMap: Record<string, string> = {
  online: '在线',
  offline: '离线',
  busy: '忙碌',
  idle: '空闲',
  working: '工作中',
  error: '错误',
  pending: '待执行',
  running: '运行中',
  completed: '已完成',
  cancelled: '已取消',
  failed: '失败',
  enabled: '启用',
  disabled: '已停止',
  executing: '执行中',
};

export function StatusBadge({
  status,
  variant = 'badge',
  label,
}: {
  status: string;
  variant?: 'badge' | 'dot';
  label?: string;
}) {
  const displayLabel = label || labelMap[status] || (status.charAt(0).toUpperCase() + status.slice(1));
  const isActive = activeStates.has(status);

  if (variant === 'dot') {
    const dot = dotColors[status] || 'bg-text-muted';
    return (
      <span className="flex items-center gap-2 text-sm text-text-secondary">
        <span className={clsx(
          'w-2 h-2 rounded-full relative',
          dot,
          isActive && 'animate-pulse shadow-[0_0_6px_currentColor]',
        )} />
        {displayLabel}
      </span>
    );
  }

  const badge = statusColors[status] || 'bg-text-muted/15 text-text-muted';
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium transition-all',
        badge,
        isActive && 'shadow-[0_0_8px_rgb(var(--accent-blue)/0.2)]',
      )}
    >
      {isActive && (
        <span className={clsx('w-1.5 h-1.5 rounded-full animate-pulse', dotColors[status] || 'bg-text-muted')} />
      )}
      {displayLabel}
    </span>
  );
}
