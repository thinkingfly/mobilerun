'use client';

import { useEffect, useState } from 'react';
import { Plus, Trash2, MessageSquare, Eraser, Archive } from 'lucide-react';
import { api } from '@/lib/api';
import { StatusBadge } from '@/components/StatusBadge';

export default function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [devices, setDevices] = useState<any[]>([]);
  const [selectedDevice, setSelectedDevice] = useState('');
  const [memoryCounts, setMemoryCounts] = useState<Record<string, number>>({});

  async function fetchData() {
    try {
      const [agentsData, devicesData] = await Promise.all([
        api.agents.list(),
        api.devices.list(),
      ]);
      setAgents(agentsData);
      setDevices(devicesData);

      const counts: Record<string, number> = {};
      for (const a of agentsData) {
        try {
          const mem = await api.agents.getMemory(a.id);
          counts[a.id] = mem.chat_count;
        } catch {
          counts[a.id] = 0;
        }
      }
      setMemoryCounts(counts);
    } catch (e) {
      console.error('Failed to fetch agents:', e);
    } finally {
      setLoading(false);
    }
  }

  async function createAgent() {
    if (!newName.trim()) return;
    try {
      await api.agents.create({
        name: newName,
        device_serial: selectedDevice || undefined,
      });
      setNewName('');
      setSelectedDevice('');
      setShowCreate(false);
      fetchData();
    } catch (e) {
      console.error('Failed to create agent:', e);
    }
  }

  async function deleteAgent(id: string) {
    try {
      await api.agents.delete(id);
      fetchData();
    } catch (e: any) {
      console.error('Failed to delete agent:', e);
      if (e.message) alert(e.message);
    }
  }

  async function clearMemory(id: string) {
    if (!confirm('确定要清空该 Agent 的对话记忆吗？')) return;
    try {
      await api.agents.clearMemory(id);
      fetchData();
    } catch (e) {
      console.error('Failed to clear memory:', e);
    }
  }

  async function compressMemory(id: string) {
    if (!confirm('确定要压缩该 Agent 的对话记忆吗？\n将只保留最近 10 条消息，其余压缩为摘要。')) return;
    try {
      await api.agents.compressMemory(id);
      fetchData();
    } catch (e) {
      console.error('Failed to compress memory:', e);
    }
  }

  function handleDeviceChange(serial: string) {
    setSelectedDevice(serial);
    if (serial) setNewName(serial);
    else setNewName('');
  }

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-8 space-y-8 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Agent 管理</h1>
          <p className="text-text-secondary mt-1 text-sm">共 {agents.length} 个 Agent</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-accent-blue to-accent-purple text-white rounded-lg text-sm hover:shadow-[0_0_20px_rgb(var(--accent-blue)/0.3)] transition-all duration-200"
        >
          <Plus className="w-4 h-4" />
          新增 Agent
        </button>
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-bg-secondary border border-border rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h2 className="text-lg font-semibold text-text-primary mb-4">创建 Agent</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-text-secondary mb-1">名称</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="Agent 名称"
                  className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue focus:shadow-[0_0_8px_rgb(var(--accent-blue)/0.15)] transition-all"
                />
              </div>
              <div>
                <label className="block text-sm text-text-secondary mb-1">绑定设备（可选）</label>
                <select
                  value={selectedDevice}
                  onChange={(e) => handleDeviceChange(e.target.value)}
                  className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent-blue transition-all"
                >
                  <option value="">不绑定</option>
                  {devices.filter((d) => d.state !== 'offline').map((d) => (
                    <option key={d.serial} value={d.serial}>{d.serial}</option>
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
                  onClick={createAgent}
                  className="flex-1 py-2 text-sm text-white bg-gradient-to-r from-accent-blue to-accent-purple rounded-lg hover:shadow-[0_0_15px_rgb(var(--accent-blue)/0.25)] transition-all"
                >
                  创建
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Agent List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin w-8 h-8 border-2 border-accent-blue border-t-transparent rounded-full" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => {
            const isWorking = agent.status === 'working';
            return (
              <div
                key={agent.id}
                className={`group bg-bg-secondary border rounded-xl p-6 space-y-4 transition-all duration-200 hover:shadow-[0_4px_20px_rgb(var(--accent-blue)/0.06)] hover:-translate-y-0.5 ${
                  isWorking
                    ? 'border-t-2 border-t-accent-blue border-border'
                    : 'border-border'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">{agent.name}</h3>
                    <p className="text-xs text-text-muted mt-0.5 font-mono">ID: {agent.id}</p>
                  </div>
                  <StatusBadge status={agent.status} />
                </div>

                <div className="space-y-2 text-xs text-text-muted">
                  {agent.device_serial && (
                    <p className="flex items-center gap-1.5">
                      <span className="w-1 h-1 rounded-full bg-accent-cyan" />
                      设备: {agent.device_serial}
                    </p>
                  )}
                  {agent.current_task && (
                    <p className="flex items-center gap-1.5">
                      <span className="w-1 h-1 rounded-full bg-accent-blue animate-pulse" />
                      当前任务: {agent.current_task}
                    </p>
                  )}
                  <p>完成任务: <span className="text-text-secondary tabular-nums">{agent.total_tasks}</span></p>
                  {memoryCounts[agent.id] !== undefined && (
                    <div className="flex items-center gap-1.5 text-text-secondary">
                      <MessageSquare className="w-3 h-3" />
                      对话记录: <span className="tabular-nums">{memoryCounts[agent.id]}</span> 条
                    </div>
                  )}
                </div>

                {/* Memory Actions */}
                <div className="flex gap-2 border-t border-border pt-3">
                  <button
                    onClick={() => clearMemory(agent.id)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-secondary bg-bg-tertiary border border-border rounded-md hover:text-accent-red hover:border-accent-red/30 transition-all"
                    title="清空对话记忆"
                  >
                    <Eraser className="w-3 h-3" />
                    清空
                  </button>
                  <button
                    onClick={() => compressMemory(agent.id)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-text-secondary bg-bg-tertiary border border-border rounded-md hover:text-accent-blue hover:border-accent-blue/30 transition-all"
                    title="压缩对话记忆"
                  >
                    <Archive className="w-3 h-3" />
                    压缩
                  </button>
                </div>

                {/* Delete */}
                <div className="flex gap-2">
                  {agent.is_default ? (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-muted bg-bg-tertiary border border-border rounded-lg cursor-not-allowed" title="默认 Agent，无法删除">
                      <Trash2 className="w-3 h-3" />
                      默认 Agent
                    </div>
                  ) : agent.status === 'working' ? (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-muted bg-bg-tertiary border border-border rounded-lg cursor-not-allowed" title="该 Agent 正在执行任务，无法删除">
                      <Trash2 className="w-3 h-3" />
                      执行中，无法删除
                    </div>
                  ) : (
                    <button
                      onClick={() => deleteAgent(agent.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-accent-red bg-accent-red/10 rounded-lg hover:bg-accent-red/20 transition-colors"
                    >
                      <Trash2 className="w-3 h-3" />
                      删除
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
