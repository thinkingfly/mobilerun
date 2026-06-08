'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Smartphone,
  Bot,
  ListTodo,
  MessageSquare,
} from 'lucide-react';

const navItems = [
  { name: '仪表盘', href: '/', icon: LayoutDashboard },
  { name: '设备', href: '/devices/', icon: Smartphone },
  { name: 'Agent', href: '/agents/', icon: Bot },
  { name: '任务', href: '/tasks/', icon: ListTodo },
  { name: '对话', href: '/chat/', icon: MessageSquare },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-bg-secondary border-r border-border flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-border">
        <h1 className="text-lg font-bold text-text-primary">Mobilerun</h1>
        <p className="text-xs text-text-muted mt-1">Agent Dashboard</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-accent-blue/10 text-accent-blue'
                  : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
              }`}
            >
              <item.icon className="w-4 h-4" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <p className="text-xs text-text-muted">v0.1.0</p>
      </div>
    </aside>
  );
}
