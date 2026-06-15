'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams } from 'next/navigation';
import { ArrowLeft, X } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { logWs } from '@/lib/websocket';
import { StatusBadge } from '@/components/StatusBadge';

const colorMap: Record<string, string> = {
  blue: 'text-accent-blue',
  cyan: 'text-accent-cyan',
  green: 'text-accent-green',
  red: 'text-accent-red',
  yellow: 'text-accent-yellow',
  magenta: 'text-accent-purple',
  white: 'text-text-primary',
};

export default function TaskDetailPage() {
  const params = useParams();
  const taskId = params.id as string;
  const [task, setTask] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [children, setChildren] = useState<any[]>([]);
  const [scheduledTask, setScheduledTask] = useState<any>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);

  async function fetchTask() {
    try {
      const data = await api.tasks.get(taskId);
      setTask(data);
      // 获取子任务
      try {
        const childData = await api.tasks.children(taskId);
        if (childData.items && childData.items.length > 0) {
          setChildren(childData.items);
        }
      } catch { /* no children */ }
    } catch (e) {
      // 如果不是普通任务，尝试作为定时任务获取
      try {
        const stData = await api.scheduledTasks.get(taskId);
        setScheduledTask(stData);
        // 获取定时任务的执行历史
        try {
          const histData = await api.scheduledTasks.history(taskId);
          setChildren(histData.items || []);
        } catch { /* no history */ }
      } catch {
        console.error('Failed to fetch task:', e);
      }
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

  async function fetchLogs() {
    try {
      const data = await api.tasks.logs(taskId);
      if (data.logs && data.logs.length > 0) {
        setLogs(data.logs);
      }
    } catch { /* no persisted logs */ }
  }

  useEffect(() => {
    fetchTask();
    fetchLogs();
    const interval = setInterval(fetchTask, 3000);
    return () => clearInterval(interval);
  }, [taskId]);

  useEffect(() => {
    // Connect to WebSocket for real-time logs (append to persisted ones)
    logWs.connect(taskId);

    const unsubscribe = logWs.onMessage((entry) => {
      setLogs((prev) => {
        // 避免 WebSocket 重复推送已有的日志
        if (prev.some(l => l.msg === entry.msg && l.color === entry.color)) return prev;
        return [...prev, entry];
      });
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

  if (!task && !scheduledTask) {
    return (
      <div className="p-8 text-center">
        <p className="text-text-muted">任务不存在</p>
        <Link href="/tasks/" className="text-accent-blue text-sm mt-2 inline-block">
          返回任务列表
        </Link>
      </div>
    );
  }

  // 定时任务详情视图
  if (scheduledTask) {
    return (
      <div className="p-8 space-y-6 animate-fade-in-up">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/tasks/" className="text-text-muted hover:text-text-primary transition-colors">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-xl font-bold text-text-primary">{scheduledTask.goal}</h1>
              <p className="text-sm text-text-muted mt-0.5">
                定时任务 ID: {scheduledTask.id}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              scheduledTask.enabled ? 'bg-accent-green/10 text-accent-green' : 'bg-bg-tertiary text-text-muted'
            }`}>
              {scheduledTask.enabled ? '运行中' : '已停止'}
            </span>
            {scheduledTask.enabled && (
              <button
                onClick={async () => {
                  await api.scheduledTasks.cancel(taskId);
                  fetchTask();
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-accent-red bg-accent-red/10 rounded-lg hover:bg-accent-red/20 transition-colors"
              >
                <X className="w-4 h-4" />
                取消
              </button>
            )}
          </div>
        </div>

        {/* 统计 */}
        {(() => {
          const runningCount = children.filter((c: any) => c.status === 'running').length;
          const completedCount = children.filter((c: any) => c.status === 'completed').length;
          const failedCount = children.filter((c: any) => c.status === 'failed').length;
          return (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
                <p className="text-xs text-text-muted uppercase tracking-wider">Cron 表达式</p>
                <p className="text-sm text-text-primary font-mono mt-1">{scheduledTask.cron_expression}</p>
              </div>
              <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
                <p className="text-xs text-text-muted uppercase tracking-wider">下次执行</p>
                <p className="text-sm text-text-primary mt-1">
                  {scheduledTask.next_run ? new Date(scheduledTask.next_run).toLocaleString('zh-CN') : '-'}
                </p>
              </div>
              <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
                <p className="text-xs text-text-muted uppercase tracking-wider">已执行</p>
                <p className="text-sm text-text-primary mt-1 tabular-nums">{children.length} 次</p>
              </div>
              <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
                <p className="text-xs text-text-muted uppercase tracking-wider">成功 / 失败</p>
                <p className="text-sm mt-1">
                  <span className="text-accent-green tabular-nums">{completedCount}</span>
                  <span className="text-text-muted mx-1">/</span>
                  <span className="text-accent-red tabular-nums">{failedCount}</span>
                </p>
              </div>
              <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
                <p className="text-xs text-text-muted uppercase tracking-wider">设备</p>
                <p className="text-sm text-text-primary font-mono mt-1 truncate" title={scheduledTask.device_serials?.join(', ')}>
                  {scheduledTask.device_serials?.length || 0} 台
                </p>
              </div>
            </div>
          );
        })()}

        {/* 执行历史 */}
        <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary">执行历史 ({children.length})</h3>
            {children.some((c: any) => c.status === 'running') && (
              <span className="flex items-center gap-1.5 text-xs text-accent-blue">
                <span className="w-1.5 h-1.5 bg-accent-blue rounded-full animate-pulse" />
                有任务运行中
              </span>
            )}
          </div>
          {children.length === 0 ? (
            <p className="text-text-muted text-center py-8 text-sm">暂无执行记录</p>
          ) : (
            <div className="divide-y divide-border">
              {children.map((child: any) => {
                // 计算耗时
                let duration = '-';
                if (child.started_at && child.finished_at) {
                  const ms = new Date(child.finished_at).getTime() - new Date(child.started_at).getTime();
                  if (ms < 60000) duration = `${Math.round(ms / 1000)}s`;
                  else duration = `${Math.round(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`;
                } else if (child.started_at && child.status === 'running') {
                  const ms = Date.now() - new Date(child.started_at).getTime();
                  duration = `${Math.round(ms / 1000)}s...`;
                }
                return (
                <div key={child.id} className="px-4 py-3 hover:bg-bg-tertiary/50">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm text-text-muted">{child.id}</span>
                      <span className="text-xs text-text-secondary font-mono">{child.device_serial}</span>
                      <StatusBadge status={child.status} />
                      <span className="text-xs text-text-muted">{duration}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-muted">
                        {child.started_at ? new Date(child.started_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-'}
                      </span>
                      <Link
                        href={`/tasks/${child.id}/`}
                        className="text-xs text-accent-blue hover:underline"
                      >
                        详情
                      </Link>
                    </div>
                  </div>
                  {child.result && (
                    <p className={`text-xs mt-1.5 truncate ${child.result.success ? 'text-accent-green/70' : 'text-accent-red/70'}`}>
                      {child.result.success ? '✓' : '✗'} {child.result.reason}
                    </p>
                  )}
                </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6 animate-fade-in-up">
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
        <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
          <p className="text-xs text-text-muted uppercase tracking-wider">设备</p>
          <p className="text-sm text-text-primary font-mono mt-1">
            {task.device_serial}
          </p>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
          <p className="text-xs text-text-muted uppercase tracking-wider">Agent</p>
          <p className="text-sm text-text-primary font-mono mt-1">
            {task.agent_id}
          </p>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
          <p className="text-xs text-text-muted uppercase tracking-wider">日志数</p>
          <p className="text-sm text-text-primary mt-1 tabular-nums">{logs.length}</p>
        </div>
        <div className="bg-bg-secondary border border-border rounded-lg p-4 hover:border-accent-blue/20 transition-all duration-200">
          <p className="text-xs text-text-muted uppercase tracking-wider">状态</p>
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

      {/* Parent Task Link */}
      {task.parent_task && task.parent_task !== '0' && (
        <div className="bg-accent-purple/5 border border-accent-purple/20 rounded-lg p-4">
          <p className="text-xs text-text-muted mb-1">此任务由定时任务创建</p>
          <Link
            href={`/tasks/${task.parent_task}/`}
            className="text-sm text-accent-purple hover:underline"
          >
            查看父级定时任务 →
          </Link>
        </div>
      )}

      {/* Child Tasks */}
      {children.length > 0 && (() => {
        const runningCount = children.filter(c => c.status === 'running').length;
        const completedCount = children.filter(c => c.status === 'completed').length;
        const failedCount = children.filter(c => c.status === 'failed').length;
        return (
        <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary">子任务 ({children.length})</h3>
            <div className="flex items-center gap-2 text-xs">
              {runningCount > 0 && <span className="text-accent-blue">{runningCount} 运行中</span>}
              {completedCount > 0 && <span className="text-accent-green">{completedCount} 完成</span>}
              {failedCount > 0 && <span className="text-accent-red">{failedCount} 失败</span>}
            </div>
          </div>
          <div className="divide-y divide-border">
            {children.map((child: any) => {
              // 计算耗时
              let duration = '-';
              if (child.started_at && child.finished_at) {
                const ms = new Date(child.finished_at).getTime() - new Date(child.started_at).getTime();
                if (ms < 60000) duration = `${Math.round(ms / 1000)}s`;
                else duration = `${Math.round(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`;
              } else if (child.started_at && child.status === 'running') {
                const ms = Date.now() - new Date(child.started_at).getTime();
                duration = `${Math.round(ms / 1000)}s...`;
              }
              return (
              <div key={child.id} className="px-4 py-3 hover:bg-bg-tertiary/50 flex items-start gap-3">
                <div className={`w-0.5 h-8 rounded-full mt-0.5 shrink-0 ${
                  child.status === 'running' ? 'bg-accent-blue shadow-[0_0_3px_rgb(var(--accent-blue))]' :
                  child.status === 'completed' ? 'bg-accent-green' :
                  child.status === 'failed' ? 'bg-accent-red' :
                  'bg-border'
                }`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm text-text-muted">{child.id}</span>
                      <span className="text-xs text-text-secondary font-mono">{child.device_serial}</span>
                      <StatusBadge status={child.status} />
                      <span className="text-xs text-text-muted">{duration}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-muted">
                        {child.started_at ? new Date(child.started_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-'}
                      </span>
                      <Link
                        href={`/tasks/${child.id}/`}
                        className="text-xs text-accent-blue hover:underline"
                      >
                        详情
                      </Link>
                    </div>
                  </div>
                  {child.result && (
                    <p className={`text-xs mt-1.5 truncate ${child.result.success ? 'text-accent-green/70' : 'text-accent-red/70'}`}>
                      {child.result.success ? '✓' : '✗'} {child.result.reason}
                    </p>
                  )}
                </div>
              </div>
              );
            })}
          </div>
        </div>
        );
      })()}

      {/* Log Viewer */}
      <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden shadow-[0_0_20px_rgb(var(--accent-blue)/0.03)]">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-accent-red/60" />
              <span className="w-2.5 h-2.5 rounded-full bg-accent-yellow/60" />
              <span className="w-2.5 h-2.5 rounded-full bg-accent-green/60" />
            </div>
            <h3 className="text-sm font-semibold text-text-primary">
              执行日志 {logs.length > 0 && <span className="text-text-muted font-normal">({logs.length} 条)</span>}
            </h3>
          </div>
          {task.status === 'running' && (
            <span className="flex items-center gap-1.5 text-xs text-accent-green">
              <span className="w-1.5 h-1.5 bg-accent-green rounded-full animate-pulse shadow-[0_0_6px_rgb(var(--accent-green))]" />
              实时
            </span>
          )}
        </div>
        <div
          ref={logContainerRef}
          className="h-96 overflow-y-auto p-4 font-mono text-xs space-y-1 bg-terminal-bg text-terminal-text"
        >
          {logs.length === 0 ? (
            <p className="text-text-muted text-center py-8">
              {task.status === 'running' ? '等待日志输出...' : '暂无日志记录'}
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
