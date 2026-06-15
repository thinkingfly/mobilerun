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
import { ThemeToggle } from '@/components/ThemeToggle';

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
    <aside className="w-64 bg-bg-secondary border-r border-border flex flex-col dark:shadow-[1px_0_12px_rgb(var(--accent-blue)/0.04)]">
      {/* Logo */}
      <div className="p-6 border-b border-border flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold bg-gradient-to-r from-accent-blue to-accent-purple bg-clip-text text-transparent">
            Mobilebot
          </h1>
          <p className="text-xs text-text-muted mt-1 font-mono tracking-wider">Agent Dashboard</p>
        </div>
        <ThemeToggle />
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex items-center gap-3 py-2.5 px-3 rounded-lg text-sm transition-all duration-200 ${
                isActive
                  ? 'border-l-2 border-accent-blue bg-accent-blue/8 text-accent-blue pl-[10px]'
                  : 'border-l-2 border-transparent text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/60 hover:border-border-light'
              }`}
            >
              <item.icon className={`w-4 h-4 transition-colors ${
                isActive ? 'text-accent-blue' : 'text-text-muted group-hover:text-text-secondary'
              }`} />
              {item.name}
              {isActive && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-accent-blue shadow-[0_0_6px_rgb(var(--accent-blue))]" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <div className="flex items-center justify-between">
          <p className="text-xs text-text-muted font-mono">v0.1.0</p>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-green shadow-[0_0_4px_rgb(var(--accent-green))]" />
            <span className="text-[10px] text-text-muted">Online</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
