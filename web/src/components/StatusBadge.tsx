import { clsx } from 'clsx';

const statusColors: Record<string, string> = {
  online: 'bg-accent-green text-accent-green',
  offline: 'bg-accent-red text-accent-red',
  busy: 'bg-accent-yellow text-accent-yellow',
  idle: 'bg-text-muted text-text-muted',
  working: 'bg-accent-blue text-accent-blue',
  error: 'bg-accent-red text-accent-red',
  pending: 'bg-text-muted text-text-muted',
  running: 'bg-accent-blue text-accent-blue',
  completed: 'bg-accent-green text-accent-green',
  cancelled: 'bg-accent-red text-accent-red',
  failed: 'bg-accent-red text-accent-red',
};

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
};

export function StatusBadge({
  status,
  variant = 'badge',
}: {
  status: string;
  variant?: 'badge' | 'dot';
}) {
  const label = status.charAt(0).toUpperCase() + status.slice(1);

  if (variant === 'dot') {
    const dot = dotColors[status] || 'bg-text-muted';
    return (
      <span className="flex items-center gap-2 text-sm text-text-secondary">
        <span className={clsx('w-2 h-2 rounded-full', dot)} />
        {label}
      </span>
    );
  }

  const badge = statusColors[status] || 'bg-text-muted text-text-muted';
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-opacity-10',
        badge
      )}
    >
      {label}
    </span>
  );
}
