# 类案检索速配智能体

这是一个用 Python 标准库实现的 Web 演示应用，面向课堂作业、案例分析训练和模拟法庭准备，支持本地运行和公网部署。

## 功能

- 自然语言案情解析：提取行为、主体、责任类型和法律要素。
- 争议焦点匹配：把问题转换为可检索的焦点和关键词。
- Top 3 类案卡片：统一展示案号、法院、日期、相似点、差异点、裁判要旨和可借鉴角度。
- 学习型摘要：输出案情概括、争议焦点、法院观点、裁判结果和可引用要旨。
- 智能问答：围绕主播责任、平台责任、原告/被告立场提供论证提示。
- 导出报告：下载 Markdown 格式的类案速配报告。
- 多源案例检索 Agent：根据当前案情生成人民法院案例库、微信公众号公开内容和网页检索式、备用检索式、筛选步骤，并一键打开相关公开检索入口。
- 外部案例库：优先从 `cases.json` 读取案例，可按领域持续扩展。

## 启动

```bash
python3 web_app.py
```

打开浏览器访问：

```text
http://127.0.0.1:8765
```

如果希望同一 Wi-Fi 或局域网里的其他设备访问，请先查看本机 IP 地址，然后让对方访问：

```text
http://你的电脑IP:8765
```

例如本机 IP 是 `192.168.1.23`，访问地址就是：

```text
http://192.168.1.23:8765
```

如果希望互联网中的任何人都能访问，需要部署到云服务器、Render、Railway、Vercel/Serverless Python 平台，或使用 ngrok、Cloudflare Tunnel 等内网穿透工具。

## 制作公开网址（Render）

项目已经配置为监听 `0.0.0.0`，并附带 `render.yaml`。`0.0.0.0` 不是供人打开的网址，它表示程序接受部署平台转发的外部访问。真正的公开网址由 Render 在部署成功后生成。

1. 把本项目上传到你自己的 GitHub 仓库。
2. 登录 Render，选择 **New + → Blueprint**。
3. 连接该 GitHub 仓库，Render 会自动读取 `render.yaml`。
4. 在 Render 的环境变量中填写 `OPENAI_API_KEY`；建议同时填写 `APP_PASSWORD`，避免任何人无限制使用你的 API。
5. 部署完成后，Render 会显示形如 `https://case-search-agent-xxxx.onrender.com` 的公开网址。

本地运行时仍然打开：

```text
http://127.0.0.1:8765
```

## 说明

当前优先读取 `cases.json` 作为本地案例库。案例名称、案号和法院信息如标注为示例数据，则仅用于展示智能体工作流，不应当作为真实判例引用。

新增案例时，在 `cases.json` 中追加对象即可。建议保留这些字段：

```json
{
  "title": "案例名称",
  "docket": "案号",
  "court": "法院",
  "date": "2024-01-01",
  "cause": "案由",
  "domain": "餐饮消费",
  "facts": "案情摘要",
  "issues": ["争议焦点一", "争议焦点二"],
  "holding": "裁判要旨",
  "reasoning": "裁判理由",
  "result": "裁判结果",
  "tags": ["餐饮服务", "格式条款", "消费者权益"],
  "support_for": "消费者",
  "quote": "可引用裁判观点",
  "source": "来源链接或来源说明"
}
```

领域 `domain` 很重要。系统会让全部本地案例参与初筛，再对同领域案例加权，并设置逐条可信度门槛，避免把低相关案例凑进 Top 3。

“多源案例检索 Agent”不会绕过登录、验证码、关注公众号、付费阅读或网站访问限制。它适合辅助生成检索策略、打开公开检索入口并整理公开结果；如果页面要求人工确认，需要由用户在浏览器里接管。引用微信公众号文章中的案例时，应尽量回到法院官网、裁判文书或权威发布来源核验。


## 接入 AI 案情理解 API

新版智能体使用“AI 案情理解 + 本地案例库检索”。AI 只负责提取案由、领域、主体、争议焦点、法律要素和检索关键词，每次检索最多调用一次；候选案例只来自 `cases.json`，不会要求 AI 生成案号或判例。AI 不可用时会自动降级到本地规则。

默认已使用 OpenAI-compatible 聊天接口模式。使用 OpenAI 官方接口时，在项目目录新建 `.env` 文件：

```bash
OPENAI_API_KEY="sk-你的密钥"
```

然后直接启动：

```bash
python3 web_app.py
```

不要把 `.env` 发给别人，也不要上传到 GitHub。

如果使用其他兼容服务商，再覆盖服务地址和模型：

```bash
export LEGAL_KB_API_URL="https://你的服务地址/v1/chat/completions"
export LEGAL_KB_API_KEY="你的密钥"
export LEGAL_KB_MODEL="你的法律知识库模型或应用ID"
python3 web_app.py
```

可选配置：

```bash
export LEGAL_KB_TOP_K=10
export LEGAL_KB_TIMEOUT=15
export LEGAL_KB_EXTRA_HEADERS='{"X-App-Id":"your-app-id"}'
```

默认会调用 OpenAI-compatible 模型做一次 AI 深度案情分析，用于覆盖规则生成的案由、争议焦点、法律要素和检索关键词，然后只匹配 `cases.json` 中的案例。可按需关闭或提高推理强度：

```bash
export LEGAL_KB_DEEP_ANALYSIS=0          # 关闭 AI 深度案情分析
export LEGAL_KB_REASONING_EFFORT=high    # 服务商支持 reasoning_effort 时再开启
```


### Render 公网部署访问密码

部署到 Render 时，建议在 Environment Variables 中同时添加：

```text
OPENAI_API_KEY=你的 OpenAI 密钥
APP_PASSWORD=你想设置的访问密码
```

设置 `APP_PASSWORD` 后，打开网页会先要求输入访问密码；不设置则保持公开访问。不要把 `.env` 或真实密钥上传到 GitHub。

### 无真实 API 时进行模拟测试

```bash
export LEGAL_KB_MOCK_FILE="/Users/fairy/Desktop/case-search-app/legal_kb_mock.example.json"
python3 web_app.py
```

启动后，页面右上角会显示知识库状态；也可以访问：

```text
http://127.0.0.1:8765/api/status
```

查看当前连接模式、本地案例数量和 Top K 配置。模拟文件中的内容不是现实判例，不得用于作业引用。
