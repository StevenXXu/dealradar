# DealRadar: 预测性交易情报系统 (Predictive Deal Intelligence CRM)
## 全局商业企划与技术执行总纲 (Master Blueprint)

**项目代号:** DealRadar
**定位:** 一级市场预测性投研 SaaS 平台 / INP Capital 独家项目雷达
**核心引擎:** AI 驱动的数据采集、深度研判与融资时钟预测

---

## 🟢 第一部分：商业化战略与产品愿景 (Business Strategy)

### 1. 核心痛点与产品愿景
*   **行业痛点：** 传统一级市场投研（如 Crunchbase、Pitchbook）严重依赖“后视镜”数据，只能看到已发生的交易。机构获取项目高度依赖人脉，缺乏前瞻性的 Proprietary Deal Flow（独家/水下项目源）。
*   **产品定位：** DealRadar 是一款“预测性交易情报系统”。它不仅监控顶级 VC 的投资组合，更通过 AI 捕捉目标公司的底层业务动作，**在交易（融资/并购）发生前 3-6 个月，向用户发出狙击警报**。

### 2. 目标客群与阶梯定价 (Commercialization)
*   **Tier 1: 精品 VC / 家族办公室 ($499 - $999 / 月)**
    *   *功能:* 基础竞品 VC 追踪，自动获取 1000+ 公司的富化数据，基础融资预警。
*   **Tier 2: 投行 FA / 企业 M&A 部门 ($2,500+ / 月)**
    *   *功能:* 无限追踪，深度跨国信号定制（如“只要红杉投的医疗公司招募澳洲员工即报警”），API 接入。
*   **Tier 3: INP Capital 隐藏变现端 (The Big Money)**
    *   *功能:* 平台数据霸权。系统发现优质的跨境或 Pre-IPO 标的，INP 直接下场做 FA 或跟投（Secondary Market / 跨境并购），赚取百万级美元的 Deal Carry 和 Advisor Fee。

---

## 🔵 第二部分：AI Agent 技术架构与执行计划 (Technical Architecture)

此部分为研发团队与 AI Agent（如 AutoGPT / CrewAI）的直接执行指令。

### 1. Agent 身份定义 (System Prompt)
> **Role:** 你是一个名为 "Radar-Architect" 的资深全栈工程师与量化投资分析师。你的任务是构建 DealRadar MVP，一个能够自动抓取 VC Portfolio、分析企业动态并预测融资需求的智能系统。
> **Objective:** 建立一个自动化的数据管道，将公开的“弱信号”转化为高价值的“确定性情报”。

### 2. MVP 技术架构设计 (The 3 Modules)

#### 模块 A：数据采集引擎 (The Harvester)
*   **技术栈:** Python, Firecrawl / Apify, BeautifulSoup4。
*   **输入:** 包含顶级 VC 官网 URL 的种子列表。
*   **任务:**
    1.  爬取 Portfolio 页面，提取：公司名称、官网 URL、行业分类、上一轮融资阶段。
    2.  对每个公司官网进行二次深度爬取（Focus on: `/about`, `/news`, `/careers`）。

#### 模块 B：智能研判引擎 (The AI Reasoner)
*   **技术栈:** GPT-4o 或 Claude 3.5 Sonnet (API)。
*   **处理逻辑:**
    *   **语义提炼:** 将杂乱的官网文本压缩成 100 字以内的业务核心说明。
    *   **信号提取:** 搜索核心关键词：*CFO, VP of Finance, Global Expansion, Strategic Partnership, Series B*。
    *   **融资时钟计算 (Funding Clock - 优化版):**
        利用爬取到的员工人数 (Headcount) 估算烧钱率：
        `Avg. Monthly Burn ≈ Headcount × (Industry Avg. Salary + 30% Overhead)`
        `Days Remaining = (Last Round Amount / Avg. Monthly Burn) - Time Elapsed`

#### 模块 C：终端输出层 (The Commander)
*   **集成:** Airtable API 或 Notion API。
*   **数据字段:** Company Name | Domain | Signal Score (0-100) | Predicted Window | Intelligence Tags | Lead Source。

---

## 🟠 第三部分：详细行动方案 (Action Plan)

### 第一阶段：环境初始化与种子抓取 (Day 1-2)
*   **任务 1.1:** 编写脚本，访问 [Sequoia, Blackbird, Matrix] 等 10 家顶级 VC 官网。
*   **任务 1.2:** 利用 LLM 解析动态 HTML 结构，统一输出为 JSON 格式的项目池。
*   **任务 1.3:** 数据清洗，剔除已倒闭或已公开发行 (IPO) 的无效干扰项。

### 第二阶段：多维信号抓取与评分 (Day 3-5)
*   **任务 2.1 (招聘信号):** 监控目标公司 Careers 页面或招聘聚合平台。若出现“财务总监(CFO)”或“合规官(General Counsel)”岗位，**加 40 分**（强 Pre-IPO 信号）。
*   **任务 2.2 (扩张信号):** 监控官网多语言版本更新或特定区域招聘。若新增“Chinese”或“APAC 业务负责人”，标记为 `[✈️ Cross-Border Target]`。
*   **任务 2.3 (资金预测):** 结合外部融资数据（Crunchbase API等），计算融资倒计时。若距离上次融资超过 18-24 个月，**加 30 分**。

### 第三阶段：Airtable 自动化看板构建 (Day 6-7)
*   **任务 3.1:** 通过 API 创建 Airtable 表结构并导入富化后的 JSON 数据。
*   **任务 3.2:** 设置自动化规则：当 `Signal Score > 80` 时，自动给用户（Steven）发送 Slack 或邮件高优提醒。
*   **任务 3.3:** 生成周报模版，输出每周“最值得接触的 5 个独角兽/潜客项目”。

---

## 🔴 第四部分：关键逻辑算法与合规防护 (Logic Hooks & Guardrails)

### 1. 核心研判算法 (Logic Hooks)
为了让 Agent 具备真实投资人的嗅觉，强制执行以下判断树：

> **IF** 目标公司招聘 "Head of Supply Chain" **AND** 行业属于 "Robotics / Hardware"
> **THEN** 触发标签 `[Venture_Nexus_Potential]`
> **ACTION:** 搜索该公司在中国的潜在竞对或供应链伙伴，生成跨境 FA 切入点。

> **IF** 目标公司上一轮融资为 $10M - $20M **AND** 距今 >= 15 个月
> **THEN** 触发标签 `[⚠️ Funding_Urgency_High]`
> **ACTION:** 推送到“老股转让 (Secondary Market)”观察名单，提示准备 Outreach 话术。

### 2. 异常处理与合规防护 (Exception Handling)
1.  **反爬与接口保护 (Rate Limiting):** Agent 必须在抓取请求之间设置随机延迟（2-5s）；针对 LinkedIn 等高防御网站，必须调用合法商业 Proxy API (如 Proxycurl/Coresignal) 而非直接硬爬。
2.  **准确性追溯 (Accuracy Check):** AI 生成的所有判断和总结，必须附带原始网页链接（Source Citation），以便人工尽调回溯。
3.  **Token 成本控制 (Cost Control):** 对长文本进行 Token 压缩，仅将包含关键 `<p>` 标签的 `About Us` 和 `News` 片段输入大模型上下文，避免 API 费用失控。
