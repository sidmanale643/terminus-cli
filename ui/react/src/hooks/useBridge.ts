import { useReducer, useEffect, useCallback, useRef } from "react";
import { SocketClient } from "../bridge/socketClient.js";
import type { InboundMessage } from "../bridge/protocol.js";
import { bridgeReducer, initialState, type BridgeState } from "../bridge/state.js";

const SOCK_PATH = process.env.TERMINUS_SOCK || "";

export type { BridgeState } from "../bridge/state.js";
export type { ModelOption, CommandOption } from "../bridge/protocol.js";
export type { ChatMessage } from "../bridge/state.js";

export function useBridge() {
  const [state, dispatch] = useReducer(bridgeReducer, initialState);
  const clientRef = useRef<SocketClient | null>(null);

  useEffect(() => {
    if (!SOCK_PATH) {
      dispatch({ type: "connection_error", error: "TERMINUS_SOCK not set" });
      return;
    }

    const client = new SocketClient(SOCK_PATH, {
      onMessage: (msg: InboundMessage) => {
        if (msg.type === "exit") {
          client.disconnect();
          process.exit(0);
        }
        dispatch({ type: "bridge_message", message: msg });
      },
      onConnected: () => {
        dispatch({ type: "connected" });
        client.send({ type: "ready" });
      },
      onDisconnected: () => dispatch({ type: "disconnected" }),
      onError: (error) => dispatch({ type: "connection_error", error }),
    });

    clientRef.current = client;
    client.connect();

    return () => {
      client.disconnect();
      clientRef.current = null;
    };
  }, []);

  const sendInput = useCallback((input: string): boolean => {
    const client = clientRef.current;
    if (!client) {
      dispatch({ type: "connection_error", error: "Not connected to TERMINUS" });
      return false;
    }
    const ok = client.send({ type: "input", content: input });
    if (ok) {
      dispatch({ type: "input_sent" });
    }
    return ok;
  }, []);

  const sendInterrupt = useCallback((): void => {
    clientRef.current?.send({ type: "interrupt" });
  }, []);

  const sendCopyLastResponse = useCallback((): boolean => {
    const client = clientRef.current;
    if (!client) {
      dispatch({ type: "connection_error", error: "Not connected to TERMINUS" });
      return false;
    }
    return client.send({ type: "copy_last_response" });
  }, []);

  const sendModelSelected = useCallback((name: string | null): boolean => {
    const client = clientRef.current;
    if (!client) {
      dispatch({ type: "connection_error", error: "Not connected to TERMINUS" });
      return false;
    }
    const ok = client.send({ type: "model_selected", name });
    if (ok) {
      dispatch({ type: "model_selected_sent" });
      return true;
    }
    return false;
  }, []);

  const sendProviderSelected = useCallback((name: string): boolean => {
    const client = clientRef.current;
    if (!client) return false;
    const ok = client.send({ type: "provider_selected", name });
    if (ok) {
      dispatch({ type: "provider_selected_sent" });
      return true;
    }
    return false;
  }, []);

  const sendApiKey = useCallback((key: string): boolean => {
    const client = clientRef.current;
    if (!client) return false;
    const ok = client.send({ type: "api_key_submitted", key });
    if (ok) {
      dispatch({ type: "api_key_submitted_sent" });
      return true;
    }
    return false;
  }, []);

  const toggleThinking = useCallback((index: number): void => {
    dispatch({ type: "toggle_thinking", index });
  }, []);

  return {
    ...state,
    sendInput,
    sendInterrupt,
    sendCopyLastResponse,
    sendModelSelected,
    sendProviderSelected,
    sendApiKey,
    toggleThinking,
  };
}
