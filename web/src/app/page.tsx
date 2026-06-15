'use client';

import { useEffect, useState } from 'react';
import { Smartphone, Bot, ListTodo, Play } from 'lucide-react';
import { api } from '@/lib/api';
import { StatusBadge } from '@/components/StatusBadge';

const statusColorMap: Record<string, string> = {
  running: 'bg-accent-blue',
  completed: 'bg-accent-green',
  failed: 'bg-accent-red',
  cancelled: 'bg-accent-red',
  pending: 'bg-text-muted',
};

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  async function fetchData() {
    try {
      const [statsData, tasksData, devicesData] = await Promise.all([
        api.stats(),
        api.tasks.list(),
        api.devices.list(),
      ]);
      setStats(statsData);
      setTasks(tasksData.slice(0, 5));
      setDevices(devicesData);
    } catch (e) {
      console.error('Failed to fetch dashboard data:', e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="animate-spin w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full" />
      </div>
    );
  }

  const statCards = [
    { label: '设备总数', value: stats?.total_devices || 0, icon: Smartphone, color: 'accent-cyan' },
    { label: '在线设备', value: stats?.online_devices || 0, icon: Smartphone, color: 'accent-green' },
    { label: 'Agent 数', value: stats?.total_agents || 0, icon: Bot, color: 'accent-purple' },
    { label: '运行中任务', value: stats?.running_tasks || 0, icon: Play, color: 'accent-blue' },
  ];

  return (
    <div className="p-8 space-y-8 animate-fade-in-up">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">仪表盘</h1>
        <p className="text-text-secondary mt-1 text-sm">系统概览</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((card, i) => (
          <div
            key={card.label}
            className="group bg-bg-secondary border border-border rounded-xl p-6 transition-all duration-200 hover:border-accent-blue/30 hover:shadow-[0_4px_20px_rgb(var(--accent-blue)/0.06)] hover:-translate-y-0.5"
            style={{ animationDelay: `${i * 80}ms` }}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-text-muted uppercase tracking-wider">{card.label}</p>
                <p className="text-3xl font-bold text-text-primary mt-2 tabular-nums">
                  {card.value}
                </p>
              </div>
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center bg-${card.color}/10 shadow-[0_0_12px_rgb(var(--${card.color})/0.15)]`}>
                <card.icon className={`w-5 h-5 text-${card.color}`} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Recent Tasks */}
      <div className="bg-bg-secondary border border-border rounded-xl p-6">
        <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">最近任务</h2>
        {tasks.length === 0 ? (
          <p className="text-text-muted text-center py-8 text-sm">暂无任务</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="group flex items-center justify-between p-3 bg-bg-tertiary/60 rounded-lg border border-transparent hover:border-border transition-all duration-200"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className={`w-1 h-8 rounded-full ${statusColorMap[task.status] || 'bg-text-muted'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text-primary truncate">
                      {task.goal}
                    </p>
                    <p className="text-xs text-text-muted mt-0.5 font-mono">
                      {task.device_serial}
                    </p>
                  </div>
                </div>
                <StatusBadge status={task.status} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Devices */}
      <div className="bg-bg-secondary border border-border rounded-xl p-6">
        <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">设备状态</h2>
        {devices.length === 0 ? (
          <p className="text-text-muted text-center py-8 text-sm">暂无设备</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {devices.map((device) => (
              <div
                key={device.serial}
                className="group flex items-center justify-between p-4 bg-bg-tertiary/60 rounded-lg border border-transparent hover:border-border transition-all duration-200"
              >
                <div>
                  <p className="text-sm text-text-primary font-mono">
                    {device.serial}
                  </p>
                  <p className="text-xs text-text-muted mt-0.5">
                    {device.platform}
                  </p>
                </div>
                <StatusBadge status={device.state} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
