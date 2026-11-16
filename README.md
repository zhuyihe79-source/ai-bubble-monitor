# AI 泡沫监测

每天采集免费公开数据，算出 0–100 的“AI 泡沫温度”和“市场宽松度”，加上 11 个破裂信号和 AI 分析师的新闻评级，发布成静态看板。

## 运行

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export SEC_USER_AGENT="你的名字 you@example.com"   # SEC 要求带联系方式
.venv/bin/bubblemon-fetch                           # 采集；可加 --only id1 id2
.venv/bin/streamlit run app/dashboard.py
.venv/bin/bubblemon-report                          # 生成独立 HTML 看板 data/dashboard.html
.venv/bin/pytest
```

## 结构

- `config/indicators.yaml`：指标注册表。新增指标只改这里（加 fetcher 时再改代码）。
- `src/bubblemon/fetchers/`：每个数据源一个采集器，统一返回 `pd.Series`（日期 → 值）。
- `src/bubblemon/db.py`：DuckDB，表 `observations(date, indicator_id, value, source, fetched_at)` 和 `fetch_log`。
- `src/bubblemon/scoring.py`：周频对齐 → 15 年滚动分位 → 维度均值 → AI 泡沫温度和市场宽松度。
- `src/bubblemon/alerts.py`：AI 泡沫温度越线、单指标极端值。
- `data/manual/*.csv`：没有免费接口的指标可以手工录入（`date,value`，`source: manual`），目前没有使用。

## 评分方法

看板有两个分数，分开看：

- **AI 泡沫温度**：只用和 AI 直接相关的维度（估值与集中度、投入与回报），从 2023 年开始计算。回答“AI 这一轮有多热”。
- **市场宽松度**：信用利差、VIX、利率三个维度。它们衡量的是整个市场的风险偏好，2017、2021 年同样很高，所以不放进 AI 温度，只作为大环境参考：宽松度高时，泡沫更容易被吹大，也更经不起冲击。

计算步骤：

1. 每个指标转成周频（周五），前值填充；超过 `max_stale_days` 视为缺失。
2. 季度财报数据按 `publication_lag_days`（35 天）后移，避免历史分数用到当时还没公布的数据。
3. 取过去最多 15 年（至少 3 年）的滚动分位；`direction: low` 的指标取 `1 - 分位`。
4. 维度内等权平均，维度间按 `weight` 加权，乘以 100。维度属于哪个分数由 `group`（`ai` / `market`）决定。
5. AI 温度至少 `min_dimensions` 个维度有数据才发布，且只发布 `ai_start`（2023-01-01）之后的读数。更早的读数衡量的不是 AI：旧版把信用、波动、利率也算进来，2017 年底会显示 82 分。
6. 增长型序列用增速而不是金额（capex 用同比），否则分位常年贴着 100。
## 破裂信号与每周解读

AI 泡沫温度回答“有多热”，破裂信号回答“有没有开始破”。两者分开看。

- `config/indicators.yaml` 的 `triggers:` 定义 11 个信号，每个有警戒线、触发线和“为什么重要”。改阈值只改这里。
- 信号状态可以按任意日期回算（`triggers.evaluate(series, cfg, asof)`），财报数据按季末后 35 天才算可见，所以历史状态不会用到当时还没公布的数据。
- 每周解读（`commentary.weekly_note`）自动生成：信号状态变化、AI 温度变化拆到具体指标、市场周表现、最新财报要点、需要盯住的信号。看板保留最近 8 周。
- 新增的价格、单季 capex、NVDA 收入、云厂商有息负债序列标了 `score: false`，只用于信号和解读，不进入任何分数。
- 云厂商有息负债 = 长期债务（非流动）+ 一年内到期部分，不含租赁负债。合并序列从 2023 年底开始，因为 Meta 更早的季度申报有缺口。

## 新闻与分析师周报

新闻不是爬虫抓的，由定时任务里的 AI 分析师按 `analyst/GUIDE.md` 阅读、核实、打分后写入仓库。

- `news/YYYY-MM-DD.json`：当天收录的新闻，四个主题（存储、英伟达、融资、需求），每条有重要性 1–5、风险方向、可选的关联破裂信号。
- `notes/YYYY-MM-DD.md`：分析师周报，每周一写，出现重要性 5 的新闻时加写。
- `bubblemon-news-check`：校验新闻文件格式，提交前必须通过。
- 看板显示最新周报、近 7 天要闻和各主题 8 周新闻热度（重要性 ≥ 3 的条数和风险净方向）。新闻不进入泡沫温度的计算。
- **分析师风险评级（1–5）**：近 7 天新闻按重要性加权的净方向，按固定规则换算成规则值；分析师每次运行可在规则值上下各调一级并写明理由（新闻文件的 `assessment`）。显示在泡沫温度旁边，规则见 `analyst/GUIDE.md`。
- **新闻预警**：关联到某个破裂信号、重要性 ≥ 4、风险上升的新闻，会在信号表里标出，作为财报数据到来前的提前提示。

## 已知局限

- **历史太短的指标不计分**：只有 3 年左右历史的指标分位意义很弱，而且一加入就会让分数跳变。高收益债利差（FRED 只给近 3 年）和 Google 搜索“AI bubble”+“AI crash”（2023 年前几乎没人搜）因此设为 `score: false`，只用于破裂信号。看板会标出新加入或缺数据的指标。
- **AI 温度只有两个维度**：估值与集中度、投入与回报。GPU 租金没有可靠的免费长历史数据，不纳入。季度财报公布那一周（季末后约 35 天）温度会跳一下，这是真实数据更新。
- **分位只和自身历史比**：AI 温度 80 以上说明这些指标处在过去 15 年的高位，不等于和 2000 年互联网泡沫一样极端。SPY/RSP、TIPS 实际利率等序列起点较晚，无法回测 1999–2000 年。- **FRED 的 ICE BofA 高收益利差只给近 3 年**，所以另加了 Moody's Baa 利差（`BAA10Y`）作长历史替代。
- **Google Trends 是相对值**，且会限流（只用于破裂信号）；失败只记录在 `fetch_log`，不会中断其他指标。
- **GPU 租赁价、融资余额（FINRA）、循环融资关系**没有接入；这些方面靠分析师新闻评级覆盖。
- 破裂信号的阈值是经验设定，没有用历史回测校准。
- 指标方向（`direction`）和维度权重是主观设定，没有做过校准。

## 上线（GitHub Pages）

1. 把项目推到 GitHub 仓库，默认分支叫 `main`。
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**。
3. （可选）Settings → Secrets and variables → Actions，新建 secret `SEC_USER_AGENT`，值如 `你的名字 you@example.com`。不设置会用默认值。不要用 GitHub 的 `noreply` 邮箱，SEC 会返回 403。
4. Actions 页手动运行一次 `publish-dashboard`，之后每个工作日自动更新。网址是 `https://<用户名>.github.io/<仓库名>/`。

注意：Pages 在免费账号下要求仓库公开；私有仓库需要付费计划。看板是纯静态页面，没有后端。
