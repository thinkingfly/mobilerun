'use client';

import { useEffect, useRef, useState } from 'react';
import { Send, X, Eye } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { logWs } from '@/lib/websocket';

const colorMap: Record<string, string> = {
  blue: 'text-blue-400',
  cyan: 'text-cyan-400',
  green: 'text-green-400',
  red: 'text-red-400',
  yellow: 'text-yellow-400',
  magenta: 'text-purple-400',
  white: 'text-text-primary',
};

type Message = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  compressed?: boolean;
};

const WELCOME_MSG: Message = {
  role: 'assistant',
  content: '你好！我是移动设备管理助手。你可以告诉我想要执行的操作，例如"打开微信"或"截屏"。',
  timestamp: new Date(),
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState('');
  const [activeTask, setActiveTask] = useState<{ id: string; goal: string; logs: any[]; status: string; result: any; agentName?: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  // Track running task info across re-renders
  const activeTaskRef = useRef<{ taskId: string; pollInterval: ReturnType<typeof setInterval> | null }>({ taskId: '', pollInterval: null });
  // Input history (like terminal up-arrow history)
  const [inputHistory, setInputHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const [draftInput, setDraftInput] = useState<string>('');

  // Load agents + auto-select first
  useEffect(() => {
    api.agents.list().then(data => {
      setAgents(data);
      if (data.length > 0) {
        setSelectedAgent(prev => prev || data[0].id);
      }
    }).catch(console.error);
  }, []);

  // Load chat history when agent is determined (only once per agent)
  useEffect(() => {
    if (!selectedAgent) return;
    let cancelled = false;

    api.chat.getHistory(selectedAgent).then(data => {
      if (cancelled) return;
      const historyMessages = (data.messages || []).map((m: any) => ({
        role: m.role as 'user' | 'assistant' | 'system',
        content: m.content,
        timestamp: new Date(m.timestamp),
        compressed: m.compressed,
      }));
      const displayMessages = historyMessages.filter((m: any) => m.role !== 'system');
      setMessages(displayMessages.length > 0 ? displayMessages : [WELCOME_MSG]);

      // Initialize input history from chat history (user messages only)
      const userMessages = (data.messages || [])
        .filter((m: any) => m.role === 'user')
        .map((m: any) => m.content);
      setInputHistory(userMessages);

      // Check if there's a running task to restore
      // Look for the last task_id mentioned in chat history
      const lastTaskMsg = [...(data.messages || [])].reverse().find((m: any) => m.task_id);
      if (lastTaskMsg?.task_id) {
        // Check if task is still running
        api.tasks.get(lastTaskMsg.task_id).then(task => {
          if (cancelled) return;
          if (task.status === 'running') {
            const agentName = agents.find((a: any) => a.id === task.agent_id)?.name || task.agent_id;
            setActiveTask({
              id: task.id,
              goal: task.goal,
              logs: [],
              status: task.status,
              result: task.result,
              agentName,
            });
            // Connect WebSocket for logs
            logWs.connect(task.id);
            const unsub = logWs.onMessage((entry) => {
              setActiveTask((prev) => {
                if (!prev || prev.id !== task.id) return prev;
                return { ...prev, logs: [...prev.logs, entry] };
              });
            });
            // Store unsubscribe for cleanup
            activeTaskRef.current = { taskId: task.id, pollInterval: null };

            // Start polling
            const pollInterval = setInterval(async () => {
              try {
                const t = await api.tasks.get(task.id);
                setActiveTask((prev) => {
                  if (!prev || prev.id !== task.id) return prev;
                  if (t.status !== 'running') {
                    clearInterval(pollInterval);
                    unsub();
                    logWs.disconnect();
                    activeTaskRef.current = { taskId: '', pollInterval: null };
                    api.agents.list().then(setAgents);
                  }
                  return { ...prev, status: t.status, result: t.result };
                });
              } catch { /* ignore */ }
            }, 3000);
            activeTaskRef.current = { taskId: task.id, pollInterval };
          }
        }).catch(() => { /* task not found, ignore */ });
      }
    }).catch(() => {
      if (!cancelled) setMessages([WELCOME_MSG]);
    });

    return () => {
      cancelled = true;
      // Cleanup polling and WebSocket
      if (activeTaskRef.current.pollInterval) {
        clearInterval(activeTaskRef.current.pollInterval);
      }
      logWs.disconnect();
      activeTaskRef.current = { taskId: '', pollInterval: null };
      // Reset input history when switching agents
      setInputHistory([]);
      setHistoryIndex(-1);
      setDraftInput('');
    };
  }, [selectedAgent]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeTask?.logs.length]);

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [activeTask?.logs]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending || !selectedAgent) return;

    // Save to input history
    setInputHistory(prev => [...prev, text]);
    setHistoryIndex(-1);
    setDraftInput('');

    const userMessage: Message = {
      role: 'user',
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setSending(true);

    try {
      const result = await api.chat.send(userMessage.content, selectedAgent);

      // If a task was created, show it
      if (result.task_id) {
        const agentName = agents.find(a => a.id === result.agent_id)?.name || result.agent_id;
        setActiveTask({
          id: result.task_id,
          goal: result.goal || userMessage.content,
          logs: [],
          status: 'running',
          result: null,
          agentName,
        });

        // Clean up previous task if any
        if (activeTaskRef.current.pollInterval) {
          clearInterval(activeTaskRef.current.pollInterval);
        }
        logWs.disconnect();

        // Connect to WebSocket for real-time logs
        logWs.connect(result.task_id);
        const unsub = logWs.onMessage((entry) => {
          setActiveTask((prev) => {
            if (!prev || prev.id !== result.task_id) return prev;
            return { ...prev, logs: [...prev.logs, entry] };
          });
        });

        // Poll task status
        const pollInterval = setInterval(async () => {
          try {
            const task = await api.tasks.get(result.task_id);
            setActiveTask((prev) => {
              if (!prev || prev.id !== result.task_id) return prev;
              if (task.status !== 'running') {
                clearInterval(pollInterval);
                unsub();
                logWs.disconnect();
                activeTaskRef.current = { taskId: '', pollInterval: null };
                // Refresh agents list
                api.agents.list().then(setAgents);
                // Reload chat history to show task result
                api.chat.getHistory(selectedAgent).then(data => {
                  const historyMessages = (data.messages || []).map((m: any) => ({
                    role: m.role as 'user' | 'assistant' | 'system',
                    content: m.content,
                    timestamp: new Date(m.timestamp),
                    compressed: m.compressed,
                  }));
                  const displayMessages = historyMessages.filter((m: any) => m.role !== 'system');
                  setMessages(displayMessages);
                });
              }
              return { ...prev, status: task.status, result: task.result };
            });
          } catch {
            // ignore
          }
        }, 3000);

        activeTaskRef.current = { taskId: result.task_id, pollInterval };

        const assistantMessage: Message = {
          role: 'assistant',
          content: `已创建任务：${result.goal || userMessage.content}\nAgent: ${agentName} | 执行中...`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } else {
        const assistantMessage: Message = {
          role: 'assistant',
          content: result.response || '收到，正在处理...',
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
      }
    } catch (e) {
      const errorMessage: Message = {
        role: 'assistant',
        content: '抱歉，处理消息时出错，请稍后再试。',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (historyIndex === -1) {
        // First press: save current input and go to last history entry
        setDraftInput(input);
        if (inputHistory.length > 0) {
          setHistoryIndex(inputHistory.length - 1);
          setInput(inputHistory[inputHistory.length - 1]);
        }
      } else if (historyIndex > 0) {
        // Go to previous history entry
        const newIndex = historyIndex - 1;
        setHistoryIndex(newIndex);
        setInput(inputHistory[newIndex]);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex !== -1) {
        if (historyIndex < inputHistory.length - 1) {
          // Go to next history entry
          const newIndex = historyIndex + 1;
          setHistoryIndex(newIndex);
          setInput(inputHistory[newIndex]);
        } else {
          // Return to the input that was being typed before navigating history
          setHistoryIndex(-1);
          setInput(draftInput);
        }
      }
    }
  }

  function closeActiveTask() {
    if (activeTaskRef.current.pollInterval) {
      clearInterval(activeTaskRef.current.pollInterval);
    }
    logWs.disconnect();
    activeTaskRef.current = { taskId: '', pollInterval: null };
    setActiveTask(null);
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="px-8 py-4 border-b border-border">
          <h1 className="text-xl font-bold text-text-primary">对话</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            通过自然语言控制移动设备
          </p>
        </div>

        {/* Agent Selector */}
        {agents.length > 0 && (
          <div className="px-8 py-3 border-b border-border flex items-center gap-3">
            <span className="text-sm text-text-secondary">执行 Agent:</span>
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="px-3 py-1.5 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent-blue"
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} {a.device_serial ? `(${a.device_serial})` : ''} {a.status === 'working' ? '🔵' : '🟢'}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-2xl px-4 py-3 rounded-xl text-sm ${
                  msg.compressed
                    ? 'bg-bg-tertiary/50 border border-dashed border-border text-text-muted italic'
                    : msg.role === 'user'
                    ? 'bg-accent-blue text-white'
                    : 'bg-bg-tertiary text-text-primary border border-border'
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
                <p className="text-xs mt-2 text-text-muted">
                  {msg.compressed ? '压缩摘要' : msg.timestamp.toLocaleTimeString('zh-CN')}
                </p>
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-bg-tertiary border border-border px-4 py-3 rounded-xl">
                <div className="flex gap-1">
                  <div className="w-2 h-2 bg-text-muted rounded-full animate-bounce" />
                  <div
                    className="w-2 h-2 bg-text-muted rounded-full animate-bounce"
                    style={{ animationDelay: '0.1s' }}
                  />
                  <div
                    className="w-2 h-2 bg-text-muted rounded-full animate-bounce"
                    style={{ animationDelay: '0.2s' }}
                  />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-8 py-4 border-t border-border">
          <div className="flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入指令，如: 打开抖音点赞"
              disabled={sending}
              className="flex-1 px-4 py-3 bg-bg-tertiary border border-border rounded-xl text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              onClick={sendMessage}
              disabled={sending || !input.trim()}
              className="px-4 py-3 bg-accent-blue text-white rounded-xl hover:bg-accent-blue/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Task Panel (right side) */}
      {activeTask && (
        <div className="w-96 border-l border-border flex flex-col bg-bg-primary">
          {/* Task Header */}
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-text-primary truncate max-w-[220px]">
                {activeTask.goal}
              </h3>
              <p className="text-xs text-text-muted mt-0.5">
                ID: {activeTask.id}
                {activeTask.agentName && ` | Agent: ${activeTask.agentName}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                href={`/tasks/${activeTask.id}/`}
                className="text-text-muted hover:text-text-primary"
                title="查看详情"
              >
                <Eye className="w-4 h-4" />
              </Link>
              <button
                onClick={closeActiveTask}
                className="text-text-muted hover:text-text-primary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Status */}
          <div className="px-4 py-2 border-b border-border flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${
              activeTask.status === 'running' ? 'bg-accent-blue animate-pulse' :
              activeTask.status === 'completed' ? 'bg-green-400' :
              activeTask.status === 'failed' ? 'bg-red-400' :
              'bg-text-muted'
            }`} />
            <span className="text-xs text-text-secondary capitalize">
              {activeTask.status === 'running' ? '执行中...' :
               activeTask.status === 'completed' ? '已完成' :
               activeTask.status === 'failed' ? '失败' :
               activeTask.status === 'cancelled' ? '已取消' :
               activeTask.status}
            </span>
          </div>

          {/* Logs */}
          <div
            ref={logContainerRef}
            className="flex-1 overflow-y-auto p-3 font-mono text-xs space-y-1 bg-bg-secondary"
          >
            {activeTask.logs.length === 0 ? (
              <p className="text-text-muted text-center py-8">
                等待日志输出...
              </p>
            ) : (
              activeTask.logs.map((log, i) => {
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

          {/* Result */}
          {activeTask.result && (
            <div className="px-4 py-3 border-t border-border bg-bg-tertiary">
              <p className="text-xs text-text-secondary">
                {activeTask.result.success ? '✅ 成功' : '❌ 失败'}
                {activeTask.result.reason && `: ${activeTask.result.reason}`}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
