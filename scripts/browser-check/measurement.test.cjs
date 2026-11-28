const {test}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const {measureComparison}=require('./measurement.cjs');

test('old calculated cards cannot finish a measurement before fresh API/render',async t=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try {
    for(const batched of [false,true]) await t.test(batched?'one batched request':'per-facility requests',async()=>{
      const page=await browser.newPage();
      const ids=['first','second'];
      await page.route('https://measurement.invalid/',route=>route.fulfill({contentType:'text/html; charset=utf-8',body:
        '<button>선택한 시설 2곳 비교하기</button><section id="results"><span id="status"></span><div class="comparison-card">계산 완료</div><div class="comparison-card">계산 완료</div></section>'}));
      await page.route('**/api/compare',async route=>{
        await new Promise(resolve=>setTimeout(resolve,250));
        await route.fulfill({json:{results:route.request().postDataJSON().facility_ids.map(facility_id=>({
          facility_id,fee:{status:'calculated',total:6000}}))}});
      });
      await page.goto('https://measurement.invalid/');
      await page.evaluate(({ids,batched})=>{
        document.querySelector('button').onclick=async()=>{
          // This mutation leaves the old successful cards visible.
          document.querySelector('#status').textContent='loading';
          const groups=batched?[ids]:ids.map(id=>[id]);
          await Promise.all(groups.map(facility_ids=>fetch('/api/compare',{
            method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({facility_ids})})));
          setTimeout(()=>{
            document.querySelector('#results').innerHTML=ids.map(()=>'<div class="comparison-card">계산 완료</div>').join('');
          },100);
        };
      },{ids,batched});
      const elapsed=await measureComparison(page,page.getByRole('button'),ids);
      assert.ok(elapsed>=350,'Must include delayed responses and new DOM, not old cards');
      await page.close();
    });
    await t.test('no API response cannot pass on existing cards',async()=>{
      const page=await browser.newPage();
      await page.setContent('<button>선택한 시설 2곳 비교하기</button><section id="results"><div class="comparison-card">계산 완료</div><div class="comparison-card">계산 완료</div></section>');
      await assert.rejects(measureComparison(page,page.getByRole('button'),['first','second'],500),
                           /response timeout/);
      await page.close();
    });
  }finally{await browser.close();}
});
