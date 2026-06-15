'use client';

import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import { StatusBadge } from '@/components/StatusBadge';

export default function DevicesPage() {
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function fetchDevices() {
    try {
      const data = await api.devices.list();
      setDevices(data);
    } catch (e) {
      console.error('Failed to fetch devices:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function refreshDevice(serial: string) {
    try {
      await api.devices.refresh(serial);
      fetchDevices();
    } catch (e) {
      console.error('Failed to refresh device:', e);
    }
  }

  useEffect(() => {
    fetchDevices();
    const interval = setInterval(fetchDevices, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-8 space-y-8 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">设备管理</h1>
          <p className="text-text-secondary mt-1 text-sm">
            共 {devices.length} 台设备
          </p>
        </div>
        <button
          onClick={() => {
            setRefreshing(true);
            fetchDevices();
          }}
          className="flex items-center gap-2 px-4 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-secondary hover:text-text-primary hover:border-accent-blue/30 transition-all duration-200"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full" />
        </div>
      ) : devices.length === 0 ? (
        <div className="bg-bg-secondary border border-border rounded-xl p-12 text-center">
          <p className="text-text-muted">没有连接的设备</p>
          <p className="text-sm text-text-muted mt-2">请确保设备已通过 ADB 连接</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {devices.map((device) => {
            const isOnline = device.state !== 'offline';
            return (
              <div
                key={device.serial}
                className={`group bg-bg-secondary border rounded-xl p-6 space-y-4 transition-all duration-200 hover:shadow-[0_4px_20px_rgb(var(--accent-blue)/0.06)] hover:-translate-y-0.5 ${
                  isOnline
                    ? 'border-l-2 border-l-accent-green border-border'
                    : 'border-border opacity-60'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-mono text-text-primary truncate">
                      {device.serial}
                    </p>
                    <p className="text-xs text-text-muted mt-1">
                      {device.platform}
                    </p>
                  </div>
                  <StatusBadge status={device.state} />
                </div>

                <div className="space-y-2 text-xs text-text-muted">
                  {device.current_task && (
                    <p className="flex items-center gap-1.5">
                      <span className="w-1 h-1 rounded-full bg-accent-blue" />
                      当前任务: {device.current_task}
                    </p>
                  )}
                  {device.last_seen && (
                    <p>
                      最后在线:{' '}
                      {new Date(device.last_seen).toLocaleTimeString('zh-CN')}
                    </p>
                  )}
                </div>

                <button
                  onClick={() => refreshDevice(device.serial)}
                  className="w-full py-2 text-xs text-text-secondary bg-bg-tertiary border border-border rounded-lg hover:text-text-primary hover:border-accent-blue/30 transition-all duration-200"
                >
                  刷新状态
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
