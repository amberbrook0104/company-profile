"""Fetch an A-share company snapshot. Standard library only; never persist secrets."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

TOKEN_NAMES = ('TUSHARE_TOKEN', 'TUSHARE_API_TOKEN', 'TS_TOKEN')
API_URL = 'https://api.tushare.pro'
DOCS = dict(stock_basic=25, stock_company=112, income=33, balancesheet=36,
            cashflow=44, daily_basic=32, fina_mainbz=81, top10_holders=61)


def shanghai_now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))


def valid_token(value):
    value = str(value or '').strip()
    return (len(value) >= 20 and bool(re.fullmatch(r'[A-Za-z0-9_-]+', value))
            and not any(s in value.lower() for s in ('your_token', 'yourtoken', 'xxxx', 'placeholder', 'example')))


def token_from_file(path):
    text = Path(path).expanduser().read_text(encoding='utf-8-sig').strip()
    if text.startswith('{'):
        obj = json.loads(text)
        return next((str(obj[k]).strip() for k in (*TOKEN_NAMES, 'token', 'tushare_token') if obj.get(k)), '')
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows and 'token' in rows[0]:
        return rows[0]['token'].strip()
    for key in TOKEN_NAMES:
        found = re.search(r'^\s*(?:export\s+)?' + key + r'\s*=\s*[\"\']?([^\s\"\'#]+)', text, re.M)
        if found:
            return found.group(1)
    return text.strip('\"\'')


def load_token(token_file=None):
    explicit = token_file or os.environ.get('TUSHARE_TOKEN_FILE')
    if explicit:
        try:
            token = token_from_file(explicit)
        except (OSError, ValueError):
            raise ValueError('指定凭证文件无法读取或格式错误；未显示文件内容。') from None
        if not valid_token(token):
            raise ValueError('指定凭证文件为空、格式不符或包含示例占位值。')
        return token, '指定凭证文件'
    for key in TOKEN_NAMES:
        token = os.environ.get(key, '').strip()
        if valid_token(token):
            return token, '进程环境变量 ' + key
    if sys.platform == 'win32':
        import winreg
        for root, subkey, label in (
            (winreg.HKEY_CURRENT_USER, 'Environment', 'Windows 用户环境'),
            (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Windows 系统环境')):
            try:
                with winreg.OpenKey(root, subkey) as handle:
                    for key in TOKEN_NAMES:
                        try:
                            token = str(winreg.QueryValueEx(handle, key)[0]).strip()
                            if valid_token(token):
                                return token, label + ' ' + key
                        except OSError:
                            pass
            except OSError:
                pass
    local_config = Path(__file__).resolve().parents[1] / 'references' / 'local-config.json'
    if local_config.is_file():
        try:
            settings = json.loads(local_config.read_text(encoding='utf-8-sig'))
            configured_file = settings.get('token_file')
            if configured_file:
                token = token_from_file(configured_file)
                if valid_token(token):
                    return token, 'Skill 本机配置引用的凭证文件'
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    sdk_file = Path.home() / 'tk.csv'
    if sdk_file.is_file():
        try:
            token = token_from_file(sdk_file)
            if valid_token(token):
                return token, 'Tushare SDK 默认凭证文件'
        except (OSError, ValueError):
            pass
    raise ValueError('未找到可用 Tushare Token（环境变量、Skill 本机配置及 ~/tk.csv）；示例占位值不可使用。请指出已有凭证文件位置。')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.URLError('API redirect refused')


class AuthenticationError(RuntimeError):
    pass


class Client:
    def __init__(self, token, timeout=20, interval=1.1):
        self.token, self.timeout, self.interval = token, timeout, interval
        self.sources = []
        self.raw = {}
        self.opener = urllib.request.build_opener(NoRedirect())
        self.last_call = 0.0

    def fetch(self, api, params, fields):
        source = {'api': api, 'url': f'https://tushare.pro/document/2?doc_id={DOCS[api]}',
                  'params': params, 'retrieved_at': shanghai_now().isoformat(timespec='seconds'),
                  'status': 'error', 'rows': 0, 'message': ''}
        self.sources.append(source)
        payload = json.dumps({'api_name': api, 'token': self.token,
                              'params': params, 'fields': fields}).encode('utf-8')
        for attempt in range(3):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            try:
                request = urllib.request.Request(API_URL, payload, {'Content-Type': 'application/json'}, method='POST')
                with self.opener.open(request, timeout=self.timeout) as response:
                    body = response.read(12_000_001)
                if len(body) > 12_000_000:
                    raise ValueError('oversize response')
                result = json.loads(body)
                if result.get('code') != 0:
                    message = str(result.get('msg') or '').replace(self.token, '[REDACTED]')
                    if re.search(r'token|令牌|认证|凭证', message, re.I):
                        source['message'] = '认证失败'
                        raise AuthenticationError('Tushare 认证失败；凭证未显示。')
                    rate_limit = bool(re.search(r'频率|频次|每分钟|每小时|rate.?limit|too many', message, re.I))
                    if rate_limit and attempt < 2:
                        time.sleep(3 * (attempt + 1))
                        continue
                    source['message'] = ('调用频率限制' if rate_limit else
                                         '权限不足' if result.get('code') == 2002 or re.search(r'权限|积分', message) else
                                         '接口错误，返回码 ' + str(result.get('code')))
                    source['status'] = 'unavailable'
                    return []
                data = result.get('data') or {}
                rows = [dict(zip(data.get('fields', []), item)) for item in data.get('items', [])]
                # Persist response data only, never the authenticated request or server message.
                self.raw[api] = rows
                source.update(status='ok' if rows else 'empty', rows=len(rows))
                return rows
            except AuthenticationError:
                raise
            except (OSError, ValueError, TypeError, KeyError):
                if attempt == 2:
                    source['message'] = '连接或响应失败（未保存请求体和错误原文）'
                    return []
                time.sleep(attempt + 1)
        return []


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def latest_financials(rows, as_of):
    chosen = {}
    # Actual announcement date first; report_type 1 is the consolidated cumulative statement.
    for row in rows:
        end = str(row.get('end_date') or '')
        ann = str(row.get('f_ann_date') or row.get('ann_date') or '')
        if not re.fullmatch(r'\d{8}', end) or not re.fullmatch(r'\d{8}', ann):
            continue
        if end > as_of or ann > as_of or str(row.get('report_type', '1')) != '1':
            continue
        previous = chosen.get(end)
        priority = (ann, str(row.get('update_flag') or ''))
        previous_priority = (str(previous.get('f_ann_date') or previous.get('ann_date') or ''),
                             str(previous.get('update_flag') or '')) if previous else ('', '')
        if previous is None or priority > previous_priority:
            chosen[end] = row
    return chosen


def normalize(raw, code, as_of, sources, retrieved_at):
    notes = []
    financial_maps = {key: latest_financials(raw.get(key, []), as_of)
                      for key in ('income', 'balancesheet', 'cashflow')}
    periods = sorted(set().union(*(set(x) for x in financial_maps.values())))
    annual = [x for x in periods if x.endswith('1231')][-3:]
    selected = set(annual)
    if periods and not periods[-1].endswith('1231'):
        selected.add(periods[-1])
    fin = []
    for end in sorted(selected):
        inc, bal, cash = [financial_maps[key].get(end, {}) for key in ('income', 'balancesheet', 'cashflow')]
        revenue_field = 'revenue' if number(inc.get('revenue')) is not None else 'total_revenue'
        revenue, profit = number(inc.get(revenue_field)), number(inc.get('n_income_attr_p'))
        previous = financial_maps['income'].get(str(int(end[:4]) - 1) + end[4:], {})
        previous_revenue = number(previous.get(revenue_field))
        growth = ((revenue / previous_revenue - 1) * 100
                  if revenue is not None and previous_revenue is not None and previous_revenue > 0 else None)
        assets, liabilities = number(bal.get('total_assets')), number(bal.get('total_liab'))
        fin.append({'period': end, 'revenue': revenue, 'revenue_field': revenue_field,
                    'net_profit_parent': profit, 'revenue_yoy': growth,
                    'assets': assets, 'liabilities': liabilities,
                    'equity_parent': number(bal.get('total_hldr_eqy_exc_min_int')),
                    'operating_cashflow': number(cash.get('n_cashflow_act')),
                    'parent_net_margin': profit / revenue * 100 if revenue and profit is not None else None,
                    'debt_ratio': liabilities / assets * 100 if assets and liabilities is not None else None,
                    'announcement_dates': {k: financial_maps[k].get(end, {}).get('f_ann_date')
                                           or financial_maps[k].get(end, {}).get('ann_date') for k in financial_maps},
                    'company_type': inc.get('comp_type')})
    basic = next((x for x in raw.get('stock_basic', []) if x.get('ts_code') == code), {})
    company = next((x for x in raw.get('stock_company', []) if x.get('ts_code') == code), {})
    market_rows = [x for x in raw.get('daily_basic', []) if str(x.get('trade_date') or '') <= as_of]
    market = max(market_rows, key=lambda x: str(x.get('trade_date') or ''), default={})
    holders_rows = [x for x in raw.get('top10_holders', [])
                    if x.get('ann_date') and str(x['ann_date']) <= as_of and str(x.get('end_date') or '') <= as_of]
    holder_period = max((str(x.get('end_date') or '') for x in holders_rows), default='')
    holders = sorted([x for x in holders_rows if x.get('end_date') == holder_period],
                     key=lambda x: number(x.get('hold_ratio')) or 0, reverse=True)
    holder_seen, selected_holders = set(), []
    for holder in sorted(holders, key=lambda x: (str(x.get('ann_date') or '')), reverse=True):
        key = holder.get('holder_name')
        if key not in holder_seen:
            selected_holders.append(holder)
            holder_seen.add(key)
    holders = sorted(selected_holders, key=lambda x: number(x.get('hold_ratio')) or 0, reverse=True)[:5]
    segments_rows = raw.get('fina_mainbz', [])
    segment_period = max((str(x.get('end_date') or '') for x in segments_rows
                          if str(x.get('end_date') or '') <= as_of), default='')
    segments = [x for x in segments_rows if x.get('end_date') == segment_period]
    segment_issues, seen = [], set()
    if len(segments_rows) >= 100:
        segment_issues.append('主营接口可能达到单次行数上限')
    for segment in segments:
        label = str(segment.get('bz_item') or '').strip()
        if not label or label in seen or re.search(r'合计|小计|总计', label):
            segment_issues.append('分类包含重复名称、空名称或汇总项')
        seen.add(label)
        if segment.get('curr_type') != 'CNY':
            segment_issues.append('存在非人民币或未知货币')
        if number(segment.get('bz_sales')) is None or number(segment.get('bz_sales')) < 0:
            segment_issues.append('存在缺失或负收入')
    total = sum(number(x.get('bz_sales')) or 0 for x in segments)
    if total <= 0:
        segment_issues.append('无有效收入分项')
    segment_items = [{'name': x.get('bz_item'), 'revenue': number(x.get('bz_sales')),
                      'listed_share': number(x.get('bz_sales')) / total * 100
                      if number(x.get('bz_sales')) is not None and total > 0 else None}
                     for x in sorted(segments, key=lambda x: number(x.get('bz_sales')) or 0, reverse=True)]
    if len(segments) > 6 and not segment_issues:
        tail = segment_items[5:]
        segment_items = segment_items[:5] + [{'name': '其他所列分项',
                         'revenue': sum(x['revenue'] for x in tail),
                         'listed_share': sum(x['listed_share'] for x in tail)}]
    for source in sources:
        if source['status'] != 'ok':
            notes.append(source['api'] + '：' + (source['message'] or '暂无数据'))
    notes.extend(['公司基本资料为抓取时点快照。主营构成无公告日期，历史时点须核对原公告。',
                  '财务使用合并累计报表，金额人民币元；市值原始单位万元。'])
    if any(str(x.get('comp_type')) in ('2', '3', '4', '7') for x in financial_maps['income'].values()):
        notes.append('金融企业：营业收入字段及现金流指标须结合行业会计口径解读。')
    return {'schema_version': 1, 'code': code, 'as_of': as_of, 'retrieved_at': retrieved_at,
            'company': {**basic, **company}, 'market': market, 'financials': fin,
            'segments': {'period': segment_period, 'dimension': 'P', 'currency': 'CNY',
                         'items': segment_items, 'issues': sorted(set(segment_issues)),
                         'verified': False, 'denominator': '所列产品分项收入合计'},
            'holders': {'period': holder_period, 'items': holders}, 'sources': sources, 'notes': notes}


def dump_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


