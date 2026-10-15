import io, re, collections, datetime
import pdfplumber
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight, Text
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit

ROLES = ['Bar','Bus','Delivery','Dish','Food Runner','Host','Kitchen','Manager','Marketing','Meetings','Night Cleaner','QA','Server','Shift Leader','Silverware','To Go','Training']
DEFAULTS = {'early_start':'10:30','close_time':'','double_limit':5,'swing_boundary':'16:00','hosts':True,'locations':True,'sections':True,'open_close':True,'early':True,'doubles':True,'house':True,'swing':True}
DEFAULTS.update(host_coverage=True,cook_close=True,z3_rover=True)

def person_key(row):
    return re.sub(r'\[[^]]*\]','',row['name']).strip().casefold()

def assigned_people(rows):
    return [r for r in rows if person_key(r) and not re.search(r'\bhouse\b',r['name'],re.I)]

def cook_deadline(card):
    try:day=datetime.datetime.strptime(card['date'],'%B %d, %Y').weekday()
    except (ValueError,KeyError):return None
    return 1500 if day in (4,5) else 1440

def pm_z3(rows):
    return assigned_people([r for r in rows if r['role'].strip().casefold()=='kitchen' and r['period']=='PM' and re.match(r'^Z\s*3\b',r['location'].strip(),re.I)])
TIME = re.compile(r'(\d{1,2}:\d{2})\s*([AP]M)',re.I)

def minutes(value):
    m=TIME.fullmatch(value.strip())
    if not m: raise ValueError('Use a time such as 4:00 PM.')
    h,n=map(int,m[1].split(':'))
    if not 1<=h<=12 or not 0<=n<60: raise ValueError('Invalid shift time.')
    return (h%12+(12 if m[2].upper()=='PM' else 0))*60+n

def clock(n):
    n%=1440
    return f'{(n//60)%12 or 12}:{n%60:02d} '+('PM' if n>=720 else 'AM')

def service_times(in_time,out_time):
    """Restaurant service day: after-midnight times follow the evening shift."""
    start=minutes(in_time)
    if start<240:start+=1440
    end=minutes(out_time)
    while end<=start:end+=1440
    return start,end

def text(chars):
    if not chars:return ''
    return pdfplumber.utils.extract_text(chars,x_tolerance=0.8,y_tolerance=0.6).strip()

