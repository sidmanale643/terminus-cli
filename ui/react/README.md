# React UI Architecture

## Module Boundaries

```
src/
  bridge/
    protocol.ts      Inbound/outbound message types, JSON-line parsing
    socketClient.ts   Unix socket connection, reconnect, buffering, send
    state.ts          BridgeState reducer — converts bridge messages to UI state
  helpers/
    inputHelpers.ts   Pure functions for input/cursor state and command filtering
    format.ts         Display formatting (price formatting, message color mapping)
  hooks/
    useBridge.ts      Thin React wrapper: wires SocketClient events to reducer, exposes actions
  components/
    InputBox.tsx      Ink useInput wiring + display (behavior from inputHelpers)
    MessageList.tsx   Renders chat messages with colors from format helpers
    ModelSelect.tsx   Model picker (uses formatPrice from helpers)
    StatusBar.tsx     Status bar (uses theme helpers)
    Logo.tsx          Static fallback logo
  App.tsx             Layout composition only
  theme.ts            Color constants and progress-bar helpers
  main.tsx            Ink render entry point
```

## Rules

1. **Python bridge owns the protocol producer.** The React side only consumes inbound messages and sends outbound messages — it never generates its own protocol types.
2. **React bridge modules own socket/protocol handling.** All socket I/O goes through `SocketClient`; all state transitions go through the `bridgeReducer`. Components must not open sockets or mutate protocol state directly.
3. **Components receive normalized props.** `MessageList`, `ModelSelect`, and `StatusBar` take simple data props and avoid protocol-specific imports.
4. **Future agents should change the narrowest module for a bug.** Socket reconnection? `socketClient.ts`. New message type? `protocol.ts` + `state.ts`. Input key handling? `inputHelpers.ts`. Display color? `format.ts` or `theme.ts`.