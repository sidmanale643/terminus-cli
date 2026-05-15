import net from "node:net";
import {
  encodeMessage,
  parseJsonLines,
  type InboundEnvelope,
  type OutboundMessage,
} from "./protocol.js";

interface SocketClientHandlers {
  onConnected: () => void;
  onDisconnected: () => void;
  onError: (error: string) => void;
  onMessage: (message: InboundEnvelope) => void;
}

export class SocketClient {
  private readonly socketPath: string;
  private readonly handlers: SocketClientHandlers;
  private socket: net.Socket | null = null;
  private buffer = "";

  constructor(socketPath: string, handlers: SocketClientHandlers) {
    this.socketPath = socketPath;
    this.handlers = handlers;
  }

  connect(): void {
    const socket = net.createConnection(this.socketPath);
    this.socket = socket;

    socket.setEncoding("utf8");

    socket.on("connect", () => {
      this.handlers.onConnected();
    });

    socket.on("data", (chunk: string) => {
      this.buffer += chunk;
      const { messages, remainder } = parseJsonLines(this.buffer);
      this.buffer = remainder;
      for (const message of messages) {
        this.handlers.onMessage(message);
      }
    });

    socket.on("error", (error) => {
      this.handlers.onError(error.message);
    });

    socket.on("close", () => {
      this.handlers.onDisconnected();
    });
  }

  send(message: OutboundMessage): boolean {
    if (!this.socket || this.socket.destroyed) {
      return false;
    }
    this.socket.write(encodeMessage(message));
    return true;
  }

  disconnect(): void {
    if (!this.socket) {
      return;
    }
    this.socket.end();
    this.socket.destroy();
    this.socket = null;
  }
}