def parse_pdf(data,filename):
    cards=[]
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for pi,p in enumerate(pdf.pages):
            raw=p.extract_text(x_tolerance=1,y_tolerance=0.6) or ''
            if 'Labor Card for' not in raw:continue
            title=re.search(r'Labor Card for\s+([^\n]+)',raw)
            service_text='\n'.join(line for line in raw.splitlines() if 'Generated On' not in line)
            dm=re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})',service_text)
            date=dm[2] if dm else 'Date needs review'
            card={'page':pi,'filename':filename,'date':date,'restaurant':title[1].strip() if title else 'Unknown restaurant','width':float(p.width),'height':float(p.height),'rows':[],'warnings':[]}
            if any((im['x1']-im['x0'])*(im['bottom']-im['top'])>p.width*p.height*.5 for im in p.images):
                card['warnings'].append('This is a scanned or image-based card. Upload an original downloaded Labor Card PDF. The roster has not been automatically reviewed.')
                cards.append(card);continue
            words=p.extract_words(x_tolerance=1,y_tolerance=0.6)
            pair=None
            for a in words:
                if a['text']=='AM' and a['x0']>p.width*.4:
                    b=next((b for b in words if b['text']=='PM' and b['x0']>a['x0']+p.width*.1 and abs(b['top']-a['top'])<.8),None)
                    if b:pair=(a,b);break
            if not pair:
                card['warnings'].append('Cannot reliably read the AM/PM roster. Use an original HotSchedules PDF, not a scanned or marked-up copy. No automatic checks were completed.')
                cards.append(card);continue
            a,b=pair
            ac=(a['x0']+a['x1'])/2;bc=(b['x0']+b['x1'])/2;mid=(ac+bc)/2
            left=max(0,ac-(bc-ac)/2-3);right=min(p.width,bc+(bc-ac)/2+3)
            stop=next((w['top'] for w in words if w['text']=='Weekly' and w['top']>a['top']),p.height)
            borders=[e['x0'] for e in p.edges if e.get('orientation')=='v' and e.get('height',0)>100 and p.width*.4<e['x0']<ac]
            if borders:left=max(borders)
            headings=[w['x0'] for w in words if w['text'] in ['Kitchen','Server','Bar','Dish','Host','QA','Bus'] and mid<w['x0']<bc-15 and a['bottom']<w['top']<stop]
            if headings:mid=min(headings)-7
            right=p.width
            for period,x0,x1 in [('AM',left,mid),('PM',mid,right)]:
                chars=[c for c in p.chars if x0<=c['x0']<x1 and a['bottom']<c['top']<stop]
                groups=[]
                for c in sorted(chars,key=lambda c:c['top']):
                    if not groups or abs(c['top']-groups[-1][0]['top'])>.8:groups.append([c])
                    else:groups[-1].append(c)
                # Location columns have a consistent left edge in original labor-card PDFs.
                candidates=[]
                for g in groups:
                    s=text(g)
                    if len(TIME.findall(s))!=2:continue
                    ws=pdfplumber.utils.extract_words(g,x_tolerance=.8,y_tolerance=.6)
                    for w in ws:
                        if re.match(r'^(SECTION|LOUNGE|LEADER|GREETER|SEATER|PREP|Z[123]|BAR|WELL|ASSEMBLER|REGISTER|FOOD|DRINK|BUS|ROVER|QA|JANITORIAL|HOH|DISH|CLOSER)',w['text'],re.I) and w['x0']>x0+(x1-x0)*.2:
                            candidates.append(round(w['x0'],1));break
                loc=collections.Counter(candidates).most_common(1)[0][0] if candidates else x0+(x1-x0)*.4
                role=None
                for g in groups:
                    s=text(g).replace('\n',' ')
                    if s in ROLES:role=s;continue
                    matches=list(TIME.finditer(s))
                    if not matches:
                        if role and s.strip() and s not in ['AM','PM']:
                            card['warnings'].append(f'{period}: unrecognized roster line under {role}: {s}. Verify this line manually.')
                        continue
                    if len(matches)!=2 or not role:
                        card['warnings'].append(f'{period}: could not read roster row: {s}.');continue
                    # Identify the first time's position from the characters, avoiding location text touching times.
                    timewords=pdfplumber.utils.extract_words(g,x_tolerance=.8,y_tolerance=.6)
                    tw=next((w for w in timewords if re.match(r'^\d{1,2}:\d{2}',w['text'])),None)
                    if not tw:
                        card['warnings'].append(f'{period}: could not separate shift times: {s}.');continue
                    startx=tw['x0']
                    name=text([c for c in g if c['x0']<loc-.6]).replace('\n',' ')
                    location=text([c for c in g if loc-.6<=c['x0']<startx-.2]).replace('\n',' ')
                    in_time=matches[0][0];out_time=matches[1][0]
                    try:st,en=service_times(in_time,out_time)
                    except ValueError:
                        card['warnings'].append(f'Invalid times: {s}');continue
                    row={'id':f'{pi}-{period}-{len(card["rows"])}','name':name,'role':role,'location':location,'period':period,'in':in_time,'out':out_time,'start':st,'end':en,'double':bool(re.search(r'\[D\]',name,re.I)),'rect':[float(min(c['x0'] for c in g)),float(min(c['top'] for c in g)),float(max(c['x1'] for c in g)),float(max(c['bottom'] for c in g))]}
                    if not name:card['warnings'].append(f'An unnamed {role} row needs review.')
                    card['rows'].append(row)
            if not card['rows']:card['warnings'].append('No roster rows were read. This card has not passed review.')
            if not dm:card['warnings'].append('The service date could not be read. Verify the date.')
            cards.append(card)
    if not cards:raise ValueError('No readable labor card found. Upload a daily Labor Card PDF, not an Employee Hours or sales report.')
    return cards

