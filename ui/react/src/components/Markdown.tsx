import React from "react";
import { Box, Text } from "ink";
import { marked } from "marked";
import type { Token, Tokens } from "marked";

const MUTED = "#666";
const CODE_BORDER = "#444";
const CODE_LANG_BG = "#2d2d44";
const INLINE_CODE_BG = "#2d2d44";
const HEADING_COLORS = ["#EF4444", "#F97316", "#EAB308", "#34D399", "#3B82F6", "#8B5CF6"];

function inlineTokens(toks: Token[], color?: string): React.ReactNode[] {
  return toks.map((token, i) => {
    switch (token.type) {
      case "text":
        return <Text key={i} color={color}>{token.text}</Text>;
      case "strong":
        return (
          <Text key={i} bold color={color}>
            {inlineTokens(token.tokens!, color)}
          </Text>
        );
      case "em":
        return (
          <Text key={i} italic color={color}>
            {inlineTokens(token.tokens!, color)}
          </Text>
        );
      case "codespan":
        return (
          <Text key={i} backgroundColor={INLINE_CODE_BG} color="#E5E7EB">
            {token.text}
          </Text>
        );
      case "link":
        return (
          <Text key={i} underline color="#3B82F6">
            {inlineTokens((token as Tokens.Link).tokens, "#3B82F6")}
          </Text>
        );
      case "del":
        return (
          <Text key={i} dimColor color={color}>
            {inlineTokens(token.tokens!, color)}
          </Text>
        );
      case "br":
        return <Text key={i}>{"\n"}</Text>;
      case "image":
        return (
          <Text key={i} dimColor color={color}>
            [Image: {token.text}]
          </Text>
        );
      case "escape":
        return <Text key={i} color={color}>{token.text}</Text>;
      default:
        return <Text key={i} color={color}>{(token as any).text || ""}</Text>;
    }
  });
}

function CodeBlock({ token, key }: { token: Tokens.Code; key?: number }) {
  const lines = token.text.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return (
    <Box key={key} flexDirection="column">
      {token.lang && (
        <Box>
          <Text backgroundColor={CODE_LANG_BG} color="#999">
            {" "}{token.lang}{" "}
          </Text>
        </Box>
      )}
      <Box
        flexDirection="column"
        borderStyle="single"
        borderColor={CODE_BORDER}
        paddingX={1}
        paddingY={1}
      >
        {lines.map((line, i) => (
          <Text key={i} wrap="wrap">
            {line || " "}
          </Text>
        ))}
      </Box>
    </Box>
  );
}

function renderToken(token: Token, color?: string, key?: number): React.ReactNode {
  switch (token.type) {
    case "space":
      return <Text key={key}>{"\n"}</Text>;

    case "code":
      return <CodeBlock key={key} token={token as Tokens.Code} />;

    case "heading": {
      const headingToken = token as Tokens.Heading;
      const hcolor = HEADING_COLORS[headingToken.depth - 1] || "#E5E7EB";
      return (
        <Box key={key} marginTop={headingToken.depth <= 2 ? 1 : 0}>
          <Text bold color={hcolor} wrap="wrap">
            {inlineTokens(headingToken.tokens, hcolor)}
          </Text>
        </Box>
      );
    }

    case "paragraph": {
      const paraToken = token as Tokens.Paragraph;
      return (
        <Box key={key}>
          <Text wrap="wrap" color={color}>
            {inlineTokens(paraToken.tokens, color)}
          </Text>
        </Box>
      );
    }

    case "text": {
      const textToken = token as Tokens.Text;
      return (
        <Box key={key}>
          <Text wrap="wrap" color={color}>
            {textToken.tokens ? inlineTokens(textToken.tokens, color) : textToken.text}
          </Text>
        </Box>
      );
    }

    case "blockquote": {
      const bq = token as Tokens.Blockquote;
      return (
        <Box key={key} flexDirection="column" paddingLeft={1}>
          <Box>
            <Text color={MUTED}>│ </Text>
            <Box flexDirection="column">
              {bq.tokens.map((t: Token, idx: number) => renderToken(t, color, idx))}
            </Box>
          </Box>
        </Box>
      );
    }

    case "list": {
      const listToken = token as Tokens.List;
      const start = listToken.start || 1;
      return (
        <Box key={key} flexDirection="column">
          {listToken.items.map((item: Tokens.ListItem, idx: number) => {
            const prefix = listToken.ordered ? `${start + idx}.` : "•";
            const blocks: Token[] = [];
            const nestedLists: Tokens.List[] = [];
            for (const t of item.tokens) {
              if (t.type === "list") {
                nestedLists.push(t as Tokens.List);
              } else {
                blocks.push(t);
              }
            }
            return (
              <Box key={idx} flexDirection="column">
                <Box>
                  <Text color={color}>{prefix} </Text>
                  <Box flexDirection="column">
                    {blocks.map((t: Token, j: number) => renderToken(t, color, j))}
                  </Box>
                </Box>
                {nestedLists.map((nl: Tokens.List, j: number) => (
                  <Box key={`nl-${j}`} marginLeft={2}>
                    {renderToken(nl, color)}
                  </Box>
                ))}
              </Box>
            );
          })}
        </Box>
      );
    }

    case "hr":
      return (
        <Text key={key} dimColor color={MUTED}>
          {"─".repeat(80)}
        </Text>
      );

    case "table": {
      const tableToken = token as Tokens.Table;
      return (
        <Box key={key} flexDirection="column">
          <Box>
            {tableToken.header.map((cell: Tokens.TableCell, idx: number) => (
              <Box key={idx} width={24}>
                <Text bold wrap="wrap" color={color}>
                  {inlineTokens(cell.tokens, color)}
                </Text>
              </Box>
            ))}
          </Box>
          <Box>
            {tableToken.align.map((_a: unknown, idx: number) => (
              <Box key={idx} width={24}>
                <Text dimColor color={MUTED}>
                  {"─".repeat(24)}
                </Text>
              </Box>
            ))}
          </Box>
          {tableToken.rows.map((row: Tokens.TableCell[], idx: number) => (
            <Box key={idx}>
              {row.map((cell: Tokens.TableCell, ci: number) => (
                <Box key={ci} width={24}>
                  <Text wrap="wrap" color={color}>
                    {inlineTokens(cell.tokens, color)}
                  </Text>
                </Box>
              ))}
            </Box>
          ))}
        </Box>
      );
    }

    default:
      return null;
  }
}

interface MarkdownProps {
  children: string;
  color?: string;
}

export function Markdown({ children, color = "#E5E7EB" }: MarkdownProps) {
  if (!children) return null;
  const tokens = marked.lexer(children);
  return (
    <Box flexDirection="column">
      {tokens.map((token, i) => (
        <Box key={i}>
          {renderToken(token, color, i)}
        </Box>
      ))}
    </Box>
  );
}

export default Markdown;
