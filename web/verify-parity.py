import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent/'local'))
from analyzer import parse_pdf,analyze,DEFAULTS
from pypdf import PdfReader
root=Path(__file__).parent
def same(a,b,where=''):
    if isinstance(a,(float,int)) and isinstance(b,(float,int)):
        assert abs(a-b)<1e-7,(where,a,b)
    elif isinstance(a,dict):
        assert a.keys()==b.keys(),where
        for key in a:same(a[key],b[key],where+'/'+key)
    elif isinstance(a,(list,tuple)):
        assert len(a)==len(b),(where,len(a),len(b))
        for i,(x,y) in enumerate(zip(a,b)):same(x,y,where+'/'+str(i))
    else:assert a==b,(where,a,b)
result=json.loads((root/'browser-test-results.json').read_text(encoding='utf-8'))
for doc in result['documents']:
    source=Path(os.environ['LABOR_CARD_FIXTURES'])/doc['name']
    native=[analyze(card,DEFAULTS) for card in parse_pdf(source.read_bytes(),doc['name'])]
    same(native,doc['cards'],doc['name'])
pdf=PdfReader(root/'browser-test-export.pdf')
assert len(pdf.pages)>=14
assert 'Passed:' in ''.join(page.extract_text() for page in pdf.pages)
print('All seven browser reviews exactly match the local parser and rules. Export contains originals and passed checks:',len(pdf.pages),'pages.')
