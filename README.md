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
2. 季度财报数据按 `publication_lag_days`（45 天）后移，避免历史分数用到当时还没公布的数据。
3. 取过去最多 15 年（至少 3 年）的滚动分位；`direction: low` 的指标取 `1 - 分位`。
4. 维度内等权平均，维度间按 `weight` 加权，乘以 100。
5. 至少 `min_dimensions` 个维度有数据才发布总分。

## 已知局限

- **水平值指标会贴着 100**：capex 这类持续增长的序列，分位数天然接近 100，信息量低于增速类指标。下一步建议加同比增速版本。
- **历史最早只到 2002 年**：SPY/RSP、TIPS 实际利率等序列起点较晚，所以无法回测 1999–2000 互联网泡沫。需要的话可补纳指、电信 capex 等长历史代理。
- **FRED 的 ICE BofA 高收益利差只给近 3 年**，所以另加了 Moody's Baa 利差（`BAA10Y`）作长历史替代。
- **Google Trends 是相对值**，且会限流；失败只记录在 `fetch_log`，不会中断其他指标。
- **GPU 租赁价、融资余额（FINRA）、循环融资关系**还没有接入，GPU 价格先走手工 CSV。
- 指标方向（`direction`）和维度权重是主观设定，没有做过校准。

## 上线（GitHub Pages）

1. 把项目推到 GitHub 仓库，默认分支叫 `main`。
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**。
3. （可选）Settings → Secrets and variables → Actions，新建 secret `SEC_USER_AGENT`，值如 `你的名字 you@example.com`。不设置会用默认值。不要用 GitHub 的 `noreply` 邮箱，SEC 会返回 403。
4. Actions 页手动运行一次 `publish-dashboard`，之后每个工作日自动更新。网址是 `https://<用户名>.github.io/<仓库名>/`。

注意：Pages 在免费账号下要求仓库公开；私有仓库需要付费计划。看板是纯静态页面，没有后端。
