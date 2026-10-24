import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from fetch_profile import choose_provider
import fetch_profile
from providers import map_statement, field
from render_profile import fmt, render
from resolve_stock import resolve_stock, StockResolutionError
from tushare_backend import valid_token, latest_financials

CATALOG = [
    {'ts_code': '000858.SZ', 'name': '五粮液', 'fullname': '宜宾五粮液股份有限公司'},
    {'ts_code': '600519.SH', 'name': '贵州茅台', 'fullname': '贵州茅台酒股份有限公司'},
    {'ts_code': '000001.SZ', 'name': '平安银行', 'fullname': '平安银行股份有限公司'},
    {'ts_code': '601318.SH', 'name': '中国平安', 'fullname': '中国平安保险（集团）股份有限公司'}]


class Resolution(unittest.TestCase):
    def test_short_full_and_common_code_formats(self):
        for query in ['五粮液', '宜宾五粮液股份有限公司', '000858', '000858.SZ', 'sz000858', '000858sz', 'ＳＺ０００８５８', ' 五 粮 液 ']:
            with self.subTest(query=query):
                self.assertEqual(resolve_stock(query, CATALOG)['ts_code'], '000858.SZ')

    def test_full_name_when_catalog_has_only_short_name(self):
        short_only = [{k:v for k,v in row.items() if k != 'fullname'} for row in CATALOG]
        self.assertEqual(resolve_stock('宜宾五粮液股份有限公司', short_only)['ts_code'], '000858.SZ')

    def test_ambiguous_name_lists_candidates(self):
        with self.assertRaises(StockResolutionError) as caught:
            resolve_stock('平安', CATALOG)
        self.assertEqual(len(caught.exception.candidates), 2)

    def test_wrong_exchange_unknown_and_empty_rejected(self):
        for query in ['000858.SH', 'sh000858.SZ', '999999', '', '不存在公司', '股份有限公司']:
            with self.subTest(query=query), self.assertRaises(StockResolutionError):
                resolve_stock(query, CATALOG)


class Financials(unittest.TestCase):
    def test_source_selection(self):
        self.assertEqual(choose_provider('auto', None), 'akshare')
        self.assertEqual(choose_provider('auto', 'token-present'), 'tushare')
        self.assertEqual(choose_provider('akshare', 'token-present'), 'akshare')
        with self.assertRaises(ValueError): choose_provider('tushare', None)

    def test_sina_consolidated_mapping_and_original_amount(self):
        rows = [{'报告日':'20251231', '类型':'合并期末','更新日期':'2026-04-30 T10:00:00',
                 '营业收入':'40,528,509,770.23','归属于母公司所有者的净利润':'8,954,257,202.51'},
                {'报告日':'20251231','类型':'母公司期末','营业收入':999}]
        mapped = map_statement(rows, 'income', '000858.SZ', '20261023')
        self.assertEqual(len(mapped),1)
        self.assertEqual(mapped[0]['revenue'],40528509770.23)
        self.assertEqual(mapped[0]['ann_date'],'20260430')
        self.assertIn('非公告日', mapped[0]['date_basis'])

    def test_units_missingness_and_zero(self):
        self.assertEqual(field({'经营活动产生的现金流量净额(元)':'0'},'经营活动产生的现金流量净额'),0)
        self.assertIsNone(field({'营业收入':'--'},'营业收入'))
        self.assertEqual(fmt(27842774.184,1e4),'2,784.28')
        self.assertEqual(fmt(0),'0.00')
        self.assertEqual(fmt(None),'—')

    def test_announcement_and_report_type_boundaries(self):
        base={'end_date':'20251231','report_type':'1'}
        rows=[dict(base,ann_date='20260301',revenue=1),dict(base,ann_date='20260401',revenue=2),
              dict(base,ann_date='20261101',revenue=99),dict(base,ann_date='20260501',report_type='6',revenue=88)]
        self.assertEqual(latest_financials(rows,'20261023')['20251231']['revenue'],2)

    def test_schema_compatible_with_renderer(self):
        profile=json.loads((ROOT/'examples/wuliangye/profile.json').read_text(encoding='utf-8'))
        output=render(profile)
        self.assertIn('五粮液',output)
        self.assertIn('284.17',output)
        self.assertNotIn('<script',output)

    def test_placeholder_token_rejected(self):
        self.assertFalse(valid_token('your_tushare_token'))

    def test_akshare_cli_marks_provider_dates_without_inventing_announcements(self):
        base={'ts_code':'000858.SZ','end_date':'20251231','ann_date':'20260430','report_type':'1'}
        raw={'stock_basic':[CATALOG[0]],'income':[dict(base,revenue=100, n_income_attr_p=20)],
             'balancesheet':[dict(base,total_assets=200,total_liab=60,total_hldr_eqy_exc_min_int=140)],
             'cashflow':[dict(base,n_cashflow_act=10)],
             'top10_holders':[dict(base,holder_name='示例机构',hold_ratio=10)]}
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temporary:
            with patch.object(fetch_profile,'catalog_cached',return_value=CATALOG), \
                 patch.object(fetch_profile,'collect_akshare',return_value=(raw,[],[],{})):
                code=fetch_profile.main(['五粮液','--source','akshare','--out',temporary])
            self.assertEqual(code,0)
            result=json.loads((Path(temporary)/'profile.json').read_text(encoding='utf-8'))
            self.assertIn('provider_update_dates',result['financials'][0])
            self.assertNotIn('announcement_dates',result['financials'][0])
            self.assertNotIn('ann_date',result['holders']['items'][0])


if __name__ == '__main__': unittest.main()
