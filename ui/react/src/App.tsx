import React from "react";
import { Box, Text, useInput } from "ink";
import { useBridge } from "./hooks/useBridge.js";
import { Logo } from "./components/Logo.js";
import { Banner } from "./components/Banner.js";
import { InputBox } from "./components/InputBox.js";
import { StatusBar } from "./components/StatusBar.js";
import { MessageList } from "./components/MessageList.js";
import { ModelSelect } from "./components/ModelSelect.js";
import { ProviderSelect } from "./components/ProviderSelect.js";
import { ApiKeyInput } from "./components/ApiKeyInput.js";
import { COLORS } from "./theme.js";

export default function App() {
  const { banner, status, commands, requestingInput, messages, streamingContent, modelSelect, providerSelect, apiKeyRequest, connected, connectionError, sendInput, sendInterrupt, sendCopyLastResponse, sendModelSelected, sendProviderSelected, sendApiKey, toggleThinking } = useBridge();

  const lastThinkingIndex = messages.reduce((idx, msg, i) => msg.type === "thinking" ? i : idx, -1);

  useInput((input, key) => {
    if (key.ctrl && input === "t" && lastThinkingIndex >= 0) {
      toggleThinking(lastThinkingIndex);
    }
  });

  return (
    <Box flexDirection="column">
      {banner ? (
        <Banner logo={banner.logo} subtitle={banner.subtitle} />
      ) : (
        <Box flexDirection="column" alignItems="center">
          <Logo />
        </Box>
      )}

      <Box flexDirection="column" flexGrow={1}>
        <MessageList messages={messages} streamingContent={streamingContent} />
        {modelSelect && (
          <ModelSelect
            models={modelSelect.models}
            currentModel={modelSelect.currentModel}
            onSelect={sendModelSelected}
          />
        )}
        {providerSelect && (
          <ProviderSelect
            providers={providerSelect.providers}
            onSelect={(name) => {
              if (name) sendProviderSelected(name);
            }}
          />
        )}
        {apiKeyRequest && (
          <ApiKeyInput
            provider={apiKeyRequest.provider}
            onSubmit={(key) => {
              sendApiKey(key);
            }}
            onCancel={() => {
              sendApiKey("");
            }}
          />
        )}
      </Box>

      <Box flexDirection="column" marginTop={2}>
        {!connected && !connectionError && (
          <Box>
            <Text color={COLORS.muted} dimColor>Connecting to TERMINUS...</Text>
          </Box>
        )}
        <InputBox
          active={requestingInput && connected && !modelSelect && !providerSelect && !apiKeyRequest}
          commands={commands}
          onSubmit={sendInput}
          onInterrupt={sendInterrupt}
          onCopyLastResponse={sendCopyLastResponse}
          connectionError={connectionError}
        />
        <StatusBar
          cwd={status.cwd}
          model={status.model}
          contextPercent={status.contextPercent}
        />
      </Box>
    </Box>
  );
}
