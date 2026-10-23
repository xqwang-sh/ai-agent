"""Invented company and numbers only. No real report answer or page selection."""
from copy import deepcopy
from pathlib import Path

COMPANY = '合成测试股份有限公司'
METRICS = ['revenue', 'operating_cost', 'operating_profit', 'parent_net_profit', 'basic_eps']
LABELS = ['营业收入', '营业成本', '营业利润', '归属于母公司股东的净利润', '基本每股收益']
VALUES = [('110', '100'), ('66', '60'), ('20', '18'), ('11', '10'), ('0.83', '0.75')]
TEXT = '\n'.join([COMPANY, '合并利润表', '2026年1-6月', '2025年1-6月', '单位：万元',
    *[f'{label} {a} {b}' for label, (a,b) in zip(LABELS, VALUES)],
    '基本每股收益(人民币元)', '营业总收入 120 115', '营业总成本 90 80',
    '公司利润表', '2026年4-6月', '2025年4-6月', '附录联系人：另一家公司'])
PAGES = [{'physical_page': 1, 'text': TEXT}]

def observation():
    return {'company': COMPANY, 'scope': 'consolidated', 'current_period': '2026H1', 'prior_period': '2025H1',
        'scope_evidence': {'page':1, 'quote':'合并利润表'},
        'current_column_path':['2026年1-6月'], 'prior_column_path':['2025年1-6月'],
        'current_column_evidence':[{'page':1, 'quote':'2026年1-6月'}],
        'prior_column_evidence':[{'page':1, 'quote':'2025年1-6月'}],
        'rows':[{'metric':m,'original_label':label,'current':a,'prior':b,
                 'unit':'元/股' if m=='basic_eps' else '万元','value_page':1,'unit_page':1,
                 'unit_quote':'基本每股收益(人民币元)' if m=='basic_eps' else '单位：万元'}
                for m,label,(a,b) in zip(METRICS,LABELS,VALUES)]}

def swapped():
    value = observation()
    for row in value['rows']:
        row['current'], row['prior'] = row['prior'], row['current']
    return value

def selection():
    return {'status':'located','pages':[1],'anchors':[{'page':1,'quote':'合并利润表','purpose':'statement'}], 'reason':'synthetic fixture'}

def reference():
    # This normalized transport fixture must pass through the production H1 parser.
    fields=['operating_income','operating_costs','operating_profit','parent_holder_net_profit','basic_eps']
    return {'synthetic':True, 'thscode':'000001.SZ', 'records':[
        {'year':year,'fiscal_period':'Q2','period_end':f'{year}-06-30','currency':'CNY','cumulative':True,
         **{f:str(__import__('decimal').Decimal(v[i])*(1 if f=='basic_eps' else 10000)) for f,v in zip(fields,VALUES)}}
        for i,year in enumerate((2026,2025))]}

def income_envelope(normalized):
    """Public CLI success envelope; Q2 is a reporting window, not an invented bool."""
    if 'records' not in normalized:return deepcopy(normalized)
    from datetime import datetime, timezone
    from decimal import Decimal
    items=[]
    for row in normalized['records']:
        end=datetime.fromisoformat(row['period_end']).replace(tzinfo=timezone.utc)
        values={key:(int(Decimal(str(value))) if Decimal(str(value))==Decimal(str(value)).to_integral() else float(value))
                for key,value in row.items() if key in ('operating_income','operating_costs','operating_profit','parent_holder_net_profit','basic_eps')}
        items.append({'thscode':row.get('thscode',normalized['thscode']),'ticker':row.get('thscode',normalized['thscode']).split('.')[0],
                      'period':'quarterly','period_end_ms':int(end.timestamp()*1000),'report_date_ms':int(end.timestamp()*1000)+86400000,
                      'fiscal_year':row['year'],'fiscal_period':row['fiscal_period'],'currency':row['currency'],**values})
    return {'ok':True,'command':'financials.income','data':{'timestamp':1782781200000,'item':items},
            'meta':{'source':'remote','requestId':'synthetic-reference','count':len(items),'truncated':False,'schemaVersion':'1'}}

def mixed_reference_envelope():
    from datetime import datetime, timezone
    result=income_envelope(reference())
    targets={item['fiscal_year']:deepcopy(item) for item in result['data']['item']}
    items=[]
    for year,quarter,month,day in [(2026,'Q2',6,30),(2026,'Q1',3,31),
            (2025,'Q4',12,31),(2025,'Q3',9,30),(2025,'Q2',6,30),
            (2025,'Q1',3,31),(2024,'Q4',12,31),(2024,'Q3',9,30)]:
        item=deepcopy(targets.get(year,targets[2025]))
        timestamp=int(datetime(year,month,day,tzinfo=timezone.utc).timestamp()*1000)
        item.update(fiscal_year=year,fiscal_period=quarter,period_end_ms=timestamp,report_date_ms=timestamp+86400000)
        items.append(item)
    result['data']['item']=items;result['meta']['count']=len(items)
    return result

