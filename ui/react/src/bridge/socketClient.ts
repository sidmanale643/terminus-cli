import net from "net";
import { InboundMessage, OutboundMessage, parseJsonLines, encodeOutbound } from "./protocol.js";

export interface SocketClientEvents {
  onMessage: (msg: InboundMessage) => void;
  onConnected: () => void;
  onDisconnected: () => void;
  onError: (error: string) => void;
}

const RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_ATTEMPTS = 5;

export class SocketClient {
  private sockPath: string;
  private events: SocketClientEvents;
  private sock: net.Socket | null = null;
  private buffer = "";
  private reconnectAttempts = 0;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private destroyed = false;

  constructor(sockPath: string, events: SocketClientEvents) {
    this.sockPath = sockPath;
    this.events = events;
  }

  connect(): void {
    if (this.destroyed) return;
    const sock = net.createConnection(this.sockPath);
    let connected = false;

    sock.on("connect", () => {
      connected = true;
      this.sock = sock;
      this.reconnectAttempts = 0;
      this.buffer = "";
      this.events.onConnected();
    });

    sock.on("data", (data: Buffer) => {
      this.buffer += data.toString();
      const { messages, remainder } = parseJsonLines(this.buffer);
      this.buffer = remainder;
      for (const msg of messages) {
        this.events.onMessage(msg);
      }
    });

    sock.on("error", (err) => {
      if (connected || this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        this.events.onError(`Socket error: ${err.message}`);
      }
    });

    sock.on("close", () => {
      this.sock = null;
      this.events.onDisconnected();
      this.scheduleReconnect();
    });

    this.sock = sock;
  }

  send(msg: OutboundMessage): boolean {
    if (!this.sock || this.sock.destroyed) return false;
    try {
      this.sock.write(encodeOutbound(msg));
      return true;
    } catch {
      return false;
    }
  }

  disconnect(): void {
    this.destroyed = true;
    this.clearReconnectTimeout();
    if (this.sock) {
      this.sock.end();
      this.sock = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.destroyed) return;
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.events.onError("Connection lost. Please restart TERMINUS.");
      return;
    }
    this.reconnectAttempts += 1;
    this.clearReconnectTimeout();
    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, RECONNECT_DELAY_MS);
  }

  private clearReconnectTimeout(): void {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }
}
