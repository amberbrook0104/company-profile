"""Name/code entry point: Tushare with a token, otherwise AKShare."""
import argparse
import csv
import datetime as dt
import getpass
import json
from pathlib import Path
import sys

from providers import collect_akshare, collect_tushare, get_catalog
from resolve_stock import StockResolutionError, resolve_stock
from tushare_backend import AuthenticationError, dump_json, load_token, normalize, shanghai_now, valid_token


def choose_provider(requested, token):
    if requested == 'tushare' and not token:
        raise ValueError('选择 Tushare 需配置 TUSHARE_TOKEN、--token-file 或 --prompt-token。')
    return ('tushare' if token else 'akshare') if requested == 'auto' else requested


def catalog_cached(provider, token, directory):
    path = directory / (provider + '-securities.json')
    if path.is_file():
        try:
            cache = json.loads(path.read_text(encoding='utf-8'))
            age = (shanghai_now() - dt.datetime.fromisoformat(cache['retrieved_at'])).total_seconds()
            if 0 <= age < 7 * 86400:
                return cache['stocks']
        except (ValueError, KeyError, TypeError):
            pass
    stocks = get_catalog(provider, token)
    directory.mkdir(parents=True, exist_ok=True)
    dump_json(path, {'retrieved_at': shanghai_now().isoformat(), 'provider': provider, 'stocks': stocks})
    return stocks


def parser():
    result = argparse.ArgumentParser(description='输入A股全称、简称或代码，自动选择Tushare/AKShare。')
    result.add_argument('identifier', nargs='?', help='五粮液、宜宾五粮液股份有限公司、000858、SZ000858 等')
    result.add_argument('--query', '--code', dest='query')
    result.add_argument('--out', type=Path, default=Path('output/company-profile'))
    result.add_argument('--source', choices=['auto', 'tushare', 'akshare'], default='auto')
    result.add_argument('--as-of', default=shanghai_now().strftime('%Y%m%d'))
    result.add_argument('--cache-dir', type=Path, default=Path('.company-profile-cache'))
    result.add_argument('--resolve-only', action='store_true')
    result.add_argument('--token-file', type=Path, help='已有凭证文件路径，不显示内容')
    result.add_argument('--prompt-token', action='store_true', help='本机终端隐藏输入Token，留空则使用AKShare')
    return result


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    query = args.query or args.identifier
    if not query or (args.query and args.identifier):
        arguments.error('请通过位置参数或 --query/--code 提供一个股票名称或代码。')
    try:
        dt.datetime.strptime(args.as_of, '%Y%m%d')
        if args.as_of > shanghai_now().strftime('%Y%m%d'):
            raise ValueError()
    except ValueError:
        arguments.error('--as-of 必须为有效日期且不晚于今天')
    token = None
    try:
        if args.source != 'akshare':
            if args.prompt_token:
                if not sys.stdin.isatty():
                    raise ValueError('隐藏输入需要交互终端；非交互调用请使用环境变量或凭证文件。')
                token = getpass.getpass('Tushare Token（留空使用 AKShare）：').strip() or None
                if token and not valid_token(token):
                    raise ValueError('Token 格式不符或为示例占位值。')
            else:
                try:
                    token, _ = load_token(args.token_file)
                except ValueError:
                    if args.token_file:
                        raise
        provider = choose_provider(args.source, token)
        identity = resolve_stock(query, catalog_cached(provider, token, args.cache_dir))
        resolved = {k: identity.get(k, '') for k in ['ts_code', 'name', 'fullname']}
        if args.resolve_only:
            print(json.dumps({'provider': provider, 'resolved': resolved}, ensure_ascii=False))
            return 0
        if provider == 'tushare':
            raw, sources, notes, native = collect_tushare(identity, token, args.as_of)
        else:
            raw, sources, notes, native = collect_akshare(identity, args.as_of)
        retrieved = shanghai_now().isoformat(timespec='seconds')
        profile = normalize(raw, identity['ts_code'], args.as_of, sources, retrieved)
        profile.update(provider=provider, input_query=query, resolved_identity=resolved)
        profile['notes'].extend(notes)
        if provider == 'akshare':
            for row in profile['financials']:
                row['provider_update_dates'] = row.pop('announcement_dates', {})
            for row in profile['holders']['items']:
                row.pop('ann_date', None)
                row['date_basis'] = '抓取时点；原公告日未提供'
        metrics = ['revenue', 'net_profit_parent', 'assets', 'liabilities', 'equity_parent', 'operating_cashflow']
        if not any(any(row.get(key) is not None for key in metrics) for row in profile['financials']):
            raise RuntimeError('未取得可用的合并财务数据，停止生成空白概览；请更换数据源或核对公告。')
        args.out.mkdir(parents=True, exist_ok=True)
        dump_json(args.out / 'profile.json', profile)
        dump_json(args.out / 'raw.json', {'provider': provider, 'code': identity['ts_code'],
                  'retrieved_at': retrieved, 'data': raw, 'provider_original': native})
        with (args.out / 'sources.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=['api', 'url', 'params', 'retrieved_at', 'status', 'rows', 'message'])
            writer.writeheader()
            for source in sources:
                writer.writerow({**source, 'params': json.dumps(source['params'], ensure_ascii=False)})
        print(json.dumps({'provider': provider, 'resolved': resolved, 'output': str(args.out.resolve()),
                          'financial_periods': [x['period'] for x in profile['financials']]}, ensure_ascii=False))
        return 0
    except StockResolutionError as error:
        print(json.dumps({'error': str(error), 'candidates': error.candidates}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (AuthenticationError, RuntimeError, ValueError, OSError) as error:
        message = str(error)
        if token:
            message = message.replace(token, '[REDACTED]')
        print(message, file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