def analyze(card,settings=None):
    s={**DEFAULTS,**(settings or {})};findings=[];rows=card['rows']
    def add(rule,message,rr=(),level='fix'):
        findings.append({'rule':rule,'message':message,'rows':[r['id'] for r in rr],'level':level})
    for w in card.get('warnings',[]):add('Reading check',w,level='review')
    for r in rows:
        r['start'],r['end']=service_times(r['in'],r['out'])
        loc=r['location'].strip().upper()
        if s['locations'] and r['role'].strip().casefold()!='manager' and not loc:add('Blank location',f'{r["period"]} · {r["name"]} ({r["role"]}), {r["in"]}–{r["out"]}: assign a location.',[r])
        if s['house'] and re.search(r'\bHOUSE\b',r['name'],re.I):add('House shift',f'{r["period"]} · {r["role"]}: House Shift found. Review this unassigned or leftover shift; the store is fully staffed.',[r])
        if s['early'] and r['role'] in ['Bar','To Go']:
            hh,mm=map(int,s['early_start'].split(':'));cut=hh*60+mm
            if r['start']<cut:add('Early start',f'{r["name"]} ({r["role"]}) starts at {r["in"]}; start no earlier than {clock(cut)}.',[r])
        if s['swing'] and r['role'].strip().casefold()!='manager' and r['period']=='AM':
            hh,mm=map(int,s['swing_boundary'].split(':'));cut=hh*60+mm
            if r['start']<cut<r['end'] and not re.search(r'\[D\]',r['name'],re.I):add('Swing shift',f'{r["name"]}: {r["in"]}–{r["out"]} spans the AM/PM boundary. Review and enter as a double under Cara’s guidance.',[r],level='review')
    if s['host_coverage']:
        for period,label in [('AM','Lunch'),('PM','Dinner')]:
            hosts=assigned_people([r for r in rows if r['role'].strip().casefold()=='host' and r['period']==period])
            if not hosts:add('Host coverage',f'{label} ({period}) has no named host scheduled. Schedule at least one host for this shift.',level='review' if card.get('warnings') else 'fix')
    if s['cook_close']:
        deadline=cook_deadline(card)
        if deadline is None:add('Closing cooks','Could not read the service date. Verify whether cooks must stay through midnight or 1:00 AM.',level='review')
        else:
            cooks=assigned_people([r for r in rows if r['role'].strip().casefold()=='kitchen'])
            closing=[r for r in cooks if r['start']<deadline<=r['end']]
            count=len({person_key(r) for r in closing})
            if count<3:add('Closing cooks',f'{count} distinct cooks are scheduled through {clock(deadline)} after this service day; at least 3 are required. Close is '+('midnight Friday/Saturday' if deadline==1500 else '11:00 PM Sunday–Thursday')+'.',[r for r in cooks if r['period']=='PM'],level='review' if card.get('warnings') else 'fix')
    if s['z3_rover']:
        z3=pm_z3(rows)
        if len({person_key(r) for r in z3})==1:
            for r in z3:
                if not re.fullmatch(r'Z\s*3\s*[-–—]\s*ROVER',r['location'].strip(),re.I):add('PM Z3-rover',f'{r["name"]} is the only PM Z3 cook and is assigned “{r["location"]}”. Assign Z3-rover.',[r])
    if s['sections']:
        for period in ['AM','PM']:
            servers=[r for r in rows if r['role']=='Server' and r['period']==period]
            for label,limit in [('SECTION',9),('LOUNGE',2)]:
                assigned=[]
                for r in servers:
                    m=re.fullmatch(label+r'\s*0*(\d+)',r['location'].strip(),re.I)
                    if m:assigned.append((int(m[1]),r))
                nums=sorted(set(n for n,r in assigned))
                expected=list(range(1,len(nums)+1))
                if nums and nums!=expected:add('Location sequence',f'{period} · {label.title()} assignments are {", ".join(map(str,nums))}; use {", ".join(map(str,expected))} consecutively.',[r for n,r in assigned])
                for n,r in assigned:
                    if not 1<=n<=limit:add('Invalid location',f'{r["name"]}: {label.title()} {n} is outside the allowed 1–{limit} range.',[r])
                for i,(n,r) in enumerate(assigned):
                    for m,q in assigned[i+1:]:
                        if n==m and max(r['start'],q['start'])<min(r['end'],q['end']):add('Duplicate location',f'{period} · {r["name"]} and {q["name"]} overlap in {label.title()} {n}.',[r,q])
            for r in servers:
                if r['location'].strip() and not re.fullmatch(r'(SECTION\s*0*\d+|LOUNGE\s*0*\d+)',r['location'].strip(),re.I):add('Invalid server location',f'{r["name"]}: “{r["location"]}” must be Section 1–9 or Lounge 1–2.',[r])
    if s['open_close']:
        servers=[r for r in rows if r['role']=='Server']
        for period in ['AM','PM']:
            # After-midnight arrivals belong to the preceding evening, never to opening.
            cohort=[r for r in servers if r['period']==period and r['start']<1440]
            if cohort:
                first=min(r['start'] for r in cohort);earliest=[r for r in cohort if r['start']==first]
                if not any(re.fullmatch(r'SECTION\s*0*1',r['location'],re.I) for r in earliest):add('Opening server',f'{period} · first server starts at {clock(first)}, but none of the first arrivals is assigned Section 1.',earliest)
        late=[r for r in servers if r['start']>=1440]
        for r in late:add('After-midnight start',f'{r["name"]} starts at {r["in"]} after the evening service. This is not an opening shift. Verify that the in-time is correct.',[r],level='review')
        if servers:
            if s['close_time']:
                hh,mm=map(int,s['close_time'].split(':'));close=hh*60+mm
                if close<240:close+=1440
                basis='your configured FOH close'
                for label,pat in [('Section 1',r'SECTION\s*0*1'),('Lounge',r'LOUNGE\s*0*\d+')]:
                    staff=[r for r in servers if re.fullmatch(pat,r['location'],re.I) and r['period']=='PM']
                    if not any(r['start']<close<=r['end'] for r in staff):add('Closing coverage',f'{label} does not cover {clock(close)} ({basis}). Verify closing coverage.',staff)
        else:add('Closing coverage','No servers were read. Opening and closing coverage could not be checked.',level='review')
    if s['hosts']:
        hosts=[r for r in rows if r['role']=='Host']
        points=sorted({n for r in hosts for n in (r['start'],r['end'])})
        problems=[]
        for a,b in zip(points,points[1:]):
            active=[r for r in hosts if r['start']<=a<r['end']]
            if len(active)<2:continue
            if len(active)==2:
                labels=[re.sub(r'\s+','',r['location']).upper() for r in active]
                # A valid three-position plan may have staggered arrivals/departures.
                # Do not demand combined labels during its two-person transition.
                roles={'LEADER','SEATER','GREETER'}
                if len(set(labels))==2 and set(labels)<=roles and active[0]['period']==active[1]['period']:
                    missing_role=next(iter(roles-set(labels)))
                    third=any(r not in active and r['period']==active[0]['period'] and r['location'].strip().upper()==missing_role and max(r['start'],*(q['start'] for q in active))<min(r['end'],*(q['end'] for q in active)) for r in hosts)
                    if third:continue
                valid='LEADER' in labels and any(label in ['SEATER/GREETER','GREETER/SEATER'] for label in labels)
                if not valid:
                    missing=['two-host assignments'];ids=tuple(sorted(r['id'] for r in active));key=(ids,tuple(missing))
                    if problems and problems[-1][2]==key and problems[-1][1]==a:problems[-1]=(problems[-1][0],b,key,active,missing)
                    else:problems.append((a,b,key,active,missing))
                continue
            # With 3+ hosts, three separate people must explicitly own the three positions.
            owned={role:[r for r in active if r['location'].strip().upper()==role] for role in ['LEADER','SEATER','GREETER']}
            missing=[role.title() for role,v in owned.items() if not v]
            if missing:
                ids=tuple(sorted(r['id'] for r in active));key=(ids,tuple(missing))
                if problems and problems[-1][2]==key and problems[-1][1]==a:problems[-1]=(problems[-1][0],b,key,active,missing)
                else:problems.append((a,b,key,active,missing))
        for a,b,key,active,missing in problems:
            if len(active)==2:
                assignments='; '.join(f'{r["name"]}: {r["location"] or "blank"}' for r in active)
                add('Host positions',f'{clock(a)}–{clock(b)} · two hosts overlap ({assignments}). Assign one host as Leader and the other as Seater/Greeter.',active)
            else:add('Host positions',f'{clock(a)}–{clock(b)} · {len(active)} hosts overlap. Assign separate Leader, Seater, and Greeter positions. Missing explicit assignment: {", ".join(missing)}.',active)
    if s['doubles']:
        names=collections.defaultdict(list)
        for r in rows:
            if r['role'].strip().casefold()=='manager':continue
            name=re.sub(r'\[[^]]*\]','',r['name']).strip().casefold()
            if name and not re.search(r'\bhouse\b',name):names[name].append(r)
        doubles=[rr for rr in names.values() if any(re.search(r'\[D\]',r['name'],re.I) for r in rr) or len({(r['start'],r['end']) for r in rr})>1]
        if len(doubles)>int(s['double_limit']):add('Doubles',f'{len(doubles)} people have doubles or multiple shifts; threshold is {s["double_limit"]}. Review the staffing plan and commitment date.',[r for rr in doubles for r in rr],level='review')
    card['findings']=findings
    card['server_count']=len({re.sub(r'\[[^]]*\]','',r['name']).strip().casefold() for r in rows if r['role']=='Server'})
    card['positives'],card['not_checked']=passed_checks(card,s,findings)
    return card