def joint_statement_case(title='合并及公司利润表', columns='consolidated'):
    pages=deepcopy(PAGES);value=observation()
    pages[0]['text']=pages[0]['text'].replace('合并利润表',title)
    pages[0]['text']+='\n合并\n公司\n母公司\n2026年1-6月 合并\n2025年1-6月 合并'
    value['scope_evidence']['quote']=title
    if columns!='ambiguous':
        column='合并' if columns=='consolidated' else '公司'
        for side in ('current','prior'):
            value[side+'_column_path'].append(column)
            value[side+'_column_evidence'].append({'page':1,'quote':column})
    return pages,value

def alternate():
    value = observation()
    value['scope_evidence']['page'] = 2
    for key in ('current_column_evidence', 'prior_column_evidence'):
        for item in value[key]: item['page'] = 2
    for row in value['rows']:
        row['value_page'] = row['unit_page'] = 2
        if row['metric'] == 'revenue': row['current'] = '111'
        if row['metric'] == 'basic_eps': row['current'] = '0.84'
    return value

ALT_TEXT = TEXT.replace('营业收入 110 100','营业收入 111 100').replace('0.83 0.75','0.84 0.75')
RUN_PAGES = PAGES + [{'physical_page':2, 'text':ALT_TEXT}]

def run_selection():
    return {'status':'located','pages':[1,2], 'anchors':[
        {'page':p,'quote':'合并利润表','purpose':'statement'} for p in (1,2)],'reason':'two invented source tables for continuation tests'}

def alternate_reference():
    result = reference()
    result['records'][0]['operating_income']='1110000'
    result['records'][0]['basic_eps']='0.84'
    return result

def script(kind):
    good, revised = observation(), alternate()
    seq = [dict(stage='locate', response={'action':'search_fulltext','query':'合并利润表','offset':0}),
           dict(stage='locate', response={'action':'read_pages','pages':[1,2]}),
           dict(stage='locate', response={'action':'select_pages','selection':run_selection()}),
           dict(stage='extract', response={'action':'submit','observation':good}),
           dict(stage='vision', response=revised if kind=='vision_revision' else good)]
    if kind=='vision_self_repair':
        invalid=deepcopy(good);invalid['rows'][-1]['unit_quote']='没有这段单位'
        seq[-1]['response']=invalid
        seq.append(dict(stage='vision',response=good))
    refs = [reference()]
    if kind in ('vision_revision','external_revision'):
        seq.extend([dict(stage='extract',response={'action':'search_fulltext','query':'基本每股收益','offset':0}),
                    dict(stage='extract',response={'action':'read_pages','pages':[1,2]}),
                    dict(stage='extract',response={'action':'submit','observation':revised}),
                    dict(stage='vision',response=revised)])
        refs = [alternate_reference()] * (2 if kind=='external_revision' else 1)
    for i,item in enumerate(seq):
        item.update(id=f'synthetic-{i+1}', usage={'prompt_tokens':100,'completion_tokens':10,'total_tokens':110})
    return {'label':'synthetic only','company':{'company':COMPANY,'thscode':'000001.SZ','identity_confirmed':True},
            'model_script':seq,'reference_script':refs,'preset':'qwen27'}

def write_pdf(path, texts=None):
    # A real two-page Unicode PDF, rendered from the same bytes in acceptance.
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, ArrayObject, NumberObject, DecodedStreamObject
    writer=PdfWriter()
    cid=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/CIDFontType0'),
        NameObject('/BaseFont'):NameObject('/STSong-Light'),NameObject('/CIDSystemInfo'):DictionaryObject({
        NameObject('/Registry'):__import__('pypdf').generic.TextStringObject('Adobe'),
        NameObject('/Ordering'):__import__('pypdf').generic.TextStringObject('GB1'),NameObject('/Supplement'):NumberObject(4)})})
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type0'),
        NameObject('/BaseFont'):NameObject('/STSong-Light'),NameObject('/Encoding'):NameObject('/UniGB-UCS2-H'),
        NameObject('/DescendantFonts'):ArrayObject([writer._add_object(cid)])})
    font_ref=writer._add_object(font)
    for text in ((TEXT,ALT_TEXT) if texts is None else texts):
        page=writer.add_blank_page(width=595,height=842)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font_ref})})
        lines=['BT /F1 12 Tf 40 800 Td 20 TL']
        for i,line in enumerate(text.splitlines()):
            if i:lines.append('T*')
            lines.append('<'+line.encode('utf-16-be').hex()+'> Tj')
        lines.append('ET'); stream=DecodedStreamObject(); stream.set_data('\n'.join(lines).encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    with Path(path).open('wb') as f:writer.write(f)
