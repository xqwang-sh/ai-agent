from pathlib import Path
from html.parser import HTMLParser
import pytest
from layout import render

ROOT=Path(__file__).resolve().parent

class Images(HTMLParser):
    def __init__(self):
        super().__init__();self.images=[];self.step=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='section' and attrs.get('id','').startswith('step-'):self.step=attrs['id']
        if tag=='img':self.images.append((self.step,attrs.get('src')))

def test_lesson_keeps_calendar_showcase_in_step_seven():
    html=render((ROOT/'lesson.md').read_text());reader=Images();reader.feed(html)
    assert {'assets/product-preview.png','assets/event-detail-preview.png','assets/watchlist-preview.png'} <= {src for step,src in reader.images if step=='step-7'}
    assert '伊利参与方式实拍' in html and '手机宽度的日历' in html and '手机宽度的完整参与方式' in html
    assert '先看展示产品' not in html

def test_unknown_step_section_cannot_disappear():
    source=(ROOT/'lesson.md').read_text().replace('### 这一阶段要交付的日历产品','### 未登记的展示内容')
    with pytest.raises(ValueError,match='未登记的展示内容'):render(source)
