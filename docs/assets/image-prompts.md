# Image Prompts

These prompts describe the README visuals. The repository uses SVG files so the images stay editable, lightweight, and easy to render on GitHub.

## Hero Architecture

### 中文提示词

为一个开源项目 README 生成一张专业、清爽、适合中国开发者和科研用户阅读的产品架构图。主题是 “jamovi MCP：让 Claude、Cursor 等 MCP 客户端直接调用本地 jamovi 做统计分析”。画面为浅色背景，横向结构，从左到右依次是 “MCP 客户端 Claude/Cursor”、中间 “jamovi MCP Python 服务器”、右侧 “本地 jamovi engine”。底部突出 “仅本地运行 127.0.0.1”。加入数据表、柱状图、统计分析结果等小元素。所有核心文字必须使用简体中文，英文只保留必要技术名词，例如 MCP、WebSocket、protobuf、jamovi。风格简洁、可信、工程化，不要赛博朋克，不要机器人，不要夸张渐变，不要暗黑背景。画面比例 1200x620，适合 GitHub README 顶部展示。

### English Prompt

Create a professional light-theme architecture graphic for an open-source README. The project is "jamovi MCP", which lets Claude, Cursor, and other MCP clients control a local jamovi engine for statistical analysis. Use a horizontal left-to-right layout: "MCP 客户端 Claude/Cursor" on the left, "jamovi MCP Python 服务器" in the center, and "本地 jamovi engine" on the right. Highlight "仅本地运行 127.0.0.1" near the bottom. Include small visual elements for a dataset table, bar chart, and analysis results. All primary text must be Simplified Chinese; keep English only for necessary technical terms such as MCP, WebSocket, protobuf, and jamovi. Keep the style clean, trustworthy, technical, and readable for Chinese developers and researchers. Avoid cyberpunk, robots, heavy gradients, dark backgrounds, and decorative clutter. Aspect ratio 1200x620 for a GitHub README hero image.

### Negative Prompt

Dark cyberpunk scene, humanoid robot, abstract AI brain, glossy marketing poster, unreadable tiny text, excessive gradients, cluttered dashboard, stock photo, 3D cartoon, distorted Chinese characters, low contrast.

## Workflow

### 中文提示词

为一个开源项目 README 生成一张清晰的使用流程图，主题是 “从一句话到 jamovi 分析结果”。画面展示用户在 MCP 客户端输入中文请求：“打开 survey.csv，查看变量，读取前 10 行，运行 t 检验，然后保存为 analysis.omv。” 下方用 5 个步骤卡片横向排列：1 打开数据，2 查看 Schema，3 读写单元格，4 运行分析，5 保存 OMV。每个步骤带简洁图标，说明文字以简体中文为主，只保留必要工具名如 jamovi_open、jamovi_get_schema、jamovi_run_analysis。风格适合中国科研、教学和数据分析用户，浅色背景，专业、现代、干净，适合 GitHub README。画面比例 1200x520。

### English Prompt

Create a clean workflow graphic for an open-source README titled in Simplified Chinese, "从一句话到 jamovi 分析结果". Show a Chinese user request in an MCP client: "打开 survey.csv，查看变量，读取前 10 行，运行 t 检验，然后保存为 analysis.omv." Below it, show five horizontal step cards in Simplified Chinese: 1 打开数据, 2 查看 Schema, 3 读写单元格, 4 运行分析, 5 保存 OMV. Each card should include a simple icon. Keep Chinese as the dominant language and preserve only necessary tool names such as jamovi_open, jamovi_get_schema, and jamovi_run_analysis. Use a light professional style suitable for Chinese researchers, students, and data analysts. Make it modern, readable, and GitHub README friendly. Aspect ratio 1200x520.

### Negative Prompt

Busy infographic, dark mode, cartoon mascot, unreadable text, fake UI screenshots, excessive shadows, stock photography, distorted Chinese characters, overly decorative background.
