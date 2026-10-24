# 数据口径与扩展

官方接口核对日期：2026-10-23。接口权限以实际账号响应为准。

| 接口 | 数据 | 官方说明 |
|---|---|---|
| stock_basic | 证券身份、行业、上市日期 | https://tushare.pro/document/2?doc_id=25 |
| stock_company | 公司简介、主营业务 | https://tushare.pro/document/2?doc_id=112 |
| income | 利润表，金额元 | https://tushare.pro/document/2?doc_id=33 |
| balancesheet | 资产负债表，金额元 | https://tushare.pro/document/2?doc_id=36 |
| cashflow | 现金流量表，金额元 | https://tushare.pro/document/2?doc_id=44 |
| daily_basic | 市值为万元，价格为元，PE/PB 为倍 | https://tushare.pro/document/2?doc_id=32 |
| fina_mainbz | 主营构成，收入/成本为元 | https://tushare.pro/document/2?doc_id=81 |
| top10_holders | 股东，hold_ratio 已经是百分数 | https://tushare.pro/document/2?doc_id=61 |

HTTP JSON 协议：https://tushare.pro/document/1?doc_id=130 。脚本仅连接 `https://api.tushare.pro`，保留 TLS 证书校验，禁止重定向到其他主机。若官方 HTTPS 在当前网络不可用，报告连接错误，不擅自转向镜像或明文连接。

## 凭证

优先级：显式 `--token-file`（或环境变量 `TUSHARE_TOKEN_FILE`）→ 进程环境 → Windows 用户/系统环境 → `references/local-config.json` 引用的凭证文件 → `~/tk.csv`。支持 `TUSHARE_TOKEN`、`TUSHARE_API_TOKEN`、`TS_TOKEN`。指定凭证文件支持 JSON 对应键、dotenv 对应键、SDK CSV 的 token 列或纯 Token 文本。只报告来源名称和是否可用，绝不输出 Token。凭证只存在于进程内存和发给官方 API 的请求体，不进入数据附件。

`local-config.json` 是本机可选配置，内容仅为 `{"token_file":"已有凭证文件的绝对路径"}`；不复制 Token。迁移机器时删除或修改这个路径。分发通用 Skill 时可排除此本机配置。

## 标准数据

`profile.json`：`schema_version`, `code`, `as_of`, `retrieved_at`, `company`, `market`, `financials`, `segments`, `holders`, `sources`, `notes`。

- `financials`：3 个完整年度 + 最新非年度累计期；同一期三张表独立合并，缺项留 null。
- 营收选 `revenue`，为空时用 `total_revenue`（逐期保留 `revenue_field`）。归母利润为 `n_income_attr_p`；权益为 `total_hldr_eqy_exc_min_int`。`n_income/revenue` 为合并净利率，`n_income_attr_p/revenue` 为归母净利率，页面默认明确使用后者。
- 不用财务指标接口的净利率代替自行计算口径。财务为元，展示除以 1e8；市值为万元，展示除以 1e4。
- 不自动年化季度，不从年报直接减出单季；同月日同期且前期基数为正时才计算同比。
- 默认仅提取 `report_type=1`。基于公告日的去重仍不等于历史数据库版本重建；历史任务需回看原公告。
- `segments` 仅按产品 P 取最近已知完整年度报告期，最多 100 行；`len>=100` 标记可能截断。不把行业/地区/产品合并求占比。检查重复名称、合计行、负值、混合货币。满足检查也只表示基本结构可用，仍应对照年报核实分类互斥。
- Tushare 产品分类可能包含同义或嵌套项，脚本无法语义判重；不能仅凭接口查询成功就认定占比已经核实。人工核对后在 editorial 中写 `segments_verified: true` 才绘图。
- 股东按最近一期显示前五位，并标报告期；数量不足保留实际数量。
- `as_of` 控制财务公告日期及行情日期。静态公司信息和无公告日的主营数据不是历史快照，页面提示这一点。

## 业务文字补充

`editorial.json` 可包含以下字段（全部可选；未使用的字段不创建）：

```json
{
  "overview": "根据年报整理的简短主营介绍。",
  "positioning": "有公告依据的产业链位置或业务定位。",
  "events": ["近期经营事项，限两条短句。"],
  "sources": [{"title": "公司年报及具体页码", "url": "https://example.com/annual-report.pdf"}],
  "segments_verified": true
}
```

示例 URL 只是 schema 示意，实际产物必须替换为真实来源。任何补充文字存在时 `sources` 不得为空；若来自用户给定本地文件可使用绝对路径作为 url，渲染器仅将 http(s) 来源变为超链接。

未经核实不要填写行业地位排名、市场份额、实控人、预测值或交易建议。可用年报/交易所公告补全财务，但须在标准 JSON、来源表和对应字段记录不同来源；不要静默覆盖接口值。

行业名单页可沿用以上单家公司 schema 逐一取数，交由 agent 用同口径数据另排一页。这个模式不复用单家公司渲染脚本硬塞多家公司。
