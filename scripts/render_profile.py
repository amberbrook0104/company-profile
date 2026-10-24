"""Render a standalone, offline company one-pager with inline SVG charts."""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import re


def esc(value):
    return html.escape(str(value if value is not None else '—'), quote=True)


def numeric(value):
    try:
        num = float(value)
        return num if math.isfinite(num) else None
    except (ValueError, TypeError):
        return None


def fmt(value, divisor=1, suffix='', decimals=2):
    value = numeric(value)
    return '—' if value is None else f'{value / divisor:,.{decimals}f}{suffix}'


def period_label(value, cumulative=True):
    value = str(value or '')
    if not re.fullmatch(r'\d{8}', value):
        return '待补'
    result = value[:4] + {'1231': '年', '0331': 'Q1累计', '0630': 'H1累计', '0930': 'Q3累计'}.get(value[4:], '/' + value[4:])
    return result if cumulative else result.replace('累计', '期末')


def safe_link(url, label):
    return (f'<a href="{esc(url)}" target="_blank" rel="noreferrer">{esc(label)}</a>'
            if re.match(r'^https?://', str(url or ''), re.I) else esc(label))


def chart(financials):
    annual = [x for x in financials if x['period'].endswith('1231')]
    if not annual:
        return '<p class="empty">暂无完整年度趋势数据</p>'
    values = [numeric(x.get(k)) for x in annual for k in ('revenue', 'net_profit_parent')]
    valid = [v / 1e8 for v in values if v is not None]
    if not valid:
        return '<p class="empty">暂无可绘制财务数据</p>'
    low, high = min(0, min(valid)), max(0, max(valid))
    span = high - low or 1
    high += span * .18
    low -= span * .06
    span = high - low
    y = lambda value: 176 - (value - low) / span * 132
    zero = y(0)
    parts = ['<svg class="trend" viewBox="0 0 380 224" role="img" aria-label="年度营收与归母净利润，单位亿元">',
             f'<line x1="8" x2="373" y1="{zero:.1f}" y2="{zero:.1f}" stroke="#bbc8d4"/>']
    for i, row in enumerate(annual):
        center = 65 + i * 118
        for j, (key, color) in enumerate((('revenue', '#163a5f'), ('net_profit_parent', '#087f8c'))):
            value = numeric(row.get(key))
            if value is None:
                continue
            value /= 1e8
            top, bottom = sorted((y(value), zero))
            x = center + (j - 1) * 38
            parts.append(f'<rect x="{x}" y="{top:.1f}" width="30" height="{max(bottom-top,.5):.1f}" rx="2" fill="{color}"/>')
            label_y = top - 6 if value >= 0 else bottom + 13
            parts.append(f'<text x="{x+15}" y="{label_y:.1f}" text-anchor="middle" font-size="12" fill="#34465a">{value:,.1f}</text>')
        parts.append(f'<text x="{center}" y="212" text-anchor="middle" font-size="14" fill="#64748b">{esc(row["period"][:4])}</text>')
    parts.append('</svg>')
    return ''.join(parts)


