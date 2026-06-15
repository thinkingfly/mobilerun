'use client';

import { useEffect, useState } from 'react';
import { Plus, X, Eye, ChevronLeft, ChevronRight, Clock, Zap, Calendar, Play, Pause, Trash2, ChevronDown, ChevronUp, StopCircle } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { StatusBadge } from '@/components/StatusBadge';

// cron 表达式转中文描述
function describeCron(cron: string): string {
  const parts = cron.split(' ');
  if (parts.length !== 5) return cron;
  const [minute, hour, dom, month, dow] = parts;
  if (dom === '*' && month === '*' && dow === '*') {
    if (hour === '*' && minute.startsWith('*/')) return `每 ${minute.slice(2)} 分钟`;
    if (hour === '*') return `每小时第 ${minute} 分`;
    if (minute === '0') return `每天 ${hour}:00`;
    return `每天 ${hour}:${minute.padStart(2, '0')}`;
  }
  if (dow !== '*' && dom === '*') {
    const dayMap: Record<string, string> = { '1': '周一', '2': '周二', '3': '周三', '4': '周四', '5': '周五', '6': '周六', '0': '周日' };
    const dayStr = dow.includes('-') ? `${dayMap[dow.split('-')[0]]}至${dayMap[dow.split('-')[1]]}` : (dayMap[dow] || dow);
    return `每${dayStr} ${hour}:${minute.padStart(2, '0')}`;
  }
  return cron;
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [goal, setGoal] = useState('');
  const [devices, setDevices] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedDevice, setSelectedDevice] = useState('');
  const [selectedAgent, setSelectedAgent] = useState('');
  const [filterMode, setFilterMode] = useState<string>('');  // '' = all, 'running'
  const [statusFilter, setStatusFilter] = useState<string>('');   // 普通任务状态筛选
  const [schedStatusFilter, setSchedStatusFilter] = useState<string>('');  // 定时任务状态筛选
  const [scheduledTasks, setScheduledTasks] = useState<any[]>([]);
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  const [childHistory, setChildHistory] = useState<Record<string, any[]>>({});
  const [historyLoading, setHistoryLoading] = useState<Record<string, boolean>>({});

  // 定时任务面板分页
  const [schedPage, setSchedPage] = useState(1);
  const SCHED_PAGE_SIZE = 5;

  // 计算定时任务状态（用于筛选和展示）
  function getSchedStatus(st: any): string {
    if (!st.enabled) return 'disabled';
    const children = childHistory[st.id] || [];
    if (children.some((c: any) => c.status === 'running')) return 'executing';
    if (children.length === 0) return 'pending';
    const last = children[0]; // 最新的一条
    return last.status || 'pending';
  }

  // 分页状态
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  async function fetchData() {
    try {
      const listParams: any = { page, page_size: pageSize };
      if (filterMode === 'running') {
        listParams.status = 'running';
      } else if (statusFilter) {
        listParams.status = statusFilter;
      }
      const [tasksData, devicesData, agentsData, schedData] = await Promise.all([
        api.tasks.list(listParams),
        api.devices.list(),
        api.agents.list(),
        api.scheduledTasks.list(),
      ]);
      setTasks(tasksData.items);
      setTotal(tasksData.total);
      setTotalPages(tasksData.total_pages);
      setDevices(devicesData);
      setAgents(agentsData);
      const schedList = schedData.items || schedData || [];
      setScheduledTasks(schedList);
      // 预加载所有 enabled 定时任务的执行历史（用于状态展示）
      for (const st of schedList) {
        if (st.enabled && !childHistory[st.id] && !historyLoading[st.id]) {
          setHistoryLoading(prev => ({ ...prev, [st.id]: true }));
          api.scheduledTasks.history(st.id).then(data => {
            setChildHistory(prev => ({ ...prev, [st.id]: data.items || [] }));
          }).catch(() => {}).finally(() => {
            setHistoryLoading(prev => ({ ...prev, [st.id]: false }));
          });
        }
      }
    } catch (e) {
      console.error('Failed to fetch data:', e);
    } finally {
      setLoading(false);
    }
  }

  async function fetchHistory(stId: string) {
    if (childHistory[stId]) return; // already loaded
    setHistoryLoading(prev => ({ ...prev, [stId]: true }));
    try {
      const data = await api.scheduledTasks.history(stId);
      setChildHistory(prev => ({ ...prev, [stId]: data.items || [] }));
    } catch (e) {
      console.error('Failed to fetch history:', e);
    } finally {
      setHistoryLoading(prev => ({ ...prev, [stId]: false }));
    }
  }

  async function cancelScheduledTask(stId: string) {
    try {
      await api.scheduledTasks.cancel(stId);
      // 清除已展开的历史缓存，下次展开时重新获取
      setChildHistory(prev => {
        const next = { ...prev };
        delete next[stId];
        return next;
      });
      fetchData();
    } catch (e) {
      console.error('Failed to cancel scheduled task:', e);
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
  }, [page, pageSize, filterMode, statusFilter]);

  // 预加载 enabled 定时任务的执行历史（用于状态展示）
  useEffect(() => {
    if (scheduledTasks.length === 0) return;
    for (const st of scheduledTasks) {
      if (st.enabled && !childHistory[st.id] && !historyLoading[st.id]) {
        setHistoryLoading(prev => ({ ...prev, [st.id]: true }));
        api.scheduledTasks.history(st.id).then(data => {
          setChildHistory(prev => ({ ...prev, [st.id]: data.items || [] }));
        }).catch(() => {}).finally(() => {
          setHistoryLoading(prev => ({ ...prev, [st.id]: false }));
        });
      }
    }
  }, [scheduledTasks]);

  // 轮询运行中的任务
  useEffect(() => {
    const hasRunning = tasks.some(t => t.status === 'running');
    if (!hasRunning) return;
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [tasks]);

  return (
    <div className="p-8 space-y-8 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">任务管理</h1>
          <p className="text-text-secondary mt-1">共 {total} 个任务</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Filter */}
          <div className="flex bg-bg-tertiary border border-border rounded-lg p-0.5">
            <button
              onClick={() => { setFilterMode(''); setStatusFilter(''); setPage(1); setSchedPage(1); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                filterMode === '' ? 'bg-accent-blue text-white' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => { setFilterMode('running'); setStatusFilter(''); setPage(1); setSchedPage(1); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                filterMode === 'running' ? 'bg-accent-blue text-white' : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <Zap className="w-3 h-3" />
              运行中
            </button>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-accent-blue to-accent-purple text-white rounded-lg text-sm hover:shadow-[0_0_20px_rgb(var(--accent-blue)/0.3)] transition-all duration-200"
          >
            <Plus className="w-4 h-4" />
            创建任务
          </button>
        </div>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-bg-secondary border border-border rounded-xl p-6 w-full max-w-md shadow-2xl">
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
                  className="flex-1 py-2 text-sm text-white bg-gradient-to-r from-accent-blue to-accent-purple rounded-lg hover:shadow-[0_0_15px_rgb(var(--accent-blue)/0.25)] transition-all"
                >
                  创建并执行
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Scheduled Tasks Panel */}
      {(() => {
        // 筛选：运行中模式只显示enabled；状态筛选用 getSchedStatus
        const filteredSched = scheduledTasks.filter((st: any) => {
          if (filterMode === 'running' && !st.enabled) return false;
          if (schedStatusFilter) {
            return getSchedStatus(st) === schedStatusFilter;
          }
          return true;
        });
        const schedTotal = filteredSched.length;
        const schedTotalPages = Math.max(1, Math.ceil(schedTotal / SCHED_PAGE_SIZE));
        const schedPageItems = filteredSched.slice(
          (schedPage - 1) * SCHED_PAGE_SIZE,
          schedPage * SCHED_PAGE_SIZE
        );
        if (scheduledTasks.length === 0) return null;
        return (
        <div className="bg-bg-secondary border border-border rounded-xl p-5 shadow-[0_0_20px_rgb(var(--accent-purple)/0.03)]">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-accent-purple" />
              <h2 className="text-sm font-semibold text-text-primary">定时任务规则</h2>
              <span className="text-xs text-text-muted">({schedTotal} 个)</span>
            </div>
            <div className="flex items-center gap-3">
              {/* 状态筛选 */}
              <div className="relative">
                <select
                  value={schedStatusFilter}
                  onChange={(e) => { setSchedStatusFilter(e.target.value); setSchedPage(1); }}
                  className={`appearance-none pl-2.5 pr-6 py-1 rounded-md text-xs font-medium border cursor-pointer transition-colors focus:outline-none focus:border-accent-blue ${
                    schedStatusFilter
                      ? 'bg-accent-purple/10 border-accent-purple/30 text-accent-purple'
                      : 'bg-bg-tertiary border-border text-text-secondary hover:text-text-primary hover:border-text-muted'
                  }`}
                >
                  <option value="">全部状态</option>
                  <option value="executing">执行中</option>
                  <option value="enabled">启用</option>
                  <option value="disabled">已停止</option>
                  <option value="completed">已完成</option>
                  <option value="failed">失败</option>
                  <option value="pending">待执行</option>
                </select>
                <svg className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 pointer-events-none text-text-muted" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 5l3 3 3-3" />
                </svg>
              </div>
              {/* 分页 */}
              {schedTotalPages > 1 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-text-muted">
                    第 {schedPage} / {schedTotalPages} 页
                  </span>
                  <button
                    onClick={() => setSchedPage(p => Math.max(1, p - 1))}
                    disabled={schedPage <= 1}
                    className="p-1 rounded border border-border text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                  </button>
                  {Array.from({ length: Math.min(5, schedTotalPages) }, (_, i) => {
                    let p: number;
                    if (schedTotalPages <= 5) p = i + 1;
                    else if (schedPage <= 3) p = i + 1;
                    else if (schedPage >= schedTotalPages - 2) p = schedTotalPages - 4 + i;
                    else p = schedPage - 2 + i;
                    return (
                      <button
                        key={p}
                        onClick={() => setSchedPage(p)}
                        className={`w-6 h-6 rounded text-xs ${
                          p === schedPage
                            ? 'bg-accent-blue text-white'
                            : 'text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        {p}
                      </button>
                    );
                  })}
                  <button
                    onClick={() => setSchedPage(p => Math.min(schedTotalPages, p + 1))}
                    disabled={schedPage >= schedTotalPages}
                    className="p-1 rounded border border-border text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          </div>
          {schedTotal === 0 ? (
            <p className="text-xs text-text-muted text-center py-6">没有符合条件的定时任务</p>
          ) : (
          <div className="space-y-3">
            {schedPageItems
              .map((st: any) => {
                const isExpanded = expandedCard === st.id;
                const history = childHistory[st.id] || [];
                const isLoadingHistory = historyLoading[st.id] || false;
                const runningCount = history.filter((c: any) => c.status === 'running').length;
                const totalCount = history.length;

                return (
                  <div
                    key={st.id}
                    className={`rounded-lg border transition-all duration-200 ${
                      st.enabled
                        ? 'border-l-2 border-l-accent-purple border-border bg-accent-purple/[0.03] hover:shadow-[0_2px_12px_rgb(var(--accent-purple)/0.06)]'
                        : 'border-border bg-bg-tertiary/50 opacity-60'
                    }`}
                  >
                    {/* Card Header */}
                    <div className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          <p className="text-sm text-text-primary font-medium leading-tight flex-1 truncate">
                            {st.goal}
                          </p>
                          {(() => {
                            const stStatus = getSchedStatus(st);
                            return <StatusBadge status={stStatus} />;
                          })()}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {/* 启用/禁用 */}
                          <button
                            onClick={async () => {
                              await api.scheduledTasks.toggle(st.id);
                              setChildHistory(prev => { const n = { ...prev }; delete n[st.id]; return n; });
                              fetchData();
                            }}
                            className={`p-1 rounded transition-colors ${
                              st.enabled
                                ? 'text-accent-green hover:bg-accent-green/10'
                                : 'text-text-muted hover:bg-bg-tertiary'
                            }`}
                            title={st.enabled ? '点击禁用' : '点击启用'}
                          >
                            {st.enabled ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
                          </button>
                          {/* 取消 */}
                          {st.enabled && (
                            <button
                              onClick={() => cancelScheduledTask(st.id)}
                              className="p-1 rounded text-accent-red hover:bg-accent-red/10 transition-colors"
                              title="取消定时任务（禁用并停止所有运行中的子任务）"
                            >
                              <StopCircle className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary mt-1.5">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {describeCron(st.cron_expression)}
                        </span>
                        <span className="font-mono text-text-muted">{st.cron_expression}</span>
                      </div>
                      <div className="flex items-center justify-between text-xs mt-1.5">
                        <span className="text-text-muted">
                          下次: {st.next_run ? new Date(st.next_run).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}
                        </span>
                        <div className="flex items-center gap-3">
                          <span className="text-text-muted">
                            {st.device_serials?.length || 0} 台设备
                          </span>
                          {totalCount > 0 && (
                            <span className="flex items-center gap-1.5 text-text-muted">
                              已执行 {totalCount} 次
                              {runningCount > 0 && <span className="text-accent-blue">· {runningCount} 运行中</span>}
                              {history.filter((c: any) => c.status === 'completed').length > 0 && (
                                <span className="text-accent-green">· {history.filter((c: any) => c.status === 'completed').length} 成功</span>
                              )}
                              {history.filter((c: any) => c.status === 'failed').length > 0 && (
                                <span className="text-accent-red">· {history.filter((c: any) => c.status === 'failed').length} 失败</span>
                              )}
                            </span>
                          )}
                          <button
                            onClick={async () => {
                              if (isExpanded) {
                                setExpandedCard(null);
                              } else {
                                setExpandedCard(st.id);
                                await fetchHistory(st.id);
                              }
                            }}
                            className="flex items-center gap-0.5 text-accent-purple hover:text-accent-purple transition-colors"
                          >
                            {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                            {isExpanded ? '收起' : '执行历史'}
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center justify-between mt-1.5">
                        {st.last_run ? (
                          <p className="text-xs text-text-muted flex items-center gap-1.5">
                            上次: {new Date(st.last_run).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                            {history.length > 0 && history[0].result && (
                              <span className={history[0].result.success ? 'text-accent-green' : 'text-accent-red'}>
                                {history[0].result.success ? '✓ 成功' : '✗ 失败'}
                              </span>
                            )}
                            {history.length > 0 && !history[0].result && history[0].status === 'running' && (
                              <span className="text-accent-blue">● 运行中</span>
                            )}
                          </p>
                        ) : <span />}
                        <button
                          onClick={async () => {
                            if (confirm('确定删除此定时任务？')) {
                              await api.scheduledTasks.delete(st.id);
                              setChildHistory(prev => { const n = { ...prev }; delete n[st.id]; return n; });
                              fetchData();
                            }
                          }}
                          className="flex items-center gap-1 text-xs text-accent-red/60 hover:text-accent-red transition-colors"
                        >
                          <Trash2 className="w-3 h-3" />
                          删除
                        </button>
                      </div>
                    </div>

                    {/* Expanded: Child Task History */}
                    {isExpanded && (
                      <div className="border-t border-border px-3 py-2 bg-bg-primary/50 rounded-b-lg">
                        {isLoadingHistory ? (
                          <div className="flex justify-center py-4">
                            <div className="animate-spin w-5 h-5 border-2 border-accent-purple border-t-transparent rounded-full" />
                          </div>
                        ) : history.length === 0 ? (
                          <p className="text-xs text-text-muted text-center py-4">暂无执行记录</p>
                        ) : (
                          <div className="space-y-1">
                            {history.slice(0, 10).map((child: any) => {
                              let duration = '';
                              if (child.started_at && child.finished_at) {
                                const ms = new Date(child.finished_at).getTime() - new Date(child.started_at).getTime();
                                duration = ms < 60000 ? `${Math.round(ms / 1000)}s` : `${Math.round(ms / 60000)}m`;
                              } else if (child.started_at && child.status === 'running') {
                                const ms = Date.now() - new Date(child.started_at).getTime();
                                duration = `${Math.round(ms / 1000)}s…`;
                              }
                              return (
                              <div key={child.id} className="py-1.5 px-2 rounded hover:bg-bg-tertiary/50 text-xs flex items-start gap-2">
                                <div className={`w-0.5 h-4 rounded-full mt-0.5 shrink-0 ${
                                  child.status === 'running' ? 'bg-accent-blue shadow-[0_0_3px_rgb(var(--accent-blue))]' :
                                  child.status === 'completed' ? 'bg-accent-green' :
                                  child.status === 'failed' ? 'bg-accent-red' :
                                  'bg-border'
                                }`} />
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3 flex-1 min-w-0">
                                      <span className="font-mono text-text-muted">{child.id}</span>
                                      <span className="text-text-secondary font-mono truncate">{child.device_serial}</span>
                                      <StatusBadge status={child.status} />
                                      {duration && <span className="text-text-muted">{duration}</span>}
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                      <span className="text-text-muted">
                                        {child.started_at ? new Date(child.started_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-'}
                                      </span>
                                      <Link
                                        href={`/tasks/${child.id}/`}
                                        className="text-accent-purple hover:text-accent-purple"
                                      >
                                        <Eye className="w-3 h-3" />
                                      </Link>
                                    </div>
                                  </div>
                                  {child.result && (
                                    <p className={`mt-0.5 truncate ${child.result.success ? 'text-accent-green/60' : 'text-accent-red/60'}`}>
                                      {child.result.success ? '✓' : '✗'} {child.result.reason}
                                    </p>
                                  )}
                                </div>
                              </div>
                              );
                            })}
                            {history.length > 10 && (
                              <p className="text-xs text-text-muted text-center pt-1">
                                仅显示最近 10 条，共 {history.length} 条记录
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
          )}
        </div>
        );
      })()}

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
          <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden shadow-[0_0_20px_rgb(var(--accent-blue)/0.03)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-tertiary/30">
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    任务
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    类型
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    Agent
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    设备
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted tracking-wider">
                    <div className="flex items-center gap-2">
                      <span className="uppercase">状态</span>
                      <div className="relative">
                        <select
                          value={statusFilter}
                          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
                          className={`appearance-none pl-2.5 pr-6 py-1 rounded-md text-xs font-medium border cursor-pointer transition-colors focus:outline-none focus:border-accent-blue ${
                            statusFilter
                              ? 'bg-accent-blue/10 border-accent-blue/30 text-accent-blue'
                              : 'bg-bg-tertiary border-border text-text-secondary hover:text-text-primary hover:border-text-muted'
                          }`}
                        >
                          <option value="">全部</option>
                          <option value="running">运行中</option>
                          <option value="completed">已完成</option>
                          <option value="failed">失败</option>
                          <option value="pending">待执行</option>
                          <option value="cancelled">已取消</option>
                        </select>
                        <svg className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 pointer-events-none text-text-muted" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M3 5l3 3 3-3" />
                        </svg>
                      </div>
                    </div>
                  </th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-text-muted uppercase tracking-wider">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tasks
              .map((task) => (
                  <tr key={task.id} className="group hover:bg-accent-blue/[0.03] transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className={`w-0.5 h-8 rounded-full transition-all ${
                          task.status === 'running' ? 'bg-accent-blue shadow-[0_0_4px_rgb(var(--accent-blue))]' :
                          task.status === 'completed' ? 'bg-accent-green' :
                          task.status === 'failed' ? 'bg-accent-red' :
                          'bg-transparent group-hover:bg-border'
                        }`} />
                        <div>
                        <p className="text-sm text-text-primary truncate max-w-xs">
                          {task.goal}
                        </p>
                        <p className="text-xs text-text-muted mt-0.5">
                          {task.id}
                        </p>
                      </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {task.parent_task && task.parent_task !== '0' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-accent-purple/10 text-accent-purple rounded text-xs">
                          <Clock className="w-3 h-3" />
                          子任务
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-bg-tertiary text-text-secondary rounded text-xs">
                          <Zap className="w-3 h-3" />
                          普通
                        </span>
                      )}
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
