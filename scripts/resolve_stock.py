"""Resolve A-share short/full names and common code formats using a live catalog."""
import re
import unicodedata


class StockResolutionError(ValueError):
    def __init__(self, message, candidates=None):
        super().__init__(message)
        self.candidates = candidates or []


def normalized(value):
    return re.sub(r'[\s·.,，。()（）\-_/]', '', unicodedata.normalize('NFKC', str(value))).casefold()


def canonical_code(value):
    text = unicodedata.normalize('NFKC', str(value)).upper().replace(' ', '')
    match = re.fullmatch(r'(?:(SH|SZ|BJ)[.:]?)?(\d{6})(?:[.:]?(SH|SZ|BJ))?', text)
    if not match:
        return None, None
    before, digits, after = match.groups()
    if before and after and before != after:
        raise StockResolutionError('前后交易所标识冲突，请检查代码。')
    return digits, before or after


def inferred_exchange(code):
    if code.startswith(('60', '68')):
        return 'SH'
    if code.startswith(('00', '30')):
        return 'SZ'
    if code.startswith(('4', '8', '92')):
        return 'BJ'
    return None


def resolve_stock(query, catalog):
    text = normalized(query)
    if not text:
        raise StockResolutionError('请输入股票名称、简称或六位代码。')
    unique = {}
    for row in catalog:
        code = str(row.get('ts_code') or '')
        if re.fullmatch(r'\d{6}\.(SH|SZ|BJ)', code):
            unique[code] = row
    catalog = list(unique.values())
    digits, exchange = canonical_code(query)
    if digits:
        matches = [x for x in catalog if x['ts_code'][:6] == digits]
        if exchange:
            matches = [x for x in matches if x['ts_code'].endswith('.' + exchange)]
        if len(matches) == 1:
            return matches[0]
        raise StockResolutionError('代码未在当前A股目录中找到，或交易所后缀不匹配。', matches)
    def aliases(row):
        return [normalized(row.get(k, '')) for k in ('name', 'fullname', 'com_name') if row.get(k)]
    matches = [row for row in catalog if text in aliases(row)]
    if not matches:
        # Full legal names often contain a geographic prefix absent from exchange short names.
        meaningful = re.sub(r'(股份有限公司|有限责任公司|有限公司)$', '', text)
        if len(meaningful) < 2:
            raise StockResolutionError('输入过于宽泛，请提供公司名称、简称或代码。')
        matches = [row for row in catalog if any(len(alias) >= 2 and
                   (alias in meaningful or meaningful in alias) for alias in aliases(row))]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise StockResolutionError('名称对应多个候选，请用完整简称或证券代码选择，不会自动猜测。',
                                   [{k: x.get(k, '') for k in ('ts_code', 'name', 'fullname')} for x in matches])
    raise StockResolutionError('未匹配到当前A股证券。请检查名称或提供六位代码；港美股不在本脚本范围。')
