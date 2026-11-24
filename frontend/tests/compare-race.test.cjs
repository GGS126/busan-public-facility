const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const app = fs.readFileSync(path.join(__dirname, '../src/App.jsx'), 'utf8');
function handler(name) {
  const start = app.search(new RegExp(`  (?:async )?function ${name}\\(`));
  assert.notEqual(start, -1, `Missing handler: ${name}`);
  const end = app.indexOf('\n  }', start) + '\n  }'.length;
  return app.slice(start, end);
}

function fixture(settings = {}) {
  const state = { results: [], error: '', loading: false, scrolls: 0 };
  const pending = [];
  const timers = [];
  // Run the real App handlers with controlled state setters and deferred API responses.
  const create = new Function('state', 'pending', 'timers', 'settings', `
    const selectedIds=['facility'], facilityTimes={facility:'10:00|12:00'};
    const sport='tennis', districts=[], date='2026-12-01', people='1';
    const discountTypes=settings.discountTypes || [], discountType=discountTypes[0] || 'none', eligibleCount=settings.eligibleCount || '0', source='direct';
    const searchRequest={current:0}, compareRequest={current:0};
    const noop=()=>{};
    const setSearching=noop, setSearched=noop, setSearchResults=noop, setSelectedIds=noop;
    const setFacilityTimes=noop, setError=noop, validateConditions=()=>'', getMatchingTime=()=>'';
    const setResults=value=>{state.results=value;};
    const setCompareError=value=>{state.error=value;};
    const setLoading=value=>{state.loading=value;};
    const setTimeout=fn=>timers.push(fn);
    const document={getElementById:()=>({scrollIntoView:()=>{state.scrolls++;}})};
    const compareFacilities=request=>new Promise((resolve,reject)=>pending.push({resolve,reject,request}));
    ${['resetComparison', 'clearResult', 'toggleFacility', 'handleTimeChange', 'handleCompare'].map(handler).join('\n')}
    return {clearResult,toggleFacility,handleTimeChange,handleCompare};
  `);
  return { state, pending, timers, ...create(state, pending, timers, settings) };
}
const response = id => ({ results: [{facility_id:id, fee:{status:'calculated'}}] });

for (const change of ['clearResult', 'toggleFacility', 'handleTimeChange']) {
  test(`ignores old comparison after ${change}`, async () => {
    const f=fixture();
    const request=f.handleCompare();
    f[change]('facility', '11:00|12:00');
    f.pending[0].resolve(response('old'));
    await request;
    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);
  });
}

test('old failure cannot overwrite a new request or its loading state', async () => {
  const f=fixture();
  const first=f.handleCompare();
  const second=f.handleCompare();
  f.pending[0].reject(new Error('old error'));
  await first;
  assert.equal(f.state.error, '');
  assert.equal(f.state.loading, true);
  f.pending[1].resolve(response('new'));
  await second;
  assert.equal(f.state.results[0].facility_id, 'new');
  assert.equal(f.state.loading, false);
});

test('newest result survives an older successful response', async () => {
  const f=fixture();
  const first=f.handleCompare();
  const second=f.handleCompare();
  f.pending[1].resolve(response('new'));
  await second;
  f.pending[0].resolve(response('old'));
  await first;
  assert.equal(f.state.results[0].facility_id, 'new');
});

test('invalidated comparison cannot scroll back to old results', async () => {
  const f=fixture();
  const request=f.handleCompare();
  f.pending[0].resolve(response('valid'));
  await request;
  f.clearResult();
  f.timers.forEach(fn=>fn());
  assert.equal(f.state.scrolls, 0);
});


test('single discount sends the entered eligible count to the common engine', async () => {
  const f=fixture({discountTypes:['multi_child'], eligibleCount:'1'});
  const request=f.handleCompare();
  const conditions=f.pending[0].request.conditions;
  assert.deepEqual(conditions.discount_types, []);
  assert.deepEqual(conditions.discounts, [{type:'multi_child',count:1,holder:false}]);
  f.pending[0].resolve(response('valid'));
  await request;
});

test('multiple discount types are not assigned an invented per-type count', async () => {
  const f=fixture({discountTypes:['multi_child','disabled'], eligibleCount:'1'});
  const request=f.handleCompare();
  const conditions=f.pending[0].request.conditions;
  assert.deepEqual(conditions.discount_types, ['multi_child','disabled']);
  assert.deepEqual(conditions.discounts, []);
  f.pending[0].resolve(response('valid'));
  await request;
});
