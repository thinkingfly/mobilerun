'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams } from 'next/navigation';
import { ArrowLeft, X } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { logWs } from '@/lib/websocket';
import { StatusBadge } from '@/components/StatusBadge';

const colorMap: Record<string, string> = {
  blue: 'text-blue-400',
  cyan: 'text-cyan-400',
  green: 'text-green-400',
  red: 'text-red-400',
  yellow: 'text-yellow-400',
  magenta: 'text-purple-400',
  white: 'text-text-primary',
};

export default function TaskDetailPage() {
  const params = useParams();
  const taskId = params.id as string;
  const [task, setTask] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  async function fetchTask() {
    try {
      const data = await api.tasks.get(taskId);
      setTask(data);
    } catch (e) {
      console.error('Failed to fetch task:', e);
    } finally {
      setLoading(false);
    }
  }

  async function cancelTask() {
    try {
      await api.tasks.cancel(taskId);
      fetchTask();
    } catch (e) {
      console.error('Failed to cancel task:', e);
    }
  }

  useEffect(() => {
    fetchTask();
    const interval = setInterval(fetchTask, 3000);
    return () => clearInterval(interval);
  }, [taskId]);

  useEffect(() => {
    // Connect to WebSocket for real-time logs
    logWs.connect(taskId);

    const unsubscribe = logWs.onMessage((entry) => {
      setLogs((prev) => [...prev, entry]);
    });

    return () => {
      unsubscribe();
      logWs.disconnect();
    };
  }, [taskId]);

  // Auto-scroll to bottom of logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  if (loading) {
    return (
      <div className="p-8 flex justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="p-8 text-center">
        <p className="text-text-muted">任务不存在</p>
        <Link href="/tasks/" className="text-accent-blue text-sm mt-2 inline-block">
          返回任务列表
        </Link>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/tasks/"
            className="text-text-muted hover:text-text-primary transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-text-primary">{task.goal}</h1>
            <p className="text-sm text-text-muted mt-0.5">
              任务 ID: {task.id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={task.status} />
          {task.status === 'running' && (
            <button
              onClick={cancelTask}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-accent-red bg-accent-red/10 rounded-lg hover:bg-accent-red/20 transition-colors"
            >
              <X className="w-4 h-4" />
              取消任务
            </button>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <p className="text-xs text-text-muted">设备</p>
          <p className="text-sm text-text-primary font-mono mt-1">
            {task.device_serial}
          </p>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <p className="text-xs text-text-muted">Agent</p>
          <p className="text-sm text-text-primary font-mono mt-1">
            {task.agent_id}
          </p>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <p className="text-xs text-text-muted">日志数</p>
          <p className="text-sm text-text-primary mt-1">{logs.length}</p>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <p className="text-xs text-text-muted">状态</p>
          <p className="text-sm text-text-primary mt-1">{task.status}</p>
        </div>
      </div>

      {/* Result */}
      {task.result && (
        <div className="bg-bg-secondary border border-border rounded-lg p-4">
          <h3 className="text-sm font-semibold text-text-primary mb-2">执行结果</h3>
          <p className="text-sm text-text-secondary">
            {task.result.success ? '成功' : '失败'}: {task.result.reason}
          </p>
        </div>
      )}

      {/* Log Viewer */}
      <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold text-text-primary">实时日志</h3>
        </div>
        <div
          ref={logContainerRef}
          className="h-96 overflow-y-auto p-4 font-mono text-xs space-y-1 bg-bg-primary"
        >
          {logs.length === 0 ? (
            <p className="text-text-muted text-center py-8">
              等待日志输出...
            </p>
          ) : (
            logs.map((log, i) => {
              const colorClass = log.color
                ? colorMap[log.color] || 'text-text-primary'
                : 'text-text-primary';
              return (
                <div key={i} className={colorClass}>
                  {log.msg}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
