# AI 泡沫监测：分析师工作手册

这份手册写给定时任务里运行的 AI 分析师。每次运行都完整按这里执行。读者是用这个看板做投资参考的人：要信息密度、要判断，不要套话。

## 每次运行的步骤

1. 准备环境（每次都可能是全新机器）：
   ```bash
   git clone https://github.com/zhuyihe79-source/ai-bubble-monitor.git || (cd ai-bubble-monitor && git pull --ff-only)
   cd ai-bubble-monitor
   python3 -m venv .venv && .venv/bin/pip install -q -e .
   ```
2. 先看数据面，作为判断新闻的背景：
   ```bash
   .venv/bin/bubblemon-fetch
   .venv/bin/python -c "
   import pandas as pd
   from bubblemon import db, scoring, commentary
   from bubblemon.registry import load_config
   cfg = load_config(); con = db.connect()
   s = {i.id: db.load_series(con, i.id) for i in cfg.indicators}
   n = commentary.weekly_note(s, cfg, scoring.compute(s, cfg), pd.Timestamp.today())
   print(n.headline); [print(t, items) for t, items in n.sections]"
   ```
3. 确定时间窗口：从 `news/` 里最新文件的日期到现在（第一次运行取最近 7 天）。日期一律用北京时间。
4. 按下面四个主题收集新闻，逐条核实，打分，写入 `news/YYYY-MM-DD.json`（今天的北京日期）。同一个链接如果已经出现在任何旧文件里，不要重复收录。
5. 如果今天是周一（北京时间），或者本次出现了 importance = 5 的新闻，写分析师周报 `notes/YYYY-MM-DD.md`。
6. 校验并提交：
   ```bash
   .venv/bin/bubblemon-news-check
   git add news notes && git commit -m "news: YYYY-MM-DD" && git push
   ```
   校验不通过就修到通过为止。推送失败就停下，在最终回复里说明原因，不要改用其他仓库或分支。
7. 最终回复用中文，三到五行：收录了几条、最重要的一条是什么、有没有写周报。

## 四个主题

| topic | 关注什么 | 常用来源 |
|---|---|---|
| `memory` 存储与供应链 | HBM/DRAM/NAND 供需、合约价和现货价、海力士/三星/美光的扩产与指引、台积电 CoWoS 等先进封装产能、HBM 设备瓶颈 | TrendForce、DigiTimes、Nikkei Asia、Reuters、公司财报和新闻稿、美光 8-K |
| `nvidia` 英伟达与芯片竞争 | 英伟达新闻稿和 SEC 文件、业绩和指引、产品节奏（Blackwell Ultra、Rubin）、出口管制、AMD、谷歌 TPU、亚马逊 Trainium、博通定制芯片、内部人减持 | nvidianews.nvidia.com、SEC EDGAR、Reuters、Bloomberg、The Information |
| `financing` 融资与循环交易 | OpenAI/Anthropic/xAI 等的融资和估值、英伟达对客户的投资、甲骨文/CoreWeave/Meta 等发债、数据中心 SPV 和私募信贷、信用利差和评级变化 | Reuters、Bloomberg、FT、WSJ、SEC 8-K、评级机构公告 |
| `demand` 需求与电力 | 云厂商 capex 指引、AI 收入和付费用户数据、企业采用率、数据中心电力和并网、项目推迟或取消 | 财报电话会、公司新闻稿、Reuters、行业协会和电网公告 |

### 免费来源的具体用法

