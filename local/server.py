import base64, io, json, secrets, threading, webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import pypdfium2
from analyzer import parse_pdf, analyze, marked_pdf, DEFAULTS

ROOT=Path(__file__).parent
PORT=8766
SESSIONS={}
LOCK=threading.Lock()

def settings_validate(value):
    out={**DEFAULTS,**{k:v for k,v in value.items() if k in DEFAULTS}}
    for key in ['early_start','swing_boundary','close_time']:
        if key=='close_time' and not out[key]:continue
        h,m=map(int,out[key].split(':'))
        if not (0<=h<24 and 0<=m<60):raise ValueError('Invalid rule time.')
    out['double_limit']=int(out['double_limit'])
    if not 0<=out['double_limit']<=100:raise ValueError('Double threshold must be 0–100.')
    return out

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,data,status=200,mime='application/json'):
        if isinstance(data,(dict,list)):data=json.dumps(data).encode()
        elif isinstance(data,str):data=data.encode()
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        try:
            u=urlparse(self.path);q=parse_qs(u.query)
            if u.path=='/health':return self.respond({'app':'labor-card-review'})
            if u.path in ['/','/app.js','/style.css']:
                name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[u.path]
                mime={'index.html':'text/html; charset=utf-8','app.js':'text/javascript','style.css':'text/css'}[name]
                return self.respond((ROOT/name).read_bytes(),mime=mime)
            session=SESSIONS.get(q.get('session',[''])[0])
            if not session:return self.respond({'error':'This review session is no longer available. Upload the files again.'},404)
            if u.path=='/preview':
                di=int(q.get('doc',['0'])[0]);pi=int(q.get('page',['0'])[0])
                pdf=pypdfium2.PdfDocument(session['docs'][di]['data']);page=pdf[pi];image=page.render(scale=1.6).to_pil();b=io.BytesIO();image.save(b,format='PNG');page.close();pdf.close();return self.respond(b.getvalue(),mime='image/png')
            if u.path=='/export':
                data=marked_pdf(session['docs'],session['settings']);return self.respond(data,mime='application/pdf')
            return self.respond({'error':'Not found'},404)
        except Exception as e:return self.respond({'error':str(e)},400)
    def do_POST(self):
        # A separate website cannot silently submit local PDFs or alter a local review.
        if self.headers.get('Origin') not in [f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}']:
            return self.respond({'error':'Open this tool directly on localhost.'},403)
        try:
            size=int(self.headers.get('Content-Length',0))
            if size>70*1024*1024:return self.respond({'error':'Upload fewer files at a time (50 MB total PDF limit).'},413)
            body=json.loads(self.rfile.read(size));settings=settings_validate(body.get('settings',{}))
            if self.path in ['/analyze','/downloaded']:
                docs=[];errors=[]
                files=body.get('files',[])
                if self.path=='/downloaded':
                    import re
                    week=body.get('week','')
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',week):raise ValueError('Choose a Thursday date.')
                    folder=Path.home()/'Downloads'/'Labor Cards'/week
                    files=[{'name':p.name,'data':base64.b64encode(p.read_bytes()).decode()} for p in sorted(folder.glob('*.pdf'))]
                    if not files:raise ValueError('No downloaded PDFs found for that week. Run the Weekly Labor Cards extension first, or choose PDFs manually.')
                for f in files:
                    try:
                        data=base64.b64decode(f['data'],validate=True)
                        if not data.startswith(b'%PDF'):raise ValueError('This file is not a PDF.')
                        cards=parse_pdf(data,Path(f['name']).name)
                        docs.append({'name':Path(f['name']).name,'data':data,'cards':[analyze(c,settings) for c in cards]})
                    except Exception as e:errors.append({'file':f['name'],'error':str(e)})
                if not docs:return self.respond({'error':'No labor cards could be analyzed. '+('; '.join(e['file']+': '+e['error'] for e in errors))},400)
                token=secrets.token_urlsafe(24)
                with LOCK:
                    if len(SESSIONS)>15:SESSIONS.pop(next(iter(SESSIONS)))
                    SESSIONS[token]={'docs':docs,'settings':settings,'errors':errors}
                return self.respond({'session':token,'documents':[{'name':d['name'],'cards':d['cards']} for d in docs],'errors':errors})
            if self.path=='/review':
                session=SESSIONS.get(body.get('session'))
                if not session:raise ValueError('Session expired. Upload again.')
                for edit in body.get('edits',[]):
                    card=session['docs'][int(edit['doc'])]['cards'][int(edit['card'])]
                    row=next(r for r in card['rows'] if r['id']==edit['id'])
                    for k in ['name','role','location','in','out']:
                        if k in edit:row[k]=str(edit[k])[:200]
                for doc in session['docs']:
                    for card in doc['cards']:analyze(card,settings)
                session['settings']=settings
                return self.respond({'session':body['session'],'documents':[{'name':d['name'],'cards':d['cards']} for d in session['docs']],'errors':session['errors']})
            return self.respond({'error':'Not found'},404)
        except Exception as e:return self.respond({'error':str(e)},400)

if __name__=='__main__':
    import sys
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    if '--open' in sys.argv:threading.Timer(.5,lambda:webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
    server.serve_forever()
