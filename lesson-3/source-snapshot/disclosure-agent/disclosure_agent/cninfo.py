"""CNInfo identity, query coverage and immutable source evidence."""
from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from pypdf import PdfReader
from .scope import title_outside_scope, source_period

STOCK_URL = 'https://www.cninfo.com.cn/new/data/szse_stock.json'
QUERY_URL = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
STATIC_URL = 'https://static.cninfo.com.cn/'
MAX_PAGES = 100
MAX_PDF_BYTES = 8 * 1024 * 1024
MIN_PDF_BYTES = 64


class CninfoSource:
    def __init__(self, workspace: Path, run_dir: Path, timeout: int = 25):
        self.workspace = Path(workspace).resolve()
        self.run_dir = Path(run_dir).resolve()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'})

    def _json(self, method: str, url: str, archive: Path, params: dict | None = None):
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.with_suffix('.request.json').write_text(json.dumps(
            {'method': method, 'url': url, 'params': params}, ensure_ascii=False, indent=2), encoding='utf-8')
        response = self.session.request(method, url, data=params, timeout=self.timeout)
        raw = response.content
        archive.write_bytes(raw)
        archive.with_suffix('.response.json').write_text(json.dumps({
            'status_code': response.status_code,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'retrieved_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'retry_after': getattr(response, 'headers', {}).get('Retry-After'),
        }), encoding='utf-8')
        response.raise_for_status()
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError('JSON response exceeds size limit')
        return json.loads(raw)

    def _pdf(self, row: dict, company: dict, evidence: Path) -> dict:
        source_id = str(row['announcementId'])
        if not re.fullmatch(r'\d+', source_id):
            raise ValueError('Invalid announcement ID')
        pdf_url = urljoin(STATIC_URL, row['adjunctUrl'])
        parsed = urlparse(pdf_url)
        if parsed.scheme != 'https' or parsed.hostname != 'static.cninfo.com.cn':
            raise ValueError('Unexpected PDF host')
        response = self.session.get(pdf_url, timeout=self.timeout, stream=True)
        content = bytearray()
        try:
            response.raise_for_status()
            length = response.headers.get('Content-Length')
            if length and int(length) > MAX_PDF_BYTES:
                raise ValueError('PDF exceeds size limit')
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > MAX_PDF_BYTES:
                    raise ValueError('PDF exceeds size limit')
        finally:
            response.close()
        raw = bytes(content)
        sha = hashlib.sha256(raw).hexdigest()
        evidence.mkdir(parents=True, exist_ok=True)
        # Invalid responses are evidence too, but never published as a PDF.
        (evidence / f'{source_id}-{sha}.response.bin').write_bytes(raw)
        if len(raw) < MIN_PDF_BYTES or not raw.startswith(b'%PDF-'):
            raise ValueError('Response is not a valid-sized PDF')
        pages = [page.extract_text(extraction_mode='layout') or '' for page in PdfReader(io.BytesIO(raw)).pages]
        if not pages or not any(text.strip() for text in pages):
            raise ValueError('PDF has no extractable page text')
        raw_dir = self.workspace / 'raw'
        raw_dir.mkdir(parents=True, exist_ok=True)
        target = raw_dir / f'{source_id}-{sha}.pdf'
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(raw)
        elif hashlib.sha256(target.read_bytes()).hexdigest() != sha:
            raise ValueError('Existing source archive hash mismatch')
        text_path = raw_dir / f'{source_id}-{sha}.pages.json'
        if not text_path.exists():
            with text_path.open('x', encoding='utf-8') as stream:
                json.dump(pages, stream, ensure_ascii=False, indent=2)
        published = datetime.fromtimestamp(int(row['announcementTime']) / 1000, ZoneInfo('Asia/Shanghai')).date().isoformat()
        return {'id': source_id, 'stock_code': company['code'], 'company': company['name'],
                'org_id': company['org_id'], 'title': re.sub('<[^>]+>', '', row['announcementTitle']),
                'publication_date': published, 'pdf_url': pdf_url, 'url': pdf_url,
                'pdf_sha256': sha, 'pdf_path': str(target), 'pages': pages}

    def acquire(self, company: dict, start_date: str, end_date: str, report_period: str | None = None) -> dict:
        code = str(company['code'])
        result = {'company': {'code': code, 'name': company['name'], 'org_id': None},
                  'status': 'failed', 'query_complete': False, 'items': [], 'failed_items': [],
                  'error': None, 'excluded_items': [], 'query': {'start_date': start_date, 'end_date': end_date,
                                         'keyword': '业绩说明会', 'pages': []}}
        evidence = self.run_dir / 'source' / code
        if evidence.exists():
            evidence = evidence / f'attempt-{uuid.uuid4().hex[:12]}'
        rows = []
        errors = []
        try:
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')
            if start_date > end_date or not re.fullmatch(r'\d{6}', code):
                raise ValueError('Invalid company/date query')
            table = self._json('GET', STOCK_URL, evidence / 'company-table.json')
            stocks = table.get('stockList') if isinstance(table, dict) else None
            if not isinstance(stocks, list):
                raise ValueError('Invalid company table structure')
            matches = [row for row in stocks if str(row.get('code')) == code]
            if len(matches) != 1 or not matches[0].get('orgId') or not matches[0].get('zwjc'):
                raise ValueError('Company code does not resolve uniquely')
            identity = matches[0]
            if company['name'] not in identity['zwjc']:
                raise ValueError('Company name does not match live company identity')
            result['company'] = {'code': code, 'name': identity['zwjc'], 'org_id': identity['orgId']}
            seen = set()
            expected_total = None
            for page in range(1, MAX_PAGES + 1):
                params = {'pageNum': str(page), 'pageSize': '30', 'column': 'szse', 'tabName': 'fulltext',
                          'plate': '', 'stock': f"{code},{identity['orgId']}", 'searchkey': '业绩说明会',
                          'secid': '', 'category': '', 'trade': '', 'seDate': f'{start_date}~{end_date}',
                          'sortName': 'time', 'sortType': 'asc', 'isHLtitle': 'false'}
                payload = self._json('POST', QUERY_URL, evidence / f'query-{page:03d}.json', params)
                if not isinstance(payload, dict) or type(payload.get('hasMore')) is not bool or type(payload.get('totalAnnouncement')) is not int:
                    raise ValueError('Invalid announcement response structure')
                total = payload['totalAnnouncement']
                announcements = payload.get('announcements')
                if announcements is None and total == 0:
                    announcements = []
                if total < 0 or not isinstance(announcements, list):
                    raise ValueError('Invalid announcement list/count')
                if expected_total is None:
                    expected_total = total
                elif total != expected_total:
                    raise ValueError('Announcement count changed during pagination; retry required')
                result['query']['pages'].append({'page': page, 'count': len(announcements), 'has_more': payload['hasMore'], 'total': total})
                before = len(seen)
                for row in announcements:
                    if not isinstance(row, dict) or str(row.get('secCode')) != code or row.get('orgId') != identity['orgId']:
                        raise ValueError('Announcement company identity mismatch')
                    notice_id = str(row.get('announcementId'))
                    if notice_id not in seen:
                        seen.add(notice_id)
                        rows.append(row)
                if not payload['hasMore']:
                    if len(seen) != total:
                        raise ValueError('Final page count does not match totalAnnouncement')
                    result['query_complete'] = True
                    break
                if len(seen) == before:
                    raise ValueError('Pagination made no progress')
            else:
                raise ValueError('Announcement pagination exceeded page limit')
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
        # A failed later page must not discard already retrieved announcements.
        for row in rows:
            title = re.sub('<[^>]+>', '', row['announcementTitle'])
            if title_outside_scope(title, report_period):
                result['excluded_items'].append({'id': str(row['announcementId']), 'title': title,
                                                'report_period': source_period(title), 'reason': 'outside_report_period'})
                continue
            try:
                result['items'].append(self._pdf(row, result['company'], evidence / 'downloads'))
            except Exception as exc:
                failure = {'id': str(row.get('announcementId')), 'error': f'{type(exc).__name__}: {exc}'}
                result['failed_items'].append(failure)
        if result['failed_items']:
            errors.append(f"{len(result['failed_items'])} PDF download/validation failures")
        result['status'] = 'complete' if result['query_complete'] and not errors else 'failed'
        result['error'] = '; '.join(errors) or None
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / 'acquisition.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result
