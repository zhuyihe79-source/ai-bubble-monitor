# AI 泡沫监测

每天采集免费公开数据，算出 0–100 的“泡沫温度”，用 Streamlit 展示。

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
- `src/bubblemon/scoring.py`：周频对齐 → 15 年滚动分位 → 维度均值 → 总分。
- `src/bubblemon/alerts.py`：总分越线、单指标极端值。
- `data/manual/*.csv`：没有免费接口的指标手工录入（`date,value`），目前有 `gpu_h100_rental.csv`（空）。

## 评分方法

1. 每个指标转成周频（周五），前值填充；超过 `max_stale_days` 视为缺失。
2. 季度财报数据按 `publication_lag_days`（35 天）后移，避免历史分数用到当时还没公布的数据。
3. 取过去最多 15 年（至少 3 年）的滚动分位；`direction: low` 的指标取 `1 - 分位`。
4. 维度内等权平均，维度间按 `weight` 加权，乘以 100。
5. 至少 `min_dimensions` 个维度有数据才发布总分。

## 破裂信号与每周解读

泡沫温度回答“有多热”，破裂信号回答“有没有开始破”。两者分开看。

- `config/indicators.yaml` 的 `triggers:` 定义 12 个信号，每个有警戒线、触发线和“为什么重要”。改阈值只改这里。
- 信号状态可以按任意日期回算（`triggers.evaluate(series, cfg, asof)`），财报数据按季末后 35 天才算可见，所以历史状态不会用到当时还没公布的数据。
- 每周解读（`commentary.weekly_note`）自动生成：信号状态变化、总分变化拆到具体指标、市场周表现、最新财报要点、需要盯住的信号。看板保留最近 8 周。
- 新增的价格、单季 capex、NVDA 收入、云厂商有息负债序列标了 `score: false`，只用于信号和解读，不改变泡沫温度的算法。
- 云厂商有息负债 = 长期债务（非流动）+ 一年内到期部分，不含租赁负债。合并序列从 2023 年底开始，因为 Meta 更早的季度申报有缺口。

## 新闻与分析师周报

新闻不是爬虫抓的，由定时任务里的 AI 分析师按 `analyst/GUIDE.md` 阅读、核实、打分后写入仓库。

- `news/YYYY-MM-DD.json`：当天收录的新闻，四个主题（存储、英伟达、融资、需求），每条有重要性 1–5、风险方向、可选的关联破裂信号。
- `notes/YYYY-MM-DD.md`：分析师周报，每周一写，出现重要性 5 的新闻时加写。
- `bubblemon-news-check`：校验新闻文件格式，提交前必须通过。
- 看板显示最新周报、近 7 天要闻和各主题 8 周新闻热度（重要性 ≥ 3 的条数和风险净方向）。新闻不进入泡沫温度的计算。
## 已知局限

- **水平值指标会贴着 100**：capex 这类持续增长的序列，分位数天然接近 100，信息量低于增速类指标。下一步建议加同比增速版本。
- **历史最早只到 2002 年**：SPY/RSP、TIPS 实际利率等序列起点较晚，所以无法回测 1999–2000 互联网泡沫。需要的话可补纳指、电信 capex 等长历史代理。
- **FRED 的 ICE BofA 高收益利差只给近 3 年**，所以另加了 Moody's Baa 利差（`BAA10Y`）作长历史替代。
- **Google Trends 是相对值**，且会限流；失败只记录在 `fetch_log`，不会中断其他指标。
- **GPU 租赁价、融资余额（FINRA）、循环融资关系**还没有接入，GPU 价格先走手工 CSV；对应的破裂信号会显示“无数据”。
- 破裂信号的阈值是经验设定，没有用历史回测校准。
- 指标方向（`direction`）和维度权重是主观设定，没有做过校准。

## 上线（GitHub Pages）

1. 把项目推到 GitHub 仓库，默认分支叫 `main`。
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**。
3. （可选）Settings → Secrets and variables → Actions，新建 secret `SEC_USER_AGENT`，值如 `你的名字 you@example.com`。不设置会用默认值。不要用 GitHub 的 `noreply` 邮箱，SEC 会返回 403。
4. Actions 页手动运行一次 `publish-dashboard`，之后每个工作日自动更新。网址是 `https://<用户名>.github.io/<仓库名>/`。

注意：Pages 在免费账号下要求仓库公开；私有仓库需要付费计划。看板是纯静态页面，没有后端。