def passed_checks(card,s,findings):
    rows=card['rows'];passed=[];skipped=[]
    def good(rule,message):passed.append({'rule':rule,'message':message,'level':'pass'})
    def clean(*rules):return not any(f['rule'] in rules for f in findings)
    if card.get('warnings') or not rows:
        return [],['Reading warnings or missing roster rows prevent confirmed pass results. Verify the roster first.']
    staff=[r for r in rows if r['role'].strip().casefold()!='manager']
    if s['host_coverage'] and clean('Host coverage'):
        good('Lunch / dinner hosts','At least one named host is scheduled in both the AM lunch and PM dinner rosters.')
    if s['cook_close'] and clean('Closing cooks'):
        deadline=cook_deadline(card)
        if deadline is not None:
            count=len({person_key(r) for r in assigned_people(rows) if r['role'].strip().casefold()=='kitchen' and r['start']<deadline<=r['end']})
            good('Closing cooks',f'{count} distinct cooks are scheduled through {clock(deadline)} after this service day; at least 3 are required.')
    if s['z3_rover']:
        z3=pm_z3(rows)
        if len({person_key(r) for r in z3})==1 and clean('PM Z3-rover'):good('PM Z3-rover','The only PM Z3 cook is assigned Z3-rover.')
        elif not z3:skipped.append('PM Z3-rover: no assigned PM Z3 cooks were read.')
        elif len({person_key(r) for r in z3})>1:skipped.append('PM Z3-rover: multiple PM Z3 cooks are scheduled, so the single-cook rule does not apply.')
    if s['locations'] and staff and clean('Blank location'):
        good('Locations assigned',f'All {len(staff)} non-manager shift rows have locations. Managers are correctly exempt.')
    servers=[r for r in rows if r['role']=='Server']
    if s['sections'] and servers:
        if clean('Location sequence','Invalid location','Invalid server location','Duplicate location'):
            for period in ['AM','PM']:
                cohort=[r for r in servers if r['period']==period]
                if not cohort:continue
                parts=[]
                for label in ['SECTION','LOUNGE']:
                    nums=sorted({int(m[1]) for r in cohort if (m:=re.fullmatch(label+r'\s*0*(\d+)',r['location'].strip(),re.I))})
                    if nums:parts.append(label.title()+(' '+str(nums[0]) if len(nums)==1 else 's '+', '.join(map(str,nums))))
                if parts:good('Server assignments',f'{period}: {"; ".join(parts)}. Numbering is consecutive, with no overlapping duplicate assignments. Lounge staff count as servers.')
    elif s['sections']:skipped.append('Server location checks: no server rows were read.')
    if s['open_close']:
        if servers and clean('Opening server'):
            for period in ['AM','PM']:
                cohort=[r for r in servers if r['period']==period and r['start']<1440]
                if cohort:
                    first=min(r['start'] for r in cohort)
                    owners=[r for r in cohort if r['start']==first and re.fullmatch(r'SECTION\s*0*1',r['location'].strip(),re.I)]
                    if owners:good('Section 1 opens',f'{period}: {", ".join(r["name"] for r in owners)} is assigned Section 1 and arrives with the first servers at {clock(first)}.')
        if not s['close_time']:skipped.append('Closing coverage: set your actual FOH closing time in Review rules.')
        elif servers and clean('Closing coverage'):good('Closing coverage','Section 1 and a lounge server cover your configured FOH closing time.')
    if s['hosts']:
        hosts=[r for r in rows if r['role']=='Host']
        points=sorted({t for r in hosts for t in (r['start'],r['end'])})
        has_overlap=any(sum(r['start']<=t<r['end'] for r in hosts)>=2 for t in points)
        if has_overlap and clean('Host positions'):good('Host positions assigned','Overlapping hosts have the correct two-host or three-position plan, including valid staggered arrivals and departures.')
        elif not has_overlap:skipped.append('Two/three-host assignments: no multiple-host overlap was present.')
    if s['early']:
        opening=[r for r in rows if r['role'] in ['Bar','To Go']]
        if opening and clean('Early start'):good('Bar / To Go starts',f'All {len(opening)} Bar and To Go shift rows start at or after {clock(int(s["early_start"].split(":")[0])*60+int(s["early_start"].split(":")[1]))}.')
        elif not opening:skipped.append('Bar / To Go start times: no relevant rows were read.')
    if s['house'] and clean('House shift'):good('No House Shifts','No House Shifts were found in the roster.')
    if s['swing'] and staff and clean('Swing shift'):good('Swing-shift entries','No non-manager AM shifts cross into PM without a double marker. PM early arrivals are allowed.')
    if s['doubles'] and clean('Doubles'):
        names=collections.defaultdict(list)
        for r in staff:
            name=re.sub(r'\[[^]]*\]','',r['name']).strip().casefold()
            if name and not re.search(r'\bhouse\b',name):names[name].append(r)
        count=sum(any(re.search(r'\[D\]',r['name'],re.I) for r in rr) or len({(r['start'],r['end']) for r in rr})>1 for rr in names.values())
        good('Doubles within threshold',f'{count} non-manager people have doubles or multiple shifts; your threshold is {s["double_limit"]}.')
    labels={'locations':'Location assignments','sections':'Server numbering','open_close':'Opening and closing coverage','hosts':'Host assignments','early':'Early starts','house':'House Shifts','swing':'Swing shifts','doubles':'Doubles'}
    labels.update(host_coverage='Lunch / dinner hosts',cook_close='Closing cooks',z3_rover='PM Z3-rover')
    for key,label in labels.items():
        if not s[key]:skipped.append(label+': disabled in Review rules.')
    return passed,skipped

