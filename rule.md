# MCP Interactive Feedback 规则

1. 在任何流程、任务、对话进行时，无论是询问、回复、或完成阶段性任务，皆必须调用 MCP mcp-interactive-feedback。

2. 每当收到用户反馈，若反馈内容非空，必须再次调用 MCP mcp-interactive-feedback，并根据反馈内容调整行为。

3. 仅当用户明确表示「结束」或「不再需要交互」时，才可停止调用 MCP mcp-interactive-feedback，流程才算结束。

4. 除非收到结束指令，否则所有步骤都必须重复调用 MCP mcp-interactive-feedback。

5. 完成任务前，必须使用 MCP mcp-interactive-feedback 工具向用户询问反馈。

6. 当用户提供图片时，要仔细分析图片内容并在后续交互中参考图片信息。

7. 利用终端功能执行必要的命令来验证或实施用户的需求。