CSS = r'''
*{box-sizing:border-box}html,body{margin:0;padding:0}body{background:#e6ebef;color:#263749;font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;font-size:16px}a{color:inherit;text-decoration:none}.sheet{width:1600px;height:1100px;padding:36px 42px;background:white;display:grid;grid-template-rows:126px 92px 1fr 80px;gap:18px;margin:24px auto;position:relative}.hero{display:flex;justify-content:space-between;gap:30px;border-bottom:3px solid #163a5f;padding-bottom:18px}.eyebrow{font-size:12px;letter-spacing:2px;color:#087f8c;font-weight:700;margin:0 0 8px}.hero h1{font-size:38px;line-height:1.25;margin:0 0 10px;color:#163a5f}.subtitle{color:#68798b;font-size:15px}.stamp{min-width:220px;text-align:right;color:#65788a;line-height:1.7;font-size:14px;padding-top:8px}.stamp b{display:block;color:#163a5f;font-size:19px}.metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:14px}.metric{border:1px solid #dbe4ea;border-top:3px solid #087f8c;padding:10px 14px}.metric .label{font-size:13px;color:#5f7083}.metric strong{display:block;font-size:28px;line-height:1.35;color:#163a5f;font-variant-numeric:tabular-nums}.metric small{font-size:11px;color:#748395}.main{display:grid;grid-template-columns:.94fr 1.06fr;grid-template-rows:1fr 1.15fr;gap:18px;min-height:0}.card{border:1px solid #dbe4ea;padding:18px 22px;min-width:0;min-height:0}.card h2{font-size:19px;line-height:1.3;color:#163a5f;margin:0 0 13px;padding-left:11px;border-left:4px solid #087f8c}.section-meta{font-size:12px;color:#748395;font-weight:400;margin-left:10px}.overview{font-size:17px;line-height:1.75;margin:0 0 13px;white-space:normal;overflow-wrap:anywhere}.factgrid{display:grid;grid-template-columns:1fr 1fr;gap:7px 16px;font-size:13px;color:#6a7989}.factgrid b{font-weight:500;color:#263749;margin-left:8px}.positioning{font-size:13px;line-height:1.55;color:#526577;margin:11px 0 0}.event{font-size:12px;line-height:1.5;margin-top:5px;color:#65788a}.segment{margin-bottom:9px}.segment-head{display:flex;justify-content:space-between;gap:10px;font-size:13px;line-height:1.3;margin-bottom:4px}.segment-head span:first-child{max-width:72%;overflow-wrap:anywhere}.track{height:8px;background:#e8eef2}.fill{height:100%;background:#087f8c}.footnote{font-size:11px;color:#748395;line-height:1.5;margin-top:8px}.pending{padding:13px 16px;border-left:3px solid #b48b50;background:#f8f4ed;color:#866531;line-height:1.6;font-size:14px}.empty{color:#8a98a6;font-size:14px;line-height:1.7}.finance{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}.finance th{text-align:right;color:#163a5f;background:#eef3f7;font-size:12px;padding:8px 6px}.finance th:first-child{text-align:left}.finance td{border-bottom:1px solid #e7edf1;text-align:right;padding:6px}.finance td:first-child{text-align:left;color:#5d6f81}.finance tr:last-child td{border-bottom:none}.trend{width:100%;height:150px;display:block}.legend{font-size:11px;color:#66788a;margin:-4px 0 8px}.dot{display:inline-block;width:9px;height:9px;margin-right:5px;background:#163a5f}.dot.green{background:#087f8c;margin-left:18px}.ownership h3{font-size:14px;line-height:1.3;color:#163a5f;margin:4px 0 8px}.holder{display:flex;justify-content:space-between;gap:15px;font-size:12px;line-height:1.4;padding:4px 0;border-bottom:1px solid #edf1f4}.holder span:first-child{overflow-wrap:anywhere;max-width:89%}.footer{font-size:11px;line-height:1.55;color:#748395;border-top:1px solid #ccd7e0;padding-top:9px;overflow-wrap:anywhere}.footer strong{color:#526577}.synthetic{color:#a02626;font-weight:800}.footer a{text-decoration:underline;text-underline-offset:2px}.sheet[data-test="true"]:before{content:"虚构测试数据 · 仅验证模板";position:absolute;right:290px;top:40px;color:#ae2d2d;font-weight:700;font-size:18px}@media print{@page{size:400mm 275mm;margin:0}html,body{width:400mm;height:275mm;background:white}.sheet{margin:0;width:1600px;height:1100px;break-inside:avoid;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
'''


