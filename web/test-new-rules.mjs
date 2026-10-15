import {loadPyodide} from 'pyodide';
import fs from 'node:fs/promises';
import path from 'node:path';
const py=await loadPyodide({indexURL:path.resolve('public/runtime')+'/'});
await py.loadPackage(['micropip','pillow','cryptography']);
const wheels=JSON.parse(await fs.readFile('public/wheels.json','utf8'));
for(const file of wheels)py.FS.writeFile('/tmp/'+file,new Uint8Array(await fs.readFile('public/wheels/'+file)));
py.globals.set('wheels',wheels);
await py.runPythonAsync("import micropip\nawait micropip.install(['emfs:///tmp/'+f for f in wheels.to_py()],deps=False)");
for(const file of ['analyzer.py','browser_bridge.py'])py.FS.writeFile('/home/pyodide/'+file,await fs.readFile('public/'+file,'utf8'));
py.FS.writeFile('/home/pyodide/test_analyzer.py',await fs.readFile('../local/test_analyzer.py','utf8'));
py.runPython(`from browser_bridge import execute
import unittest,test_analyzer
suite=unittest.TestSuite(test_analyzer.Rules(n) for n in ['test_host_required_each_shift','test_closing_cooks_weekday_weekend_and_distinct_people','test_single_pm_z3_requires_rover'])
result=unittest.TextTestRunner().run(suite)
assert result.wasSuccessful()
`);
