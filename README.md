# IdeaSpark · AI 虚拟创业团队

> 输入一句商业想法，五位 AI 角色自动协作：产出调研 / PRD / 技术方案 / 运营计划，并生成一个**公网可访问、内置可交互核心功能**的产品页面，收集订阅线索并回流增长数据。

对标 Astoms 的"先澄清、再执行"交互范式：创建项目后 AI 产品经理会先分析歧义、向你确认关键配置（视觉风格 / 价值主张 / 板块 / 商业模式），团队再严格按你的选择生成全部产出。

## 界面一览

| 首页 · 一句话创建 | 项目工作台 |
|---|---|
| ![首页](docs_img/01_home.png) | ![工作台](docs_img/02_workspace.png) |

| 落地页 · 复习计划生成器 | 落地页 · 爆款标题生成器 |
|---|---|
| ![教育](docs_img/03_landing_edu.png) | ![AI](docs_img/04_landing_ai.png) |

## 核心功能

- **一句话创建**：自动解析产品名、目标人群与痛点
- **澄清式流程**：Questions 配置卡（风格 / 卖点 / 板块 / 商业模式），选 1 个风格自动跳过赛马，选买断制价格板块直接按买断生成
- **AI 团队实时产出**：市场研究员 / 产品经理 / 架构师 / 运营增长，SSE 流式输出
- **Race 赛马**：同时生成深色 / 浅色两版落地页竞标，或单方案直接采纳
- **对话式迭代**："口号改成 XX"、"主题换绿色"、"加上价格板块"，未识别指令自动进入需求待办
- **版本管理**：每次迭代存快照，可回退任意版本
- **一键发布**：落地页公开访问（自包含 HTML），内置按赛道生成的可交互功能模块（复习计划 / 标题生成 / 用药提醒 / 报价计算等 5 类）
- **增长看板**：PV / UV / 订阅 / 转化率 / 7 日趋势，爬虫 UA 自动过滤，15 秒自动刷新
- **安全**：全站 CSRF、XSS 转义 + 主题色白名单、公开表单蜜罐反垃圾

## 快速开始

```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:5050
```

运行自动化测试（需先启动应用）：

```bash
python smoke_test.py
```

## 技术栈与架构

Flask + Jinja2 + SQLite(WAL) + SSE，无构建链，`python app.py` 即跑。

- 生成引擎（[generator.py](generator.py)）为确定性规则实现，`compose_*` / `build_app` / `apply_command` 均按可替换纯函数设计，可直接平替为 LLM 调用
- 数据层（[db.py](db.py)）：users / projects / artifacts / versions / visits / leads / todos 共 7 张表，WAL 并发，启动自动迁移
- 详细的实现取舍、完成度与扩展路线见 [TECHNICAL_DOC.md](TECHNICAL_DOC.md)（PDF 版同目录）

## License

MIT
