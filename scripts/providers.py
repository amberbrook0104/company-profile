"""Tushare and AKShare adapters. All public outputs use the original profile schema."""
from contextlib import contextmanager
import datetime as dt
import importlib
import json
import math
import re
import time

from tushare_backend import Client, latest_financials, number, shanghai_now
from resolve_stock import inferred_exchange

AK_DOC = 'https://akshare.akfamily.xyz/data/stock/stock.html'


def ak_module():
    try:
        return importlib.import_module('akshare')
    except ImportError:
        raise RuntimeError('无 Token 路径需要 AKShare：python -m pip install -r requirements.txt') from None


@contextmanager
def request_timeout(seconds=20):
    """Bound AKShare requests that do not expose their own timeout argument."""
    import requests
    original = requests.sessions.Session.request
    def bounded(session, method, url, **kwargs):
        if kwargs.get('timeout') is None:
            kwargs['timeout'] = seconds
        return original(session, method, url, **kwargs)
    requests.sessions.Session.request = bounded
    try:
        yield
    finally:
        requests.sessions.Session.request = original


def records(frame):
    if frame is None:
        return []
    # pandas handles NaN, timestamps and NumPy scalar types before JSON persistence.
    return json.loads(frame.to_json(orient='records', date_format='iso', force_ascii=False))


def get_catalog(provider, token=None):
    if provider == 'tushare':
        client = Client(token)
        rows = client.fetch('stock_basic', {'list_status': 'L'},
                            'ts_code,symbol,name,fullname,area,industry,list_date,exchange')
        if not rows:
            raise RuntimeError('Tushare 股票目录不可用，请检查 Token、权限或网络。')
        return rows
    ak = ak_module()
    with request_timeout():
        rows = records(ak.stock_info_a_code_name())
    result = []
    for row in rows:
        code = str(row.get('code', '')).zfill(6)
        exchange = inferred_exchange(code)
        if exchange:
            result.append({'ts_code': code + '.' + exchange, 'symbol': code,
                           'name': row.get('name', ''), 'fullname': row.get('fullname', '')})
    if not result:
        raise RuntimeError('AKShare 股票目录未返回可识别的字段，需检查上游接口。')
    return result


def collect_tushare(identity, token, as_of):
    code = identity['ts_code']
    client = Client(token)
    client.raw['stock_basic'] = [identity]
    client.sources.append({'api': 'stock_basic', 'url': 'https://tushare.pro/document/2?doc_id=25',
        'params': {'ts_code': code}, 'retrieved_at': shanghai_now().isoformat(timespec='seconds'),
        'status': 'ok', 'rows': 1, 'message': ''})
    client.fetch('stock_company', {'ts_code': code}, 'ts_code,com_name,exchange,chairman,manager,setup_date,province,city,employees,website,introduction,main_business')
    start = f'{int(as_of[:4]) - 5}0101'
    common = 'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,update_flag,'
    for api, fields in [('income', 'revenue,total_revenue,n_income_attr_p,n_income,basic_eps'),
                        ('balancesheet', 'total_assets,total_liab,total_hldr_eqy_exc_min_int,money_cap'),
                        ('cashflow', 'n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act,c_pay_acq_const_fiolta')]:
        client.fetch(api, {'ts_code': code, 'start_date': start, 'end_date': as_of, 'report_type': '1'}, common + fields)
    recent = (dt.datetime.strptime(as_of, '%Y%m%d') - dt.timedelta(days=45)).strftime('%Y%m%d')
    client.fetch('daily_basic', {'ts_code': code, 'start_date': recent, 'end_date': as_of},
                 'ts_code,trade_date,close,pe_ttm,pb,ps_ttm,dv_ttm,total_mv,circ_mv,total_share')
    client.fetch('top10_holders', {'ts_code': code, 'start_date': start, 'end_date': as_of},
                 'ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio,holder_type')
    annual = sorted(x for x in latest_financials(client.raw.get('income', []), as_of) if x.endswith('1231'))
    if annual:
        client.fetch('fina_mainbz', {'ts_code': code, 'period': annual[-1], 'type': 'P'},
                     'ts_code,end_date,bz_item,bz_code,bz_sales,bz_profit,bz_cost,curr_type,update_flag')
    return client.raw, client.sources, [], {}


def date8(value):
    if value is None:
        return ''
    text = re.sub(r'[^0-9]', '', str(value))
    return text[:8] if len(text) >= 8 else ''


def key_normal(value):
    return re.sub(r'[\s()（）:：,，_\-]', '', str(value)).replace('元', '')


def field(row, *candidates):
    values = {key_normal(k): v for k, v in row.items()}
    for candidate in candidates:
        value = values.get(key_normal(candidate))
        if value is not None:
            if isinstance(value, str):
                value = value.replace(',', '').replace('%', '').strip()
            parsed = number(value)
            if parsed is not None:
                return parsed
    return None


