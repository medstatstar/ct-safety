# 临床试验安全信号专家（ct-safety）

[🇨🇳 中文](#) ｜ [🇺🇸 English](./README.md)

<div align="center">
  <img src="assets/icon.svg" width="240" height="240" alt="ct-safety 图标"/>
</div>

> **不安装也能用：** 如果你不想安装，只想快速使用本技能的基础功能，也可直接访问ct系列技能的总入口网页 **https://ct.medstatstar.com** 使用。

> 一个开箱即安全的药物警戒技能：对 **FDA FAERS** 公开不良事件数据筛查药物-事件安全信号（PRR / ROR / IC / EBGM，含 95% 置信区间），并可选叠加**器械不良事件（MAUDE）**、**中国官方药物警戒通报佐证**、**FDA 标签三角验证**与 **Naranjo 因果归因**。仅读取公开数据——**零保密输入（A 档，`network=public-retrieval`）**。所有检索采用**薄本地端**架构：本地仅做计算，所有出站检索统一经端点 `ct-search.coze.site` 外发。

## 适用人群

`ct-*` 临床试验技能家族面向三类人群：

- **各制药企业的临床试验从业者** —— 申办方、CRO，以及医学 / 统计 / 注册等角色；
- **在医疗机构中设计、管理临床试验项目，或参与临床试验研究实务的医护人员**；
- **希望系统学习临床试验知识的医学专业学生**。

## 耗时与检索量提示

> ⚠️ **耗时与下载量上限**。所有检索经统一端点 `ct-search.coze.site` 外发。耗时取决于处理 + 网络。以下为 **2026-10-08 实测**（上海 / 约 200 Mbps）：
>
> | 负载 | 命令形态 | 实测 wall-clock | 产出 |
> |---|---|---|---|
> | **概览**（count-facet，默认路径） | `ct_safety.py --drug candesartan --run`（不给 `--event`） | **约 10–30 秒** | 匹配报告数，top-10 反应 |
> | **信号检测** | `ct_safety.py --drug candesartan --event NAUSEA --run` | **约 15–45 秒** | 2×2 表 + PRR/ROR/IC/EBGM |
> | **Top-N 事件信号** | `ct_safety.py --drug candesartan --top-events-signal 6 --run` | **约 30–90 秒** | 多事件不成比例分析 |
> | **叠加中国 PV 佐证** | `ct_safety.py --drug osimertinib --event PNEUMONITIS --with-cn-pv --drug-cn 奥希替尼 --event-cn 肺炎 --run` | **约 20–60 秒** | FAERS 信号 + 中国通报 |
> | **多源 + 评分** | `ct_safety.py --drug osimertinib --event PNEUMONITIS --with-fda-label --with-cn-pv --run` | **约 30–90 秒** | 安全信号评分 0–100、T1–T4 |
> | **器械（MAUDE）** | `ct_safety.py --device --drug "pacemaker" --event "malfunction" --run` | **约 15–45 秒** | 器械 2×2 + 四项指标 |
>
> **单次运行上限**：
> - `fetch_reports.py --max <n>` → 硬上限 **10,000**（`HARD_CAP`）；超出自动 clamp 并打印 `[WARN]`。
> - `ct_safety.py --case-level <n>` → **单页**抓取，硬上限 **100**；且**必须配合 `--event`** 使用。批量下载请改用 `fetch_reports.py --max`。
> - openFDA 配额（仅本机直连的 `query_total` / `fetch_case_reports`）：匿名 240 次/分、1,000 次/天按 IP；免费 key 240 次/分、120,000 次/天按 key。
>
> **如何避免长时间等待**：先用概览摸清基数；用 `--date-from` / `--date-to` 缩小时间窗；`--max` 由小到大逐步加（500 → 2000 → …）。

## 如何在对话里使用

直接用自然语言告诉助手你想做什么（示例见下）。真实计算遵循「安全」一节的两段式安全流程。

### 示例 1 · 某药的高发不良事件

**你这样说：**
> 帮我校查一下 candesartan 在 FAERS 里报告最多的不良事件。

**如何触发：**
> 概览会自动执行。说「跳过预览，直接跑」技能即抓取 FAERS 各分面并打印汇总。

### 示例 2 · 某个具体药物-事件信号

**你这样说：**
> candesartan 会不会增加血管性水肿风险？

**如何触发：**
> 概览先自动跑出，然后停下等你确认。回复「确认，跑详情」或「跳过预览，直接跑」即执行信号检测（2×2 → PRR/ROR/IC/EBGM）。

### 示例 3 · 多事件安全信号筛查

**你这样说：**
> 筛查奥希替尼在 FAERS 里报告最多的 6 个不良事件有没有安全信号。

**如何触发：**
> 确认详情步骤 —— 对每个 Top 事件跑 disproportionality、做 BH-FDR 校正、做多方法交叉判定。

### 示例 4 · 用中国官方药物警戒通报佐证

**你这样说：**
> 有没有奥希替尼肺炎的中国官方安全通报？

**如何触发：**
> 确认详情步骤并传中文词（`--drug-cn 奥希替尼 --event-cn 肺炎`）以提高召回。返回定性佐证。

### 示例 5 · 多源三角验证 + 证据分级

**你这样说：**
> 给我一个奥希替尼肺炎的安全信号评分，带证据分级——把 FDA 标签和中国 PV 也拉上。

**如何触发：**
> 确认详情步骤 —— 查询 FAERS + FDA Label + CN-PV，合成安全信号评分（0–100）与 T1–T4 证据分级。

### 示例 6 · 多药对比

**你这样说：**
> 对比一下 osimertinib、gefitinib、erlotinib 在肺炎上的安全性。

**如何触发：**
> 选一个菜单项（aROR / FDR / 时间趋势 / 完整三角验证）。选定后走两段式流程。

### 示例 7 · 器械不良事件（MAUDE）

**你这样说：**
> 起搏器故障报告在 MAUDE 里有没有安全信号？

**如何触发：**
> 确认详情步骤 —— 走同样的 2×2 / 四项指标流水线，数据源切换为 `device/event.json`。

### 示例 8 · 个案报告（含去重）

**你这样说：**
> 拉一下奥希替尼肺炎的 FAERS 个案报告，我要逐条审阅。

**如何触发：**
> 确认详情步骤加 `--case-level 50` —— 每页最多拉 100 条，按 `safetyreportid` 折叠去重（L1）+ 按反应 PT 集合 Jaccard 标记疑似重复（L2）。

### 示例 9 · Naranjo 因果归因

**你这样说：**
> 给这个信号加一个 Naranjo 因果归因评估。

**如何触发：**
> 确认详情步骤加 `--with-causality` —— 独立附录 Naranjo 7 准则判定，不与 PRR/ROR 混算。

### 示例 10 · PSUR 自动生成

**你这样说：**
> 根据刚才检出的信号生成一份 PSUR。

**如何触发：**
> 确认详情步骤加 `--psur --psur-period 2026H1` —— 自动生成 `psur.md`。

### 示例 11 · 问题上报

**你这样说：**
> 上报问题 / report a bug

**触发后：**
> 助手生成一份 11 键白名单脱敏报告 → 展示给你审阅 → 你确认后才发送至 `https://ct-bugreport.coze.site/run`。未经你明确说「发送」绝不传输任何内容。

## 你能做些什么 —— 场景索引

| 能力 | 方法 | 试试这样说 |
|---|---|---|
| 药物不良事件画像 | FAERS 计数（高发反应、严重性、人口学） | 「查 candesartan 在 FAERS 里报告最多的反应」 |
| 药物-事件信号检测 | PRR / ROR / IC / EBGM + 95% CI + 信号判定 | 「candesartan 会不会升高血管性水肿风险？」 |
| 多方法交叉判定 | ROR 下限 CI > 1 · PRR ≥ 2 且 χ² ≥ 4 · IC 下限 CI > 0 · EBGM EB05 ≥ 2 | 「这个信号在多个方法上稳健吗？」 |
| 多事件安全筛查 | `--top-events-signal N` 对焦点药 Top 事件逐个跑信号 | 「筛查奥希替尼 Top 6 不良事件的信号」 |
| 中国官方 PV 佐证 | cdr-adr.org.cn 公开通报（仅定性） | 「有任何中国官方的奥希替尼肺炎通报吗？」 |
| 多事件 FDR 控制 | Benjamini-Hochberg q 值（Top-N 事件） | 「对所有高发事件做假发现率控制筛查」 |
| PT→SOC 器官归类 | MedDRA PT → 系统器官分类映射 | 「把这些信号按器官系统分组」 |
| 时间趋势异常 | `--trend` CUSUM / rolling-Z / changepoint | 「奥希替尼肺炎报告最近有突增吗？」 |
| 多药校正 ROR | aROR 经 `--compare-drugs`（焦点 vs 合并参照） | 「对比 osimertinib 与 gefitinib 的肺炎风险」 |
| 竞品基准 | `--benchmark-drug`（同事件横向比较） | 「让 osimertinib 与 gefitinib、erlotinib 在肺炎上横向对比」 |
| 多源三角验证 + 评分 | `--with-fda-label` → 安全信号评分 0–100、T1–T4 | 「给我一个带证据分级的综合信号评分」 |
| 器械不良事件 | `--device` MAUDE `device/event.json` | 「起搏器故障有没有安全信号？」 |
| 个案报告 | `--case-level N` + L1/L2 去重 | 「拉个案报告审阅」 |
| Naranjo 因果归因 | `--with-causality` 独立 7 准则判定 | 「给这个信号加 Naranjo 归因」 |
| 信号验证 | `--verify-signal` 时序 / 剂量-反应 / 去卷积 | 「验证这个信号的稳健性」 |
| 信号优先级排序 | `--prioritize` label-gap + 时间趋势维度 | 「按风险给信号排优先级」 |
| PSUR 自动生成 | `--psur` 根据检出信号自动生成 | 「根据这些信号生成 PSUR」 |
| 非 ASCII 药名 | `--drug 阿司匹林` 自动解析为 INN | 「查一下阿司匹林的不良反应」 |
| 已发表安全性文献佐证 | 关联调用 **`ct-literature --safety`** | 「拉一下奥希替尼肺炎的已发表综述」 |
| MedDRA verbatim 编码 | `--code-verbatim` 内置字典编码 | 「把这个 verbatim 术语编码成 PT」 |

### 用已发表文献佐证（关联调用 `ct-literature --safety`）

当某个 FAERS 信号需要**定性**的已发表证据支撑时，调用 **`ct-literature --safety`**。它会把 CSM 定性子集作为独立的**「安全性相关」**页返回。

> **边界。** `ct-literature --safety` 仅作**已发表文献语境**，绝不可进入 FAERS 的 2×2 不成比例分析表。用它来佐证、解释信号，而非作为定量来源。

## 常见问题 FAQ

**只给一个药名、不给事件能算吗？**
能。只给 `--drug` 不再报错——自动降级为高频不良事件报告。要算具体信号，请补一个事件（MedDRA 首选术语）。

**PRR 和 ROR 有什么区别？**
二者都基于药物-事件 2×2 表的 disproportionality。ROR 以下限 95% CI > 1 判信号；PRR 在 PRR ≥ 2 **且** χ² ≥ 4 时判信号；IC 下限 CI > 0 判信号；EBGM 的 EB05 ≥ 2 判信号。四种方法同时报告，并对多事件做 BH-FDR 校正。

**怎么才能真跑出信号表？**
默认只给概览并停下。确认详情步骤，或说「跳过预览，直接跑」——即执行检索与 disproportionality 分析，返回结果（HTML / XLSX / JSON / Markdown）。

**中文环境输出是中文吗？**
是。技能跟随你的输入语言，报告均在 `zh-*` 区域下切中文。

**openFDA key 怎么配？**
默认**无需 key** 即可运行（主路径经统一端点）。仅本机直连场景走 openFDA。高吞吐需求注册免费 key：https://open.fda.gov/api/register/。用环境变量 `OPENFDA_KEY`、技能根目录 `.env` 或 `--api-key` 之一提供。key 仅本地存储，且仅经 HTTPS 发往官方 openFDA API。

**Q: 发现结果有误怎么办？**
A: 直接说「上报问题」/「report a bug」。技能在检测到疑似缺陷时也会主动询问（每会话最多 1 次）。流程：(1) 生成 11 键白名单脱敏报告 → (2) 展示给你审阅 → (3) 你确认后发送 → (4) 收到回执。

**Q: 必须安装技能才能用吗？**
A: 不必须——基础功能可直接访问 ct 系列总入口网页 **https://ct.medstatstar.com** 免安装使用；完整能力请安装并调用 `ct-safety` 技能。

## 安全（安全预览）

**两段式流程，开箱即安全。** 第一步（概览）自动执行。第二步（详细检索 / 信号检测）**仅在你显式确认后**才执行——或当你说「跳过预览，直接跑」时。

**出站披露。** 本地仅做计算；所有出站检索统一经端点 `ct-search.coze.site` 外发。技能仅读取：
- **FDA FAERS**（必需，量化）—— 经 `faers` 节点；
- **MAUDE**（使用 `--device` 时可选器械事件）—— 经 `maude` 节点；
- **FDA Label**（使用 `--with-fda-label` 时的可选第三源）—— 经 `fda_label` 节点；
- **国家不良反应监测中心**（使用 `--with-cn-pv` 时的可选源，仅定性）—— 经 `nmpa_pv` 节点。

**零保密数据输入**（A 档）。错误报告只发 11 键白名单至 `https://ct-bugreport.coze.site/run`。信号检测仅供筛查，非因果结论。

## 进阶参考

### 数据源

| 源 | 访问方式 | 状态 |
|---|---|---|
| FDA FAERS（openFDA `drug/event.json`） | 薄本地端 → 统一端点 `ct-search.coze.site`（`faers` 节点）；`query_total` / `fetch_case_reports` 仍本机直连 | 必需（A 档，量化） |
| MAUDE（openFDA `device/event.json`） | 薄本地端 → 统一端点（`maude` 节点）；默认维度 `patient.device.brand_name` | 可选 `--device`（量化） |
| FDA Label（openFDA `drug/label.json`） | 薄本地端 → 统一端点（`fda_label` 节点）；`check_event` 本地判定 | 可选 `--with-fda-label` |
| 国家不良反应监测中心（cdr-adr.org.cn） | 薄本地端 → 统一端点（`nmpa_pv` 节点）；本地保留关键词扩展 + 证据分级 + 缓存 | 可选 `--with-cn-pv`（仅定性） |

### 环境要求

- Python 3.10+（推荐 Anaconda `C:\Tools\anaconda3\python.exe`）。
- 必需：`requests`。可选：`matplotlib`（PNG 图）。网络：只读 FAERS 公开 API。

### CLI 工作流

```bash
# 概览（自动执行，总数+Top-N，然后停下等你确认）
python scripts/ct_safety.py --drug "candesartan" --top 10 --date-from 20200101 --date-to 20261231

# 汇总 Excel（默认 present 流程；count 分面、秒级）
python scripts/fetch_reports.py --drug "candesartan" --date-from 20200101 --date-to 20261231 --out-xlsx faers_summary.xlsx

# 详情下载（仅当你明确要个案时；硬上限 10000）
python scripts/fetch_reports.py --drug "candesartan" --max 10000 --date-from 20200101 --date-to 20261231 \
    --run --out faers_reports_raw.json --out-csv faers_reports.csv --out-xlsx faers_reports.xlsx

# 药物-事件信号检测（2x2 -> PRR/ROR/IC/EBGM）；确认后才跑
python scripts/ct_safety.py --drug "candesartan" --event "ANGIOEDEMA" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 多事件安全信号筛查
python scripts/ct_safety.py --drug "osimertinib" --top-events-signal 6 \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 中国 PV 定性佐证
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" --run --out-dir ./out

# 多源三角验证 + 安全信号评分 0-100 + T1-T4
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-fda-label --with-cn-pv --drug-cn "奥希替尼" --event-cn "肺炎" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 器械不良事件（MAUDE）
python scripts/ct_safety.py --device --drug "pacemaker" --event "malfunction" \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 个案报告（含去重）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --case-level 50 --run --out-dir ./out

# Naranjo 因果归因（定性补充，独立于 disproportionality）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --with-causality --run --out-dir ./out

# 时间趋势异常
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --trend --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 多药校正 ROR（首药=焦点，其余=参照池）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --compare-drugs osimertinib gefitinib erlotinib \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 竞品基准（同事件横向对比）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --benchmark-drug gefitinib erlotinib \
    --date-from 20200101 --date-to 20261231 --run --out-dir ./out

# 信号验证（时序/剂量-反应/去卷积）
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --verify-signal --run --out-dir ./out

# PSUR 自动生成
python scripts/ct_safety.py --drug "osimertinib" --event "PNEUMONITIS" \
    --psur --psur-period 2026H1 --run --out-dir ./out

# 流水线自检（阳性/阴性对照）
python scripts/ct_safety.py --validate-controls --out-dir ./out

# 独立 CN-PV 检索
python scripts/fetch_cn_pv.py --drug "奥希替尼" --event-cn "肝损伤" --out cn_pv.json
```

### FAERS 字段边界

- **可检索 / 可 count**：`patient.drug.medicinalproduct`、`patient.reaction.reactionmeddrapt`（Top-N 用 `.exact`）、`receivedate`、`serious*` 布尔、`patient.patientsex`（1=男 / 2=女 / 0=未知）。
- **API 不可分面（仅存于个案体内）**：`patient.patientage`、`primarysource.reportertype`、`primarysourcecountry`。需下载个案（`--run`）才能在本地统计。
- 多词 MedDRA PT：部分三词短语（`RENAL FAILURE ACUTE`）持续 404——改用标准 PT `ACUTE KIDNEY INJURY`；两词 PT（如 `HEPATIC FAILURE`）通常可用。`total()` 自动「404 → `.exact`」降级。

### 错误处理

| 错误 | 原因 | 修复 |
|---|---|---|
| `URLError` / timeout | 无网络 / 代理 | 确认网络可达；配置代理 |
| 端点错误 | 配额耗尽 / token 无效 / 端点未 allow-list | 检查 Coze 部署状态及 `config.json` `auto_approve_endpoints` |
| HTTP 429 / 限流 | 超 openFDA 限额（仅本机直连） | 加 `--api-key`；或降频 |
| 只给 `--drug` 未给 `--event` | 意图是看高发反应 | 自动降级为 Top-N 报告；加 `--event` 算信号 |
| CN-PV 0 命中 | 关键词过窄 | 传 `--drug-cn` + `--event-cn`；调大 `--cn-max` |
| `--max > 10000` | 突破上限 | 自动 clamp 到 `HARD_CAP=10000`；注意选择偏倚 |

### 比较研究设计模式

当用户要求*对比*，切换到比较轨道：(1) 数据准备 → (2) 选研究风格 + 工作负载 → (3) 选指标、对照逻辑、稳健性路线 → (4) 给每个结果打证据分级。硬规则：绝不在未准备原始计数上跑 disproportionality；始终先展示四种配置再推荐一种；Tier-4 主张无外部数据禁止。

### 回归测试

```bash
python tests/run_tests.py            # 离线（mock 网络）
python tests/run_tests.py --live     # 额外跑 tests/test_live.py（真实 openFDA）
CT_SAFETY_LIVE=1 python tests/run_tests.py
```

**版本**：v0.10.0 | **许可证**：MIT | **作者**：medstatstar, phoe-zip

如有功能改进建议、Bug 报告或其他反馈，欢迎直接联系作者：medstatstar@gmail.com（张文彤 / Wintone Zhang）。

---

## 保密声明

> CT 全系列技能由 20+ 个技能构成，按「输入是否涉密」分为 **A、B 两档**（network / egress / publish 为独立正交属性，详见 ct-base §11），完整覆盖新药临床试验全流程。
>
> - **A 档（输入非涉密）**：输入为普通数据，可完全本地运行或对外公开检索；不涉及任何保密信息。A 档技能均在 GitHub 公开发布。
> - **B 档（输入涉密）**：输入含药企需严格保密的临床试验数据 / 方案 / CRF；B 档既能本地处理（`egress=none`，数据不出域）也能对外公开检索（仅公开查询词出域）；或需审批出站（`egress=approval-req`）。但均不对外公开发布；涉密输入绝不随包 / 出站。
>
> 📧 联系方式：medstatstar@gmail.com，张文彤（Wintone Zhang）
