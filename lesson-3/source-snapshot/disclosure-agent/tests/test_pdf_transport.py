import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from disclosure_agent import market


@pytest.mark.parametrize('failures,expected_calls',[(2,3),(3,3)])
def test_pdf_transport_retry_is_bounded_and_each_attempt_is_retained(tmp_path,monkeypatch,failures,expected_calls):
    calls=[]
    class Source:
        def __init__(self,*args):self.session=SimpleNamespace(close=lambda:None)
        def _pdf(self,row,identity,evidence):
            calls.append(row['announcementId'])
            if len(calls)<=failures:raise requests.exceptions.SSLError('synthetic TLS EOF')
            pdf=tmp_path/'synthetic.pdf';pdf.write_bytes(b'explicit test source')
            pdf.with_suffix('.pages.json').write_text(json.dumps(['synthetic page']))
            return {'id':'101','pdf_path':str(pdf),'pdf_sha256':market.digest(pdf),'pages':['synthetic page']}
    monkeypatch.setattr(market,'CninfoSource',Source);monkeypatch.setattr(market.time,'sleep',lambda _:None)
    row={'announcementId':'101','secCode':'111111','adjunctUrl':'finalpage/2030-10-30/101.PDF'}
    if failures==3:
        with pytest.raises(requests.exceptions.SSLError):market._fetch(row,{},tmp_path,tmp_path/'run')
    else:
        assert market._fetch(row,{},tmp_path,tmp_path/'run')['pages']==['synthetic page']
    assert len(calls)==expected_calls
    receipts=[json.loads(p.read_text()) for p in (tmp_path/'run/source/pdf-attempts/101').glob('*.json')]
    assert len(receipts)==3
    assert sum(r['status']=='failed' for r in receipts)==failures


@pytest.mark.parametrize('error',[ValueError('synthetic PDF has no readable text'),requests.HTTPError('synthetic rate limit')])
def test_invalid_pdf_and_http_failures_are_not_transport_retried(tmp_path,monkeypatch,error):
    calls=[]
    class Source:
        def __init__(self,*args):self.session=SimpleNamespace(close=lambda:None)
        def _pdf(self,*args):calls.append(1);raise error
    monkeypatch.setattr(market,'CninfoSource',Source);monkeypatch.setattr(market.time,'sleep',lambda _:None)
    with pytest.raises(type(error)):market._fetch({'announcementId':'101','secCode':'111111','adjunctUrl':'finalpage/test.PDF'},{},tmp_path,tmp_path/'run')
    assert len(calls)==1