def marked_pdf(documents,settings):
    writer=PdfWriter()
    for doc in documents:
        reader=PdfReader(io.BytesIO(doc['data']));base=len(writer.pages)
        for p in reader.pages:writer.add_page(p)
        for card in doc['cards']:
            p=writer.pages[base+card['page']];height=float(p.mediabox.height)
            byid={r['id']:r for r in card['rows']}
            for n,f in enumerate(card['findings'],1):
                for rid in f['rows']:
                    r=byid[rid];x0,t,x1,b=r['rect'];rect=(x0,height-b,x1,height-t)
                    from pypdf.generic import ArrayObject, FloatObject
                    quad=ArrayObject([FloatObject(v) for v in [x0,height-t,x1,height-t,x0,height-b,x1,height-b]])
                    writer.add_annotation(base+card['page'],Highlight(rect=rect,quad_points=quad,highlight_color='FFE08A'))
                    writer.add_annotation(base+card['page'],Text(rect=(x0,height-b,x0+12,height-b+12),text=f'{n}. {f["rule"]}: {f["message"]}',open=False))
            buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=(612,792));y=735
            def heading():
                nonlocal y
                c.setFillColor(HexColor('#152c3d'));c.setFont('Helvetica-Bold',20);c.drawString(36,750,'Labor card review');c.setFont('Helvetica',10);c.drawString(36,732,card['restaurant'][:100]);c.drawString(36,716,card['date']);y=688
            heading()
            entries=list(card['findings']) or [{'rule':'No issues found','message':'No enabled-rule issues found in the extracted roster. Passed checks and limits are listed below.','level':'review'}]
            entries += [{'rule':'Passed: '+f['rule'],'message':f['message'],'level':'pass'} for f in card.get('positives',[])]
            entries += [{'rule':'Not checked','message':msg,'level':'review'} for msg in card.get('not_checked',[])]
            for n,f in enumerate(entries,1):
                lines=simpleSplit(f['message'],'Helvetica',10,535)
                required=32+len(lines)*14
                if y-required<45:c.showPage();heading()
                c.setFillColor(HexColor('#26704a' if f['level']=='pass' else '#b5312e' if f['level']=='fix' else '#80601c'));c.setFont('Helvetica-Bold',11);c.drawString(36,y,f'{n}. {f["rule"]}');y-=18
                c.setFillColor(HexColor('#152c3d'));c.setFont('Helvetica',10)
                for line in lines:c.drawString(36,y,line);y-=14
                y-=16
            c.setFont('Helvetica',8);c.drawString(36,24,'Original card preserved. Highlights and PDF comments point to findings. Manager review remains required.')
            c.save();notes=PdfReader(buf)
            for p in notes.pages:writer.add_page(p)
    result=io.BytesIO();writer.write(result);return result.getvalue()
