type LogEntry = {
  msg: string;
  color?: string;
  stream?: boolean;
  stream_end?: boolean;
  level?: number;
  timestamp?: string;
  type?: string;
};

type EventHandler = (entry: LogEntry) => void;

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export class LogWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Set<EventHandler> = new Set();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private task_id: string | null = null;

  connect(taskId: string) {
    this.task_id = taskId;
    this.disconnect();
    const url = `${API_BASE.replace('http', 'ws')}/api/ws/logs/${taskId}`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log(`WS connected to ${taskId}`);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'ping') return;
          this.handlers.forEach((h) => h(data));
        } catch {
          // Ignore parse errors
        }
      };

      this.ws.onerror = (err) => {
        console.error(`WS error for ${taskId}:`, err);
      };

      this.ws.onclose = () => {
        // Auto reconnect
        this.reconnectTimer = setTimeout(() => {
          if (this.task_id) this.connect(this.task_id);
        }, 3000);
      };
    } catch {
      // WebSocket not supported
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  onMessage(handler: EventHandler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }
}

export const logWs = new LogWebSocket();
