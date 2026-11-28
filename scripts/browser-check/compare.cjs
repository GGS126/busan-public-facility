/* Browser-only verification. Start the real frontend/backend before running. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { parseArgs } = require('node:util');
const { measureComparison } = require('./measurement.cjs');

const { values } = parseArgs({options:{
  url:{type:'string'}, output:{type:'string'}, samples:{type:'string',default:'30'},
  channel:{type:'string',default:'chrome'}, headed:{type:'boolean',default:false},
}});
if (!values.url) throw new Error('--url is required');
const url = new URL(values.url);
if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
  throw new Error('Use a plain HTTP(S) service URL without credentials, query or fragment');
}
const samples = Number(values.samples);
if (!Number.isInteger(samples) || samples < 20 || samples > 200) throw new Error('--samples must be 20..200');
const root = path.resolve(__dirname, '../..');
function percentile(data, p) { return [...data].sort((a,b)=>a-b)[Math.ceil(data.length*p)-1]; }

(async()=>{
  const browser = await chromium.launch({channel:values.channel,headless:!values.headed});
  const context = await browser.newContext({viewport:{width:1440,height:1080},timezoneId:'Asia/Seoul'});
  const page = await context.newPage();
  const errors=[], timings=[], checks=[];
  let realApiCalls=0;
  page.on('pageerror',error=>errors.push(error.name));
  page.on('response',response=>{
    if(new URL(response.url()).pathname === '/api/compare' && response.status() === 200) realApiCalls++;
  });
  try {
    await page.goto(values.url);
    await page.locator('#sport option[value="tennis"]').waitFor({state:'attached'});
    const day = await page.evaluate(()=>{
      const now = new Date();
      const day = new Date(now.getFullYear(),now.getMonth(),now.getDate()+((8-now.getDay())%7 || 7));
      return [day.getFullYear(),String(day.getMonth()+1).padStart(2,'0'),String(day.getDate()).padStart(2,'0')].join('-');
    });
    await page.locator('#sport').selectOption('tennis');
    await page.locator('#district').selectOption('전체');
    await page.locator('#date').fill(day);
    await page.locator('#people').fill('4');
    await page.locator('#start-time').selectOption('08:00');
    await page.locator('#end-time').selectOption('10:00');
    await page.getByRole('button',{name:'시설 검색하기',exact:true}).click();
    for (const name of ['삼락생태공원 테니스장','구덕운동장 테니스장']) {
      const card=page.locator('.facility-card').filter({has:page.getByRole('heading',{name,exact:true})});
      await card.getByRole('checkbox').check();
      const time=card.locator('select[id^="time-"]');
      await time.waitFor();
      await page.waitForFunction(id=>document.getElementById(id)?.value==='08:00|10:00',await time.getAttribute('id'));
    }
    const button=page.getByRole('button',{name:'선택한 시설 2곳 비교하기',exact:true});
    async function measure(){
      const time=await measureComparison(page,button,['busan_samrak_ecopark_tennis','busan_gudeok_stadium_tennis']);
      const results=page.locator('#results');
      await results.getByText('6,000원',{exact:true}).first().waitFor();
      await results.getByText('8,000원',{exact:true}).first().waitFor();
      assert.equal(await results.locator('.comparison-card').count(),2);
      return time;
    }
    const first=await measure();
    // First request after page start is reported separately, excluded from warm samples.
    for(let index=0;index<samples;index++) timings.push(await measure());
    checks.push('Two actual DB facilities display 6000/8000 won for every measured comparison');

    await page.route('**/api/compare',route=>route.fulfill({
      status:500,json:{error:{code:'internal_error',message:'검증용 서버 오류입니다. 다시 시도해 주세요.'}},
    }));
    await button.click();
    await page.locator('#facilities .error-message').filter({hasText:/\S/}).waitFor();
    assert.equal(await page.locator('#results .comparison-card').count(),0);
    await page.unroute('**/api/compare');
    await measure();
    checks.push('Injected comparison HTTP 500 clears old results; retry returns real results');

    await page.locator('#natural-input').fill('테니스 문의 010-0000-0000');
    const privacyResponse=page.waitForResponse(response=>new URL(response.url()).pathname === '/api/query/parse');
    await page.getByRole('button',{name:'입력 조건 확인하기',exact:true}).click();
    const privacy=await (await privacyResponse).json();
    assert.equal(privacy.status,'llm_failed');
    assert.match(privacy.message,/개인정보/);
    assert.equal(await page.locator('#natural-input').inputValue(),'테니스 문의 010-0000-0000');
    checks.push('Real query API rejects synthetic personal data and UI preserves original sentence');
    assert.deepEqual(errors,[]);
    const under=timings.filter(value=>value<=3000).length;
    const report={
      tested_at:new Date().toISOString(),mode:'real browser, real DB API, warm sequential comparisons',
      source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
      source_tree_dirty:Boolean(execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim()),
      target_origin:url.origin, browser:await browser.version(),headless:!values.headed,
      platform:os.platform(),release:os.release(),node:process.version,hardware_threads:os.cpus().length,
      timezone:await page.evaluate(()=>Intl.DateTimeFormat().resolvedOptions().timeZone),
      scenario:{date:day,sport:'tennis',time:'08:00-10:00',headcount:4,facility_count:2,discounts:[]},
      first_comparison_ms:first,samples,within_3000ms:under,within_3000ms_rate:under/samples,
      successful_compare_api_calls:realApiCalls,
      median_ms:percentile(timings,.5),p95_ms:percentile(timings,.95),max_ms:Math.max(...timings),
      criterion:'95% of warm comparison clicks display both calculated facility cards within 3000 ms',
      passed:under/samples>=.95,checks,page_errors:errors,measurements_ms:timings,
      limits:'Sequential warm desktop browser; not concurrency, mobile, hosting cold-start or final merged-release verification.',
    };
    if(values.output){
      fs.mkdirSync(path.dirname(path.resolve(values.output)),{recursive:true});
      fs.writeFileSync(values.output,JSON.stringify(report,null,2)+'\n');
    }
    console.log(JSON.stringify({passed:report.passed,samples,within_3000ms_rate:report.within_3000ms_rate,
      p95_ms:report.p95_ms,checks},null,2));
    if(!report.passed) process.exitCode=1;
  } finally {await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1});

