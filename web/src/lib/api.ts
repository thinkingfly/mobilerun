const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080/api';

async function request(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Devices
  devices: {
    list: () => request('/devices'),
    get: (serial: string) => request(`/devices/${serial}`),
    refresh: (serial: string) => request(`/devices/${serial}/refresh`, { method: 'POST' }),
  },
  // Tasks
  tasks: {
    list: (params?: { status?: string; type?: string; page?: number; page_size?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set('status', params.status);
      if (params?.type) qs.set('type', params.type);
      if (params?.page) qs.set('page', String(params.page));
      if (params?.page_size) qs.set('page_size', String(params.page_size));
      const query = qs.toString();
      return request(`/tasks${query ? `?${query}` : ''}`);
    },
    get: (id: string) => request(`/tasks/${id}`),
    create: (data: { goal: string; device_serial?: string; agent_id?: string }) =>
      request('/tasks', { method: 'POST', body: JSON.stringify(data) }),
    cancel: (id: string) => request(`/tasks/${id}/cancel`, { method: 'POST' }),
    children: (id: string) => request(`/tasks/${id}/children`),
    logs: (id: string) => request(`/tasks/${id}/logs`),
  },
  // Agents
  agents: {
    list: () => request('/agents'),
    create: (data: { name: string; device_serial?: string }) =>
      request('/agents', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: string) => request(`/agents/${id}`, { method: 'DELETE' }),
    getMemory: (id: string) => request(`/agents/${id}/memory`),
    clearMemory: (id: string) => request(`/agents/${id}/memory`, { method: 'DELETE' }),
    compressMemory: (id: string, keepLast?: number) =>
      request(`/agents/${id}/memory/compress?keep_last=${keepLast || 10}`, { method: 'POST' }),
  },
  // Chat
  chat: {
    send: (message: string, agent_id?: string, device_serials?: string[]) =>
      request('/chat', { method: 'POST', body: JSON.stringify({ message, agent_id, device_serials }) }),
    getHistory: (agent_id: string) => request(`/chat/${agent_id}/history`),
    clearHistory: (agent_id: string) => request(`/chat/${agent_id}/history`, { method: 'DELETE' }),
    compressHistory: (agent_id: string, keepLast?: number) =>
      request(`/chat/${agent_id}/history/compress?keep_last=${keepLast || 10}`, { method: 'POST' }),
  },
  // Scheduled Tasks
  scheduledTasks: {
    list: () => request('/scheduled-tasks'),
    get: (id: string) => request(`/scheduled-tasks/${id}`),
    create: (data: { goal: string; device_serials: string[]; cron_expression: string }) =>
      request('/scheduled-tasks', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: string) => request(`/scheduled-tasks/${id}`, { method: 'DELETE' }),
    toggle: (id: string) => request(`/scheduled-tasks/${id}/toggle`, { method: 'POST' }),
    cancel: (id: string) => request(`/scheduled-tasks/${id}/cancel`, { method: 'POST' }),
    history: (id: string) => request(`/scheduled-tasks/${id}/history`),
  },
  // Stats
  stats: () => request('/stats'),
};
