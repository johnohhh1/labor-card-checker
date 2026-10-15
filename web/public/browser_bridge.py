import sys,types,json,base64
# Only the unused native image renderer is replaced. PDF parsing uses pdfminer.
sys.modules['pypdfium2']=types.ModuleType('pypdfium2')
from analyzer import parse_pdf,analyze,marked_pdf,DEFAULTS
documents=[]
errors=[]

def response():
    return json.dumps({'session':'browser','documents':[{'name':d['name'],'cards':d['cards']} for d in documents],'errors':errors})

def execute(payload):
    global documents,errors
    body=json.loads(payload);settings={**DEFAULTS,**body.get('settings',{})}
    action=body['action']
    if action=='analyze':
        documents=[];errors=[]
        for f in body['files']:
            try:
                data=base64.b64decode(f['data'],validate=True)
                if not data.startswith(b'%PDF'):raise ValueError('This file is not a PDF.')
                cards=parse_pdf(data,f['name'])
                documents.append({'name':f['name'],'data':data,'cards':[analyze(c,settings) for c in cards]})
            except Exception as e:errors.append({'file':f['name'],'error':str(e)})
        if not documents:raise ValueError('No labor cards could be analyzed. '+'; '.join(e['file']+': '+e['error'] for e in errors))
    elif action=='review':
        for edit in body.get('edits',[]):
            card=documents[int(edit['doc'])]['cards'][int(edit['card'])]
            row=next(r for r in card['rows'] if r['id']==edit['id'])
            for key in ['name','role','location','in','out']:
                if key in edit:row[key]=str(edit[key])[:200]
        for doc in documents:
            for card in doc['cards']:analyze(card,settings)
    elif action=='export':
        return base64.b64encode(marked_pdf(documents,settings)).decode()
    else:raise ValueError('Unknown review action.')
    return response()
