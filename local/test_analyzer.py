import copy, unittest
from pathlib import Path
import os
FIXTURES=Path(os.environ.get('LABOR_CARD_FIXTURES',Path(__file__).parent/'fixtures'))
from analyzer import analyze, parse_pdf, marked_pdf, service_times
from pypdf import PdfReader
import io

def row(name,role,loc,period='PM',start='4:00 PM',end='10:00 PM'):
    return {'id':name+loc+start,'name':name,'role':role,'location':loc,'period':period,'in':start,'out':end,'rect':[1,1,10,10]}
def card(rows):
    return {'rows':rows,'warnings':[],'page':0,'restaurant':'Test','date':'October 15, 2026'}
def rules_only(**kw):
    return {**{k:False for k in ['hosts','locations','sections','open_close','early','doubles','house','swing','host_coverage','cook_close','z3_rover']},**kw}

class Rules(unittest.TestCase):
    def test_host_required_each_shift(self):
        rows=[row('Lunch','Host','LEADER',period='AM',start='11:00 AM',end='3:00 PM')]
        findings=analyze(card(rows),rules_only(host_coverage=True))['findings']
        self.assertEqual(len(findings),1);self.assertIn('Dinner',findings[0]['message'])
        rows.append(row('Dinner','Host','LEADER'))
        self.assertFalse(analyze(card(rows),rules_only(host_coverage=True))['findings'])
        rows[-1]['name']='House Shift'
        self.assertTrue(analyze(card(rows),rules_only(host_coverage=True))['findings'])
    def test_closing_cooks_weekday_weekend_and_distinct_people(self):
        for date,out in [('October 15, 2026','12:00 AM'),('October 16, 2026','1:00 AM'),('October 17, 2026','1:00 AM'),('October 18, 2026','12:00 AM')]:
            rows=[row(str(i),'Kitchen',f'Z{i+1}',end=out) for i in range(3)]
            c=card(rows);c['date']=date
            self.assertFalse(analyze(c,rules_only(cook_close=True))['findings'])
            rows[0]['out']='11:59 PM'
            self.assertTrue(analyze(c,rules_only(cook_close=True))['findings'])
            rows[0]['out']=out;rows[1]['name']=rows[0]['name']
            self.assertTrue(analyze(c,rules_only(cook_close=True))['findings'])
    def test_single_pm_z3_requires_rover(self):
        rows=[row('cook','Kitchen','Z3')]
        self.assertTrue(analyze(card(rows),rules_only(z3_rover=True))['findings'])
        rows[0]['location']='Z3-rover'
        self.assertFalse(analyze(card(rows),rules_only(z3_rover=True))['findings'])
        rows[0]['location']='Z3';rows.append(row('second','Kitchen','Z3'))
        self.assertFalse(analyze(card(rows),rules_only(z3_rover=True))['findings'])
    def test_positives_do_not_claim_unconfigured_close(self):
        c=analyze(card([row('s','Server','SECTION 1'),row('l','Server','LOUNGE 1')]),rules_only(locations=True,sections=True,open_close=True))
        self.assertTrue(c['positives'])
        self.assertFalse(any(p['rule']=='Closing coverage' for p in c['positives']))
        self.assertTrue(any('Closing coverage' in msg for msg in c['not_checked']))
    def test_reading_warning_prevents_confirmed_passes(self):
        c=card([row('s','Server','SECTION 1')]);c['warnings']=['Unreadable row']
        self.assertFalse(analyze(c)['positives'])
    def test_consecutive_sections_and_separate_lounge(self):
        rows=[row(str(n),'Server',f'SECTION {n}') for n in range(1,6)]+[row('L1','Server','LOUNGE 1'),row('L2','Server','LOUNGE 2')]
        c=analyze(card(rows),rules_only(sections=True));self.assertEqual(c['findings'],[]);self.assertEqual(c['server_count'],7)
        rows[2]['location']='SECTION 9'
        self.assertIn('Location sequence',[f['rule'] for f in analyze(card(rows),rules_only(sections=True))['findings']])
    def test_lounge_two_alone(self):
        self.assertTrue(analyze(card([row('L','Server','LOUNGE 2')]),rules_only(sections=True))['findings'])
    def test_nonoverlapping_duplicate_is_allowed(self):
        c=card([row('a','Server','SECTION 1',start='4:00 PM',end='6:00 PM'),row('b','Server','SECTION 1',start='6:00 PM')])
        self.assertFalse(analyze(c,rules_only(sections=True))['findings'])
    def test_three_host_coverage_uses_actual_overlap(self):
        rows=[row('a','Host','LEADER'),row('b','Host','SEATER'),row('c','Host','GREETER',start='5:00 PM')]
        self.assertFalse(any('3 hosts overlap' in f['message'] for f in analyze(card(rows),rules_only(hosts=True))['findings']))
        rows[0]['location']='LEADER/GREETER/SEATER'
        f=[f for f in analyze(card(rows),rules_only(hosts=True))['findings'] if '3 hosts overlap' in f['message']];self.assertEqual(len(f),1);self.assertIn('5:00 PM',f[0]['message'])
        rows[2]['in']='10:00 PM';rows[2]['out']='11:00 PM'
        self.assertFalse(any('3 hosts overlap' in f['message'] for f in analyze(card(rows),rules_only(hosts=True))['findings']))
    def test_two_hosts_need_leader_and_seater_greeter(self):
        rows=[row('a','Host','LEADER'),row('b','Host','SEATER/GREETER')]
        self.assertFalse(analyze(card(rows),rules_only(hosts=True))['findings'])
        rows[1]['location']='GREETER/SEATER'
        self.assertFalse(analyze(card(rows),rules_only(hosts=True))['findings'])
        rows[1]['location']='LEADER'
        f=analyze(card(rows),rules_only(hosts=True))['findings']
        self.assertEqual(len(f),1)
        self.assertIn('Seater/Greeter',f[0]['message'])
        rows[1]['in']='10:00 PM';rows[1]['out']='11:00 PM'
        self.assertFalse(analyze(card(rows),rules_only(hosts=True))['findings'])
    def test_staggered_three_host_plan(self):
        rows=[row('seater','Host','SEATER',end='11:00 PM'),row('greeter','Host','GREETER',end='9:00 PM'),row('leader','Host','LEADER',start='4:30 PM',end='9:00 PM')]
        self.assertFalse(analyze(card(rows),rules_only(hosts=True))['findings'])
    def test_house_and_blank(self):
        f=analyze(card([row('House Shift','Dish','')]),rules_only(house=True,locations=True))['findings']
        self.assertEqual({x['rule'] for x in f},{'House shift','Blank location'})
    def test_managers_do_not_need_locations(self):
        self.assertFalse(analyze(card([row('John','Manager','')]),rules_only(locations=True))['findings'])
    def test_manager_long_shift_is_not_a_swing_violation(self):
        self.assertFalse(analyze(card([row('John','Manager','',period='AM',start='7:00 AM',end='7:00 PM')]),rules_only(locations=True,swing=True,doubles=True))['findings'])
    def test_pm_cook_early_arrival_is_not_swing(self):
        self.assertFalse(analyze(card([row('Cook','Kitchen','Z1',start='3:30 PM',end='10:00 PM')]),rules_only(swing=True))['findings'])
    def test_no_invented_midnight_closing_time(self):
        rows=[row('s','Server','SECTION 1',end='11:00 PM'),row('s2','Server','SECTION 2',start='5:00 PM',end='12:30 AM'),row('l','Server','LOUNGE 1',end='12:00 AM')]
        self.assertFalse(analyze(card(rows),rules_only(open_close=True))['findings'])
        self.assertTrue(analyze(card(rows),rules_only(open_close=True,close_time='00:30'))['findings'])
    def test_overnight_close(self):
        rows=[row('s','Server','SECTION 1',end='12:30 AM'),row('l','Server','LOUNGE 1',end='12:30 AM')]
        self.assertFalse(analyze(card(rows),rules_only(open_close=True,close_time='00:30'))['findings'])
    def test_midnight_out_is_not_opening(self):
        rows=[row('opener','Server','SECTION 1',period='AM',start='10:30 AM',end='4:00 PM'),row('closer','Server','SECTION 1',end='12:30 AM'),row('lounge','Server','LOUNGE 1',end='12:30 AM')]
        self.assertFalse(analyze(card(rows),rules_only(open_close=True))['findings'])
        self.assertEqual(service_times('4:00 PM','12:30 AM'),(960,1470))
    def test_after_midnight_arrival_never_opens(self):
        rows=[row('late','Server','SECTION 2',period='AM',start='12:30 AM',end='1:30 AM'),row('opener','Server','SECTION 1',period='AM',start='10:30 AM',end='4:00 PM')]
        f=analyze(card(rows),rules_only(open_close=True))['findings']
        self.assertFalse(any(x['rule']=='Opening server' for x in f))
        self.assertTrue(any(x['rule']=='After-midnight start' for x in f))
    def test_original_sample(self):
        p=FIXTURES/'sample-labor-card.pdf'
        if not p.exists():self.skipTest('Set LABOR_CARD_FIXTURES to a folder with sample-labor-card.pdf.')
        c=analyze(parse_pdf(p.read_bytes(),p.name)[0]);self.assertTrue(c['rows']);self.assertFalse(c['warnings'])
        pdf=marked_pdf([{'data':p.read_bytes(),'cards':[c]}],{})
        output=PdfReader(io.BytesIO(pdf));self.assertGreater(len(output.pages),1);self.assertTrue(output.pages[0]['/Annots'])
    def test_service_date_is_not_generation_date(self):
        p=FIXTURES/'labor-card-2026-10-15.pdf'
        if not p.exists():self.skipTest('Set LABOR_CARD_FIXTURES to a folder with labor-card-2026-10-15.pdf.')
        self.assertEqual(parse_pdf(p.read_bytes(),p.name)[0]['date'],'October 15, 2026')

if __name__=='__main__':unittest.main()