- 网络搜索：每个主题至少搜 3 个查询，带上时间限定，例如 `HBM contract price November 2026`、`Nvidia export license news this week`、`OpenAI funding round valuation`、`data center power delay`。
- Google News RSS：`https://news.google.com/rss/search?q=<查询>+when:3d&hl=en-US&gl=US&ceid=US:en`
- 英伟达新闻稿 RSS：`https://nvidianews.nvidia.com/releases.xml`
- SEC 申报（请求头要带 `User-Agent: ai-bubble-monitor research contact@example.com`）：
  `https://data.sec.gov/submissions/CIK<10 位 CIK>.json`，看 `filings.recent` 里新出现的 8-K、10-Q、Form 4、144。
  常用 CIK：NVDA 0001045810、MSFT 0000789019、GOOGL 0001652044、AMZN 0001018724、META 0001326801、ORCL 0001341439、MU 0000723125、AMD 0000002488、AVGO 0001730168、CRWV 0001769628。

## 收录标准

- 只收会改变判断的信息：新的数字、新的交易、新的政策、新的指引。观点文章、重复报道、营销稿、SEO 聚合页不收。
- 优先一手来源（公司公告、SEC 文件）和主流财经媒体。二手来源的关键数字要能在一手来源或第二家主流媒体找到印证；找不到就把 importance 降一级，并在 summary 里写“据某某报道”。
- 每条都要打开链接确认标题和日期属实。绝对不要编造链接、数字或引语。
- 每天一般 5–15 条。宁缺毋滥。

## 打分

`importance`（1–5）：

- 5：可能改变整个周期判断。例如：云厂商大幅下调 capex 指引；英伟达业绩或指引明显低于预期；大型 AI 公司融资失败或债务违约；重大出口管制；HBM 供应严重中断。
- 4：直接影响某个破裂信号或某家核心公司。例如：100 亿美元以上的融资、发债或合同；存储合约价大幅变动；主要客户自研芯片量产；数据中心项目大规模推迟。
- 3：值得记录的趋势证据。
- 2：背景信息，帮助理解但不改变判断。
- 1：不收录。

`direction`：对“AI 泡沫破裂或大幅回调的风险”的影响。

- `risk_up`：需求出现裂缝、融资压力加大（杠杆上升、循环交易、表外融资）、供给过剩、利润率受压、监管收紧、内部人大额减持。
- `risk_down`：真实收入和付费需求得到验证、融资来自自有现金流、供给约束缓解了过度投资。
- `neutral`：方向不明确，或利多利空大致抵消。

有些新闻两面都有，比如 HBM 短缺：短期说明需求强（降低需求风险），但也限制英伟达出货、抬高成本（增加供给风险）。这种情况按对“未来 6–12 个月出现大幅回调”的净影响判断，并在 `implication` 里把两面都写出来。

`signal`（可选）：如果新闻直接关系到某个破裂信号，填它在 `config/indicators.yaml` 里的触发器 id，例如 `capex_yoy`、`debt_yoy`、`nvda_rev_yoy`、`gpu_price_3m`。

## 新闻文件格式

```json
{
  "date": "2026-11-16",
  "generated_at": "2026-11-16T08:00:00+08:00",
  "window": "2026-11-09 至 2026-11-16",
  "items": [
    {
      "published": "2026-11-14",
      "title": "原标题（保持原文语言）",
      "source": "Reuters",
      "url": "https://...",
      "topic": "memory",
      "importance": 4,
      "direction": "risk_up",
      "signal": "capex_qoq",
      "summary": "用自己的话写的中文摘要，一到两句，包含关键数字，不超过 80 字。",
      "implication": "对泡沫判断意味着什么，一句话。"
    }
  ]
}
```

不要转载原文段落，摘要必须用自己的话写。

## 周报格式（notes/YYYY-MM-DD.md）

```markdown
# 一句话结论（例如：需求仍强，但融资端在加速恶化）

## 本周最重要的三件事
1. ……（附链接）

## 数据面
引用看板上的破裂信号和泡沫温度，说明本周变化。

## 四个主题
### 存储与供应链
### 英伟达与芯片竞争
### 融资与循环交易
### 需求与电力

## 和上周相比，判断有什么变化

## 接下来要盯的事件
带日期，例如财报日、政策截止日、重要会议。
```

周报控制在 600–1000 字。每个判断都要有数据或新闻支撑，不确定的地方直接说不确定。
