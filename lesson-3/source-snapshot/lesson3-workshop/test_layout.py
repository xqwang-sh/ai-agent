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

def test_lesson_shows_product_before_preparation_and_building():
    html=render((ROOT/'lesson.md').read_text());reader=Images();reader.feed(html)
    images={'assets/product-preview.png','assets/event-detail-preview.png','assets/watchlist-preview.png'}
    assert images <= {src for step,src in reader.images if step is None}
    assert html.index('id="product-showcase"') < html.index('id="readiness"') < html.index('id="step-0"')
    assert all(html.index('id="product-showcase"') < html.index('src="'+src+'"') < html.index('id="readiness"') for src in images)
    assert all(html.count('src="'+src+'"')==1 for src in images)
    assert '伊利参与方式实拍' in html and '手机宽度的日历' in html and '手机宽度的完整参与方式' in html
    assert 'href="#product-showcase"' in html

def test_unknown_step_section_cannot_disappear():
    source=(ROOT/'lesson.md').read_text().replace('### 现在怎么做','### 未登记的展示内容',1)
    with pytest.raises(ValueError,match='未登记的展示内容'):render(source)