def map_statement(rows, api, code, as_of):
    mapped = []
    for row in rows:
        period = date8(row.get('报告日') or row.get('报告日期'))
        if not period or period > as_of:
            continue
        kind = str(row.get('类型') or '')
        if '合并' not in kind:
            continue
        updated = date8(row.get('更新日期'))
        base = {'ts_code': code, 'end_date': period, 'ann_date': updated or as_of,
                'report_type': '1', 'update_flag': '0', 'date_basis': '供应商更新日期，非公告日'}
        if api == 'income':
            base.update(revenue=field(row, '营业收入'), total_revenue=field(row, '营业总收入'),
                n_income_attr_p=field(row, '归属于母公司所有者的净利润', '归属于母公司股东的净利润', '归属母公司股东的净利润'),
                n_income=field(row, '净利润'))
        elif api == 'balancesheet':
            base.update(total_assets=field(row, '资产总计', '总资产'), total_liab=field(row, '负债合计', '总负债'),
                total_hldr_eqy_exc_min_int=field(row, '归属于母公司所有者权益合计', '归属于母公司股东权益合计', '归属母公司所有者权益合计'))
        else:
            base.update(n_cashflow_act=field(row, '经营活动产生的现金流量净额', '经营活动现金流量净额'))
        mapped.append(base)
    return mapped


def collect_akshare(identity, as_of):
    if as_of != shanghai_now().strftime('%Y%m%d'):
        raise ValueError('AKShare 路径仅支持当前快照；历史公告时点请用 Tushare 并核对原公告。')
    ak = ak_module()
    code = identity['ts_code']; digits = code[:6]; prefix = code[-2:]
    raw = {'stock_basic': [identity]}; native = {}; sources = []
    notes = ['AKShare 新浪报表的更新日期为供应商更新日期，不能视为原公告日；当前结果不是历史时点数据库。']
    def call(api, **params):
        source = {'api': 'akshare.' + api, 'url': AK_DOC, 'params': params,
                  'retrieved_at': shanghai_now().isoformat(timespec='seconds'), 'status': 'error', 'rows': 0, 'message': ''}
        sources.append(source)
        try:
            with request_timeout():
                result = records(getattr(ak, api)(**params))
            native[api + ':' + str(params.get('symbol', ''))] = result
            source.update(status='ok' if result else 'empty', rows=len(result))
            return result
        except Exception as error:
            source['message'] = '上游接口不可用：' + type(error).__name__
            return []
    base_rows = call('stock_individual_info_em', symbol=digits, timeout=15)
    basic = {x.get('item'): x.get('value') for x in base_rows}
    identity.update(industry=basic.get('行业'), list_date=basic.get('上市时间'))
    company = {'ts_code': code}
    intro_rows = call('stock_individual_basic_info_xq', symbol=prefix+digits, timeout=15)
    intro = {x.get('item'): x.get('value') for x in intro_rows}
    company.update(com_name=intro.get('org_name_cn'), main_business=intro.get('main_operation_business'),
                   introduction=intro.get('org_cn_introduction'))
    if not company.get('main_business'):
        business = call('stock_zyjs_ths', symbol=digits)
        if business:
            company['main_business'] = business[0].get('主营业务')
    raw['stock_company'] = [company]
    for api, label in [('income', '利润表'), ('balancesheet', '资产负债表'), ('cashflow', '现金流量表')]:
        rows = call('stock_financial_report_sina', stock=prefix.lower()+digits, symbol=label)
        raw[api] = map_statement(rows, api, code, as_of)
        if rows and not raw[api]:
            notes.append(label + '未识别出合并报表，请核对类型与字段。')
    valuation = call('stock_value_em', symbol=digits)
    raw['daily_basic'] = []
    for row in valuation:
        day = date8(row.get('数据日期'))
        if day and day <= as_of:
            mv = field(row, '总市值')
            raw['daily_basic'].append({'ts_code': code, 'trade_date': day,
                'close': field(row, '当日收盘价'), 'pe_ttm': field(row, 'PE(TTM)'), 'pb': field(row, '市净率'),
                'total_mv': mv/10000 if mv is not None else None})
    if not raw['daily_basic'] and basic:
        value = number(basic.get('总市值'))
        raw['daily_basic'] = [{'ts_code': code, 'trade_date': '', 'close': number(basic.get('最新')),
                               'total_mv': value/10000 if value is not None else None}]
        notes.append('实时个股资料未提供可验证行情交易日；不以抓取日冒充交易日。')
    annual = sorted(x for x in latest_financials(raw['income'], as_of) if x.endswith('1231'))
    raw['fina_mainbz'] = []
    if annual:
        segment_rows = call('stock_zygc_em', symbol=prefix+digits)
        for row in segment_rows:
            if '产品' in str(row.get('分类类型')) and date8(row.get('报告日期')) == annual[-1]:
                raw['fina_mainbz'].append({'ts_code': code, 'end_date': annual[-1], 'bz_item': row.get('主营构成'),
                    'bz_sales': field(row, '主营收入'), 'curr_type': 'CNY'})
    periods = sorted(set(x['end_date'] for api in ['income', 'balancesheet', 'cashflow'] for x in raw[api]))
    raw['top10_holders'] = []
    if periods:
        rows = call('stock_gdfx_top_10_em', symbol=prefix.lower()+digits, date=periods[-1])
        for row in rows:
            raw['top10_holders'].append({'ts_code': code, 'ann_date': as_of, 'end_date': periods[-1],
                'holder_name': row.get('股东名称'), 'hold_ratio': field(row, '占总股本持股比例'),
                'date_basis': '抓取时点；原公告日未提供'})
        notes.append('AKShare 股东数据按报告期查询，抓取时点不等于其原始公告时点。')
    return raw, sources, notes, native
