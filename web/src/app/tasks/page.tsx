'use client';

import { useEffect, useState } from 'react';
import { Plus, X, Eye, ChevronLeft, ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { StatusBadge } from '@/components/StatusBadge';

export default function TasksPage() {
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [goal, setGoal] = useState('');
  const [devices, setDevices] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedDevice, setSelectedDevice] = useState('');
  const [selectedAgent, setSelectedAgent] = useState('');

  // 分页状态
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  async function fetchData() {
    try {
      const [tasksData, devicesData, agentsData] = await Promise.all([
        api.tasks.list({ page, page_size: pageSize }),
        api.devices.list(),
        api.agents.list(),
      ]);
      setTasks(tasksData.items);
      setTotal(tasksData.total);
      setTotalPages(tasksData.total_pages);
      setDevices(devicesData);
      setAgents(agentsData);
    } catch (e) {
      console.error('Failed to fetch data:', e);
    } finally {
      setLoading(false);
    }
  }

  async function createTask() {
    if (!goal.trim()) return;
    try {
      await api.tasks.create({
        goal,
        device_serial: selectedDevice || undefined,
        agent_id: selectedAgent || undefined,
      });
      setGoal('');
      setSelectedDevice('');
      setSelectedAgent('');
      setShowCreate(false);
      // 回到第一页
      setPage(1);
      fetchData();
    } catch (e) {
      console.error('Failed to create task:', e);
    }
  }

  async function cancelTask(id: string) {
    try {
      await api.tasks.cancel(id);
      fetchData();
    } catch (e) {
      console.error('Failed to cancel task:', e);
    }
  }

  useEffect(() => {
    fetchData();
  }, [page, pageSize]);

  // 轮询运行中的任务
  useEffect(() => {
    const hasRunning = tasks.some(t => t.status === 'running');
    if (!hasRunning) return;
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [tasks]);

  return (
    <div className="p-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">任务管理</h1>
          <p className="text-text-secondary mt-1">共 {total} 个任务</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-accent-blue text-white rounded-lg text-sm hover:bg-accent-blue/80 transition-colors"
        >
          <Plus className="w-4 h-4" />
          创建任务
        </button>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-bg-secondary border border-border rounded-xl p-6 w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-text-primary">
                创建任务
              </h2>
              <button
                onClick={() => setShowCreate(false)}
                className="text-text-muted hover:text-text-primary"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-text-secondary mb-1">
                  目标指令
                </label>
                <input
                  type="text"
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  placeholder="例如: 打开微信"
                  className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                />
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-1">
                  目标设备（可选）
                </label>
                <select
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                  className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent-blue"
                >
                  <option value="">自动选择</option>
                  {devices
                    .filter((d) => d.state !== 'offline')
                    .map((d) => (
                      <option key={d.serial} value={d.serial}>
                        {d.serial}
                      </option>
                    ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-1">
                  执行 Agent（可选）
                </label>
                <select
                  value={selectedAgent}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent-blue"
                >
                  <option value="">自动选择</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} {a.device_serial ? `(${a.device_serial})` : ''} {a.status === 'working' ? '- 忙碌' : '- 空闲'}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowCreate(false)}
                  className="flex-1 py-2 text-sm text-text-secondary bg-bg-tertiary border border-border rounded-lg hover:text-text-primary transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={createTask}
                  className="flex-1 py-2 text-sm text-white bg-accent-blue rounded-lg hover:bg-accent-blue/80 transition-colors"
                >
                  创建并执行
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Task List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full" />
        </div>
      ) : tasks.length === 0 ? (
        <div className="bg-bg-secondary border border-border rounded-xl p-12 text-center">
          <p className="text-text-muted">暂无任务</p>
          <p className="text-sm text-text-muted mt-2">点击"创建任务"开始</p>
        </div>
      ) : (
        <>
          <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    任务
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    Agent
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    设备
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    状态
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tasks.map((task) => (
                  <tr key={task.id} className="hover:bg-bg-tertiary/50">
                    <td className="px-6 py-4">
                      <div>
                        <p className="text-sm text-text-primary truncate max-w-xs">
                          {task.goal}
                        </p>
                        <p className="text-xs text-text-muted mt-0.5">
                          {task.id}
                        </p>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-text-secondary">
                      {(() => {
                        const agent = agents.find(a => a.id === task.agent_id);
                        return agent ? agent.name : task.agent_id;
                      })()}
                    </td>
                    <td className="px-6 py-4 text-sm text-text-secondary font-mono">
                      {task.device_serial}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={task.status} />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/tasks/${task.id}/`}
                          className="flex items-center gap-1 px-2 py-1 text-xs text-text-secondary bg-bg-tertiary border border-border rounded hover:text-text-primary transition-colors"
                        >
                          <Eye className="w-3 h-3" />
                          详情
                        </Link>
                        {task.status === 'running' && (
                          <button
                            onClick={() => cancelTask(task.id)}
                            className="flex items-center gap-1 px-2 py-1 text-xs text-accent-red bg-accent-red/10 rounded hover:bg-accent-red/20 transition-colors"
                          >
                            <X className="w-3 h-3" />
                            取消
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-text-secondary">
              <span>每页显示</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                className="px-2 py-1 bg-bg-tertiary border border-border rounded text-sm text-text-primary"
              >
                <option value={10}>10</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-text-secondary">
                第 {page} / {totalPages} 页
              </span>
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded border border-border text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              {/* 页码按钮：最多显示 5 个 */}
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let p: number;
                if (totalPages <= 5) {
                  p = i + 1;
                } else if (page <= 3) {
                  p = i + 1;
                } else if (page >= totalPages - 2) {
                  p = totalPages - 4 + i;
                } else {
                  p = page - 2 + i;
                }
                return (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={`w-8 h-8 rounded text-sm ${
                      p === page
                        ? 'bg-accent-blue text-white'
                        : 'text-text-secondary hover:text-text-primary'
                    }`}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 rounded border border-border text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
