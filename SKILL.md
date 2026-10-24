---
name: company-profile
description: 输入A股股票全称、简称或代码，生成包含公司业务、营收结构、财务摘要、估值与股东的中文一页概览。支持Tushare和无Token的AKShare路径，交付HTML与高清图片，适合pitch book、买方介绍和公司速览。
---

# 公司一页概览

生成一家公司一页的中文基本面概览。以 `examples/wuliangye/company-profile-enhanced.html` 和配套PNG作为成品视觉参考：企业品牌配色、官方Logo、产品/实景图、营收结构、可核验的销售区域图及财务/股东信息，保持专业平面排版。各公司使用各自的品牌与素材，不套用五粮液的红金配色。

脚本提供基础数据和基础模板，Agent需按 [references/enhanced-example.md](references/enhanced-example.md) 进一步核对素材、组织图文并完成增强版。不要把基础模板当作已达到增强案例的最终成品；素材或地域数据不可用时说明限制并省略该模块，不伪造。

## 用户输入与证券身份

用户输入股票全称、简称或代码即可，不要求先知道代码。默认支持沪深京A股。使用脚本中的实时证券目录识别，不凭名称猜代码。

```text
python <SKILL_DIR>/scripts/run_profile.py "五粮液" --out <OUTPUT_DIR>
python <SKILL_DIR>/scripts/run_profile.py "宜宾五粮液股份有限公司" --out <OUTPUT_DIR>
python <SKILL_DIR>/scripts/run_profile.py 000858 --out <OUTPUT_DIR>
```

代码也支持 `000858.SZ`、`sz000858`、`000858sz`。名称先精确匹配，唯一包含匹配可用于公司全称；多个候选则向用户列出名称和代码选择，不擅自选第一项。无匹配或市场后缀错误时提示修正。港股、美股不属于当前采集脚本范围。

只需验证身份时可加 `--resolve-only`，不会下载财报。证券目录缓存七天，保存在项目工作目录的 `.company-profile-cache`，可用 `--cache-dir` 指定其他目录。

## 数据源选择与凭证

- 有可用Tushare Token时，优先采用Tushare；无Token直接使用AKShare，不要求用户购买权限。
- 用户有Token但尚未配置时，指导本机设置 `TUSHARE_TOKEN`，或交互终端运行 `--prompt-token` 隐藏输入。不要要求把Token粘贴进聊天、命令行字面量或代码。`--token-file`可引用用户已有凭证文件。
- `--source akshare`明确使用无Token路径；`--source tushare`明确使用Tushare。Token认证失败应报告并让用户修正或选择AKShare，不静默掩盖认证问题。
- AKShare需要 `python -m pip install -r <SKILL_DIR>/requirements.txt`。Tushare客户端使用Python标准库HTTPS，不要求额外SDK。
- 执行Python/Node路径以当前运行环境为准。Codex桌面可调用 `load_workspace_dependencies`，不要硬编码作者机器路径。

输出 `raw.json`、`profile.json`、`sources.csv` 与 `company-profile.html`。脚本对必要财务数据缺失报错；其他接口失败记录缺失，不使用0或示例数据冒充真实数据。不能承诺所有第三方接口在任意网络环境都可用。

## 内容核对

读取 [references/data-contract.md](references/data-contract.md) 与 [references/data-sources.md](references/data-sources.md)。

公司概况须区分上市公司与集团，主营描述优先核对年报或公司官网，不能把经营范围直接当作主营。接口底稿可由agent整理成短业务介绍。

财务默认三个完整年度加最新中期累计值，采用合并口径；单位人民币亿元。明确归母净利率的计算口径，最新估值与股东分别标注日期。重述与收入确认变化需要在页面提示。

主营构成只用同报告期、同货币、互斥分类，不能把总计、子项及产品/地区/行业混加。脚本初始标记未核验，核对年报后再设置 `segments_verified: true` 或 `segments.verified: true`。AKShare报表的供应商更新日期不是原公告日，当前版本只提供当前抓取快照，不假装支持历史时点回溯。

品牌色、官方Logo、产品/实景图片可按用户要求补充并保留来源。地图只能按真实披露粒度呈现；片区收入不能画成省级定量数据。默认保持一页可读，不加入交易建议或完整长篇研报。

如需补充业务短句、公告说明，参考 `examples/wuliangye/editorial.json`，并在 `sources` 中保留真实URL，再运行：

```text
python <SKILL_DIR>/scripts/render_profile.py --input <OUTPUT_DIR>/profile.json --out <OUTPUT_DIR>/company-profile.html --editorial <OUTPUT_DIR>/editorial.json
```

## 图片导出与验收

网页自包含、无需服务器。使用已有Playwright和Chrome/Edge导出，不下载浏览器：

```text
node <SKILL_DIR>/scripts/export_profile.cjs --html <OUTPUT_DIR>/company-profile.html --png <OUTPUT_DIR>/company-profile.png
```

包不可见时用 `NODE_PATH` 指向现有Node包目录；缺少Playwright时在本仓库 `npm install --ignore-scripts`。查看PNG，检查中文、数值、单位、来源、图表和容器边界。导出器检查溢出，但不替代人工视觉检查。

交付HTML、PNG和重要数据截止日及缺失。PDF按用户需要提供。生成Word时遵循用户指定字体，不能用本Skill默认风格覆盖项目要求。
