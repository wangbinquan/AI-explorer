# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

Daily personal "research feed" agent. Each morning at 05:00 (configurable via `launchd`), it:

1. Fetches new items from several information sources (GitHub Trending / Rising, arXiv, Hacker News, HuggingFace daily papers).
2. De-duplicates against previously sent items (SQLite at `data/seen.db`).
3. Asks DeepSeek to score each item's relevance to a user-defined list of subscription topics in `config.yaml`, and to tag matched topics.
4. Drops anything below `llm.min_score` or with no matched topic; keeps top `llm.max_per_source` per source.
5. Asks DeepSeek to write a one-sentence Chinese summary for each kept item.
6. Renders an HTML digest via Jinja2 and sends it through 163 SMTP (SSL 465).

Single entry point: `python -m src.main` (the launchd job runs exactly this).

## Architecture (read these files together)

- **`src/main.py`** — orchestrator. The pipeline is `fetch_all → Dedup.filter_new → LLM.score → trim → LLM.summarize → mailer.send → Dedup.mark_sent`. Note: items that pass dedup but get filtered out by score are still marked sent, so we don't re-score them tomorrow.
- **`src/sources/`** — each source returns `Item` objects (`base.py`). New sources only need to subclass `Source`, implement `fetch()`, and be added to `REGISTRY` in `sources/__init__.py`. The key in `REGISTRY` must match the key under `sources:` in `config.yaml`.
- **`src/llm.py`** — DeepSeek client (uses OpenAI-compatible SDK; `base_url=https://api.deepseek.com`). `score()` batches up to 30 items per call and asks for JSON output. `summarize()` is one call per item — this is the dominant cost; tune `max_per_source` to control it.
- **`src/dedup.py`** — SQLite. Dedup key is `Item.fingerprint` = sha1(`source|id`). Each source must produce a stable, unique `id`.
- **`src/mailer.py`** — groups items by `source_label`, sorts by score desc, renders `templates/email.html`, sends via `smtplib.SMTP_SSL`.
- **`config.yaml`** — single source of truth for topics, source toggles/parameters, LLM thresholds, email/SMTP, and storage. No code changes needed to add a topic or tweak filtering.

## Common commands

```bash
# one-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in DEEPSEEK_API_KEY, EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO

# manual run (sends real email)
python -m src.main

# dry run — print kept items to stdout, don't send email, don't write dedup DB until end
python -m src.main --dry-run

# alternate config file
python -m src.main -c path/to/other.yaml
```

## Scheduling (launchd)

```bash
# install
cp launchd/com.explorer.daily.plist ~/Library/LaunchAgents/
launchctl load  ~/Library/LaunchAgents/com.explorer.daily.plist

# change time: edit StartCalendarInterval Hour/Minute in the plist, then:
launchctl unload ~/Library/LaunchAgents/com.explorer.daily.plist
launchctl load   ~/Library/LaunchAgents/com.explorer.daily.plist

# trigger now (for testing)
launchctl start com.explorer.daily

# logs
tail -f logs/explorer.out.log logs/explorer.err.log
```

The plist hardcodes an absolute Python path under the project's `.venv` (e.g. `/path/to/explorer/.venv/bin/python`) plus the matching `WorkingDirectory` and log paths — update all of them to your local checkout before `launchctl load`, and reload after any venv path change.

## Scheduling on Linux server (systemd)

Files live in `deploy/systemd/`:

- `explorer.service` — `Type=oneshot`，跑一次 `python -m src.main` 就退出
- `explorer.timer` — `OnCalendar=*-*-* 05:00:00`，每天 05:00 触发，`Persistent=true` 保证关机错过会补跑
- `deploy/install.sh` — 一键安装脚本（创建 `explorer` 用户、建 venv、装依赖、安装并启用 timer）

部署步骤（假定项目放在 `/opt/explorer`）：

```bash
# 1. 把代码放到服务器
sudo mkdir -p /opt/explorer
sudo rsync -a --exclude='.venv' --exclude='data' --exclude='logs' ./ /opt/explorer/

# 2. 配置 .env（DEEPSEEK_API_KEY / EMAIL_* 等；境外服务器把 HTTPS_PROXY 留空即可）
sudo cp /opt/explorer/.env.example /opt/explorer/.env
sudo vi /opt/explorer/.env

# 3. 一键安装
sudo bash /opt/explorer/deploy/install.sh
```

常用运维命令：

```bash
systemctl list-timers explorer.timer        # 看下次触发时间
systemctl start explorer.service            # 立刻手动跑一次
journalctl -u explorer.service -n 200       # 看最近一次运行的日志
tail -f /opt/explorer/logs/explorer.{out,err}.log

# 改时间：编辑 explorer.timer 里的 OnCalendar，然后
sudo systemctl daemon-reload
sudo systemctl restart explorer.timer
```

如果默认路径 `/opt/explorer` 或运行用户 `explorer` 不合适，要在两处同步改：`deploy/systemd/explorer.service`（`WorkingDirectory` / `ExecStart` / `User` / `Group` / `EnvironmentFile` / `StandardOutput` / `StandardError`）和 `deploy/install.sh` 顶部的 `APP_DIR` / `APP_USER`。

## Proxy（代理）行为

代码里所有需要走代理的 source（HuggingFace / Google Research / DeepMind / Meta AI）都遵循同一个规则：**配了就走代理，没配就直连**。

具体怎么走的：

1. `config.yaml` 里相关 source 的 `proxy:` 字段写的是 `${HTTPS_PROXY}`，由 `src/main.load_config` 在加载时做环境变量展开。
2. 环境变量没设置 → 展开成空字符串 → 各 source 内部 `if proxy else None`，等价于不传 `proxies`，`requests` 直连。
3. 环境变量在 `.env`（被 `python-dotenv` 读入）或 shell / systemd `EnvironmentFile` 里设置 → 展开成实际代理 URL，走代理。

国内 Mac 本地：`.env` 里加 `HTTPS_PROXY=http://127.0.0.1:1087`。
境外 Linux 服务器：`.env` 里这一行保持注释/不写就行，无需改 `config.yaml`。

## Adding a new source

1. Create `src/sources/yoursrc.py` with a `Source` subclass returning `list[Item]`. Each `Item.id` must be stable for dedup.
2. Register it in `src/sources/__init__.py` `REGISTRY` under a key like `"yoursrc"`.
3. Add a matching `yoursrc:` block under `sources:` in `config.yaml` with `enabled: true`.

## Adding/changing subscription topics

Edit `topics:` in `config.yaml`. Each entry has a `name` (shown as a tag in the email and used by the LLM as the topic label) and `keywords` (signals for the LLM scorer). No code change needed.

## 163 SMTP gotcha

`EMAIL_PASSWORD` must be the **client authorization code** (set under 163 webmail → 设置 → POP3/SMTP/IMAP), **not** the account login password. If sending fails with `535 Error: authentication failed`, that's almost always the reason.

## Cost notes

- Scoring: 1 DeepSeek call per ~30 items (cheap).
- Summarization: 1 call per kept item — the only cost that scales with output size. Lower `llm.max_per_source` or raise `llm.min_score` to cut spend.
