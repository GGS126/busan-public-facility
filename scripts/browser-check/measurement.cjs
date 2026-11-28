const assert = require('node:assert/strict');

async function measureComparison(page, button, facilityIds, timeout=15000) {
  const expected=new Set(facilityIds), completed=new Set(), tracked=new Set();
  let timer, resolve, reject;
  const responses=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const onRequest=request=>{
    if(new URL(request.url()).pathname !== '/api/compare' || request.method() !== 'POST') return;
    const body=request.postDataJSON();
    if(Array.isArray(body?.facility_ids) && body.facility_ids.some(id=>expected.has(id))) tracked.add(request);
  };
  const onResponse=async response=>{
    if(!tracked.has(response.request())) return;
    try {
      if(response.status()!==200) throw new Error('Comparison request failed');
      const body=await response.json();
      assert.ok(Array.isArray(body.results),'Missing comparison results');
      for(const result of body.results) {
        if(!expected.has(result.facility_id)) continue;
        assert.equal(result.fee?.status,'calculated');
        completed.add(result.facility_id);
      }
      if([...expected].every(id=>completed.has(id))) resolve();
    } catch(error) { reject(error); }
  };
  page.on('request',onRequest);
  page.on('response',onResponse);
  timer=setTimeout(()=>reject(new Error('Comparison API response timeout')),timeout);
  try {
    await button.evaluate(button=>{
      window.__compareStart=null;
      for(const card of document.querySelectorAll('#results .comparison-card')) card.dataset.previousMeasurement='true';
      button.addEventListener('click',()=>{window.__compareStart=performance.now();},{once:true,capture:true});
    });
    // Register both waits before clicking; accept either batched or per-facility requests.
    await Promise.all([button.click(),responses]);
    await page.waitForFunction(count=>{
      const cards=[...document.querySelectorAll('#results .comparison-card')];
      return cards.length===count && cards.every(card=>!card.dataset.previousMeasurement && card.textContent.includes('계산 완료'));
    },facilityIds.length,{timeout});
    return await page.evaluate(()=>new Promise(resolve=>{
      requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(performance.now()-window.__compareStart)));
    }));
  } finally {
    clearTimeout(timer);
    page.off('request',onRequest);
    page.off('response',onResponse);
  }
}
module.exports={measureComparison};
