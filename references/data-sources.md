# 数据来源与适配说明

接口文档核对日期：2026-10-23。

## Tushare

标准HTTPS JSON协议：https://tushare.pro/document/1?doc_id=130

使用 stock_basic（含fullname）、stock_company、income、balancesheet、cashflow、daily_basic、fina_mainbz、top10_holders。三张报表使用合并累计口径，Token只在发给官方API的请求体中出现。

## AKShare

官方文档：https://akshare.akfamily.xyz/data/stock/stock.html

| 接口 | 作用 | 关键口径 |
|---|---|---|
| stock_info_a_code_name | 沪深京A股目录 | code/name，名称识别不硬编码五粮液 |
| stock_individual_info_em | 股票资料 | 证券身份、行业、市值元 |
| stock_individual_basic_info_xq | 公司简介 | main_operation_business为主营描述 |
| stock_zyjs_ths | 主营介绍补充 | 仅在简介无主营字段时使用 |
| stock_financial_report_sina | 三张财务报表 | 仅使用类型含“合并”的行；金额元 |
| stock_value_em | 日度估值 | 当日收盘价、PE(TTM)、市净率、总市值元 |
| stock_zygc_em | 主营构成 | 按产品分类，金额元，保留原始层级 |
| stock_gdfx_top_10_em | 股东 | 持股比例已是百分数 |

供应商列名可能变化，匹配不到的值保留缺失。源码将原AKShare结果保存在raw.json的provider_original中，便于检查映射。

AKShare市值元转入统一内部schema的万元时除以10000，再由渲染器转为亿元；Tushare日度市值原本就是万元。

AKShare新浪报表提供“更新日期”，该字段是供应商更新日期，不能视为原公告日。当前结果仅为抓取时点快照。个股资料未提供行情交易日时不使用抓取日期冒充交易日；页面可显示日期待补。

## 身份识别

先以Unicode NFKC统一全角代码、空格和大小写，再精确匹配名称与全称。全称缺失时，只有包含匹配唯一时才接受；多个候选返回列表。代码必须存在于当前A股目录，交易所后缀必须匹配。

目录缓存七天，不包含Token，可删除 `.company-profile-cache` 以强制更新。无法取得有效目录时不退回“根据代码前缀猜公司身份”。