def render(profile, editorial=None):
    editorial = editorial or {}
    if any(editorial.get(k) for k in ('overview', 'positioning', 'events')) and not editorial.get('sources'):
        raise ValueError('补充文字需要 sources；不可生成没有来源的业务判断。')
    for k, limit in (('overview', 200), ('positioning', 80)):
        if len(editorial.get(k, '')) > limit:
            raise ValueError(f'{k} 过长；请精简到 {limit} 字以内再渲染。')
    if len(editorial.get('events', [])) > 2 or any(len(x) > 65 for x in editorial.get('events', [])):
        raise ValueError('近期事项最多两条，每条不超过 65 字。')
    company = profile.get('company', {})
    fin = sorted(profile.get('financials', []), key=lambda x: x['period'])[-4:]
    latest = fin[-1] if fin else {}
    market = profile.get('market', {})
    title = company.get('name') or company.get('com_name') or profile['code']
    intro = editorial.get('overview')
    if not intro:
        original = str(company.get('main_business') or '').strip()
        intro = (original[:180] + '…' if len(original) > 180 else original) or '主营业务资料待补，需根据公司年报核实。'
    facts = [('证券代码', profile['code']), ('所属行业', company.get('industry')),
             ('上市日期', company.get('list_date')), ('总部地区', ' '.join(str(x) for x in (company.get('province') or company.get('area'), company.get('city')) if x)),
             ('成立日期', company.get('setup_date')), ('员工人数', fmt(company.get('employees'), decimals=0))]
    facts_html = ''.join(f'<div>{esc(k)}<b>{esc(v or "待补")}</b></div>' for k, v in facts)
    market_date = str(market.get('trade_date') or '待补')
    fin_date = period_label(latest.get('period'))
    metrics = [
        ('总市值 / 亿元', fmt(market.get('total_mv'), 1e4), market_date),
        ('市盈率 PE(TTM)', fmt(market.get('pe_ttm')) if numeric(market.get('pe_ttm')) is not None and numeric(market['pe_ttm']) > 0 else '—', market_date),
        ('营业收入 / 亿元', fmt(latest.get('revenue'), 1e8), fin_date),
        ('归母净利润 / 亿元', fmt(latest.get('net_profit_parent'), 1e8), fin_date),
        ('归母净利率', fmt(latest.get('parent_net_margin'), suffix='%'), fin_date),
        ('资产负债率', fmt(latest.get('debt_ratio'), suffix='%'), fin_date)]
    metrics_html = ''.join(f'<div class="metric"><div class="label">{esc(label)}</div><strong>{esc(value)}</strong><small>{esc(date)}</small></div>' for label, value, date in metrics)
    segments = profile.get('segments', {})
    segment_html = ''
    verified = (editorial.get('segments_verified') is True or segments.get('verified') is True) and not segments.get('issues')
    if not segments.get('items'):
        segment_html = '<p class="empty">暂无可用的主营收入构成数据</p>'
    elif not verified:
        names = '、'.join(str(x.get('name') or '') for x in segments['items'][:6])
        segment_html = f'<p class="overview">{esc(names)}</p><div class="pending">主营分项已取得，分类层级与口径尚待年报核实；暂不展示占比图。</div>'
    else:
        for item in segments['items'][:6]:
            share = numeric(item.get('listed_share'))
            if share is None or not 0 <= share <= 100:
                raise ValueError('主营分项占比不在 0—100 范围。')
            segment_html += f'<div class="segment"><div class="segment-head"><span>{esc(item["name"])}</span><span>{fmt(share, suffix="%", decimals=1)} · {fmt(item.get("revenue"), 1e8)} 亿元</span></div><div class="track"><div class="fill" style="width:{share:.3f}%"></div></div></div>'
        segment_html += '<div class="footnote">占比口径：' + esc(segments.get('denominator') or '所列产品分项收入合计') + '。</div>'
    headings = ''.join(f'<th>{esc(period_label(x["period"]))}</th>' for x in fin)
    rows = [('营业收入', 'revenue', 1e8, ''), ('营收同比', 'revenue_yoy', 1, '%'),
            ('归母净利润', 'net_profit_parent', 1e8, ''), ('归母净利率', 'parent_net_margin', 1, '%'),
            ('总资产', 'assets', 1e8, ''), ('总负债', 'liabilities', 1e8, ''),
            ('归母权益', 'equity_parent', 1e8, ''), ('经营现金流净额', 'operating_cashflow', 1e8, ''),
            ('资产负债率', 'debt_ratio', 1, '%')]
    table = '<table class="finance"><thead><tr><th>人民币亿元 / %</th>' + headings + '</tr></thead><tbody>'
    for label, key, divisor, suffix in rows:
        table += f'<tr><td>{label}</td>' + ''.join(f'<td>{fmt(x.get(key), divisor, suffix)}</td>' for x in fin) + '</tr>'
    table += '</tbody></table>' if fin else '</tbody></table><p class="empty">暂无可用财务数据</p>'
    holders = profile.get('holders', {})
    holder_html = ''.join(f'<div class="holder"><span>{esc(x.get("holder_name"))}</span><span>{fmt(x.get("hold_ratio"), suffix="%")}</span></div>' for x in holders.get('items', [])[:5]) or '<p class="empty">股东数据待补</p>'
    links, seen_source_urls = [], set()
    for source in profile.get('sources', []):
        if source.get('status') != 'ok':
            continue
        url = source.get('url')
        if url in seen_source_urls:
            continue
        seen_source_urls.add(url)
        label = 'AKShare接口说明' if str(source.get('api', '')).startswith('akshare.') else source.get('api')
        links.append(safe_link(url, label))
    links += [safe_link(x.get('url'), f'补充来源{i+1}：' + str(x.get('title') or '公告')) for i, x in enumerate(editorial.get('sources', []))]
    missing = [x.get('api') for x in profile.get('sources', []) if x.get('status') != 'ok']
    source_line = ' · '.join(links) or '尚无已取得的数据来源'
    missing_line = ('部分资料待补（' + str(len(missing)) + '项，详见来源附件）。') if missing else ''
    context_note = ('AKShare为当前抓取快照；报表更新日期不等于原公告日，不能用于历史时点回溯。'
                    if profile.get('provider') == 'akshare' else
                    '公司资料为抓取时点快照；主营构成无公告日，历史时点须核对公告。')
    test = profile.get('test_data') is True
    layout_css = '.main{grid-template-rows:1fr 1.32fr}.trendhold{display:grid;grid-template-columns:1.1fr 1fr;gap:20px;align-items:start}.trend{height:236px}.ownership{padding-top:12px}.holder{padding:9px 0}.finance td{padding:5px 6px}'
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=1600"><title>{esc(title)} · 公司一页概览</title><style>{CSS}{layout_css}</style></head>
<body><article class="sheet" data-test="{str(test).lower()}">
<header class="hero"><div><p class="eyebrow">COMPANY PROFILE / 公司一页概览</p><h1>{esc(title)}</h1><div class="subtitle">{esc(company.get('com_name') or company.get('fullname') or '')}　{esc(profile['code'])}　|　{esc(company.get('industry') or '行业待补')}</div></div><div class="stamp"><b>公司基本面速览</b>数据截止 {esc(profile['as_of'])}<br>行情日期 {esc(market_date)}</div></header>
<section class="metrics">{metrics_html}</section>
<main class="main"><section class="card" data-check="true"><h2>公司概况与业务定位</h2><p class="overview">{esc(intro)}</p><div class="factgrid">{facts_html}</div>{('<p class="positioning">'+esc(editorial['positioning'])+'</p>') if editorial.get('positioning') else ''}{''.join('<div class="event">'+esc(x)+'</div>' for x in editorial.get('events', []))}</section>
<section class="card" data-check="true"><h2>主营业务构成<span class="section-meta">{esc(period_label(segments.get('period')))} · 产品维度</span></h2>{segment_html}</section>
<section class="card" data-check="true"><h2>财务摘要<span class="section-meta">合并报表 · 中期为累计值</span></h2>{table}<div class="footnote">同比比较上年同期；前期营收基数非正时不计算百分比。归母净利率 = 归母净利润 / 营业收入。</div></section>
<section class="card" data-check="true"><h2>经营趋势与股权结构</h2><div class="trendhold"><div>{chart(fin)}<div class="legend"><span class="dot"></span>营业收入 / 亿元<br><span class="dot" style="background:#087f8c"></span>归母净利润 / 亿元</div></div><div class="ownership"><h3>前五大股东<span class="section-meta">{esc(period_label(holders.get('period'), cumulative=False))}</span></h3>{holder_html}</div></div></section></main>
<footer class="footer" data-check="true"><strong>{'<span class="synthetic">虚构测试数据，仅用于验证模板。</span> ' if test else ''}来源：</strong>{source_line}<br>{esc(missing_line)}{esc(context_note)}完整接口状态和数据见同目录附件。<br>生成时间：{esc(profile.get('retrieved_at'))}　|　财务与主营金额：人民币亿元；股东持股比例不代表控制权。</footer>
</article></body></html>'''


def main():
    parser = argparse.ArgumentParser(description='将 profile.json 渲染成可离线打开的公司一页 HTML')
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--editorial', type=Path)
    args = parser.parse_args()
    profile = json.loads(args.input.read_text(encoding='utf-8-sig'))
    editorial = json.loads(args.editorial.read_text(encoding='utf-8-sig')) if args.editorial else None
    output = render(profile, editorial)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(output, encoding='utf-8')
    print(str(args.out.resolve()))


if __name__ == '__main__':
    main()
