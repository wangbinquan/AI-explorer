# Explorer · 每日 AI 研究订阅

每天早上 05:00 自动从十几个信息源拉取最新内容，调用 DeepSeek 按订阅话题打分、过滤、生成中文一句话摘要，最后通过 163 SMTP 把 HTML 摘要邮件发到指定邮箱。

单一入口：`python -m src.main`。完整架构、部署、二次开发说明见 [CLAUDE.md](./CLAUDE.md)。

## 信息源一览

下表列出仓库内所有已注册的信息源（对应 `src/sources/` 下的实现，开关与参数在 `config.yaml` 的 `sources:` 段）。

| 信息源 key | 来源说明 | 抓取 URL（接口/页面/RSS） | 采集周期 | 主要采集参数（默认值） |
| --- | --- | --- | --- | --- |
| `github_trending` | GitHub Trending 榜单（HTML 抓取） | `https://github.com/trending` 与 `https://github.com/trending/{language}?since={daily,weekly,monthly}` | 每天 05:00（窗口由 `since` 决定） | `languages: ["", python, rust, go, typescript]`（`""` = all）<br>`since: daily` |
| `github_rising` | 近 N 天内新建、stars 上升较快的仓库（GitHub Search API） | `https://api.github.com/search/repositories`（query：`created:>YYYY-MM-DD stars:>=N`） | 每天 05:00 | `days: 7`<br>`min_stars: 100`<br>`max_results: 50`<br>可选环境变量 `GITHUB_TOKEN`（速率 60→5000/h） |
| `arxiv` | arXiv 多个 CS 子分类的最新 submissions | `https://export.arxiv.org/api/query`（Atom feed） | 每天 05:00（取近 `days` 天） | `categories: [cs.AI, cs.CL, cs.LG, cs.SE, cs.MA, cs.DC, cs.PL, cs.OS, cs.PF, cs.FL]`<br>`max_per_category: 30`<br>`days: 7` |
| `hackernews` | Hacker News 高分帖（Algolia 搜索 API） | `https://hn.algolia.com/api/v1/search`（按时间过滤、`numericFilters=points>=N`） | 每天 05:00（取近 `days` 天） | `min_points: 150`<br>`days: 2`<br>`max_results: 60` |
| `huggingface_papers` | HuggingFace Daily Papers 列表 | `https://huggingface.co/papers`（HTML 抓取） | 每天 05:00 | `max_results: 30`<br>`base_url: https://huggingface.co`<br>`proxy: ${HTTPS_PROXY}`（国内需走代理） |
| `huggingface_blog` | HuggingFace 官方博客 | `https://huggingface.co/blog/feed.xml` | 每天 05:00（取近 `days` 天） | `max_results: 15`<br>`days: 14`<br>`proxy: ${HTTPS_PROXY}` |
| `qbitai` | 量子位（中文 AI 资讯） | `https://www.qbitai.com/feed`（WordPress RSS） | 每天 05:00（取近 `days` 天） | `max_results: 20`<br>`days: 2` |
| `anthropic` | Anthropic News / Research / Engineering | `https://www.anthropic.com/sitemap.xml`（按 section 过滤） | 每天 05:00（取近 `days` 天） | `sections: [news, research, engineering]`<br>`max_results: 15`<br>`days: 14` |
| `openai` | OpenAI Engineering / Research 文章 | `https://openai.com/sitemap.xml`（仅这两个 section 的 `lastmod` 是真实发布时间） | 每天 05:00（取近 `days` 天） | `sections: [engineering, research]`<br>`max_results: 15`<br>`days: 14` |
| `google_research` | Google Research 博客 | `https://research.google/blog/rss/`（旧 `ai.googleblog.com` 已 301 跳转） | 每天 05:00（取近 `days` 天） | `max_results: 15`<br>`days: 14`<br>`proxy: ${HTTPS_PROXY}` |
| `deepmind` | Google DeepMind 博客 | `https://deepmind.google/blog/rss.xml`（`www.deepmind.com` 已 302 跳转） | 每天 05:00（取近 `days` 天） | `max_results: 15`<br>`days: 14`<br>`proxy: ${HTTPS_PROXY}` |
| `meta_ai` | Meta AI 博客 | `https://ai.meta.com/blog/`（HTML 列表，`ai.facebook.com/blog` 已 301 跳转） | 每天 05:00（取近 `days` 天） | `max_results: 15`<br>`days: 30`（Meta 发布频次较低） <br>`proxy: ${HTTPS_PROXY}` |

> **采集周期统一说明**：每天由 launchd（macOS, `launchd/com.explorer.daily.plist`）或 systemd timer（Linux, `deploy/systemd/explorer.timer`，`OnCalendar=*-*-* 05:00:00`）触发一次完整 pipeline。`days` 控制每个源向前回看的窗口大小，`max_results` / `max_per_category` 控制每次抓取的上限。

## 订阅话题（`topics:`）

打分时 LLM 会判断每条 item 是否命中以下任一话题；命中后才会进入摘要阶段。完整 keywords 在 `config.yaml`。

| 话题 | 关键词示例 |
| --- | --- |
| AI | AI, LLM, foundation model, GPT, Claude, Gemini |
| AI编程 | AI coding, copilot, cursor, codex, AI IDE |
| Agent | agent, tool use, ReAct, function calling |
| MultiAgent | multi-agent, agent orchestration |
| AgentTeam | swarm, crew, AutoGen, CrewAI |
| VibeCode | vibe coding, AI-native development |
| Harness | claude code, cline, aider, agentic harness |
| 软件工程 | SWE, code review, refactoring, CI/CD, devex |
| 大数据 | data engineering, lakehouse, spark, flink, kafka, iceberg |
| 云化 | cloud native, serverless, multi-cloud, kubernetes |
| 容器化 | docker, k8s, OCI, podman, containerd |
| 函数式编程 | haskell, scala, ocaml, monad, immutability |
| eBPF | bpf, XDP, cilium, bcc, bpftrace, tetragon |

## LLM 与邮件参数

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `llm.base_url` | `https://api.deepseek.com` | DeepSeek OpenAI 兼容端点 |
| `llm.model` | `deepseek-v4-pro` | 同时用于打分和摘要 |
| `llm.min_score` | `6` | 0–10 分，低于此值丢弃 |
| `llm.max_per_source` | `8` | 每个源最多保留几条进邮件（直接影响摘要调用次数与成本） |
| `llm.summary_lang` | `zh` | 摘要语言 |
| `email.smtp_host` | `smtp.163.com` | |
| `email.smtp_port` | `465` | SSL |
| `email.subject_prefix` | `[Explorer] 每日订阅` | 主题前缀，会自动追加日期 |
| `storage.db_path` | `data/seen.db` | SQLite 去重库 |
| `storage.retention_days` | `30` | 去重保留天数 |

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填 DEEPSEEK_API_KEY / EMAIL_FROM / EMAIL_PASSWORD / EMAIL_TO

# 试跑（不发邮件、不写 dedup）
python -m src.main --dry-run

# 正式跑一次
python -m src.main
```

定时部署（macOS launchd / Linux systemd）见 [CLAUDE.md](./CLAUDE.md) 的 “Scheduling” 两节。
