const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const {chromium} = require(process.env.PLAYWRIGHT_HOME || 'playwright');

(async () => {
  const child = spawn(process.env.PYTHON_EXE || 'python', ['tests/browser_host.py'], {cwd:path.join(__dirname,'..'),env:{...process.env,PYTHONIOENCODING:'utf-8'},stdio:['pipe','pipe','pipe']});
  let stderr='';child.stderr.on('data',c=>stderr+=c);
  const config = await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('样例环境未启动：'+stderr)),25000);
    readline.createInterface({input:child.stdout}).once('line',line=>{clearTimeout(timer);resolve(JSON.parse(line));});
    child.once('exit',code=>{clearTimeout(timer);reject(Error('样例环境提前退出：'+code+' '+stderr));});
  });
  const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
  const errors=[]; const checks=[];
  try {
    const page=await browser.newPage({viewport:{width:1360,height:900}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(config.url);
    await page.getByRole('heading',{name:'把商品资料交给店铺'}).waitFor();
    checks.push('页面打开');
    if(process.env.SCREENSHOT_DIR){fs.mkdirSync(process.env.SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'desktop.png'),fullPage:true});}
    await page.getByLabel('商品资料文件夹').fill(config.source+'不存在');
    await page.getByLabel('店铺配置文件').fill(config.shop);
    await page.getByRole('button',{name:'生成发布清单'}).click();
    await page.getByText('商品资料文件夹不存在',{exact:true}).waitFor();
    checks.push('无效资料提示');
    await page.getByLabel('商品资料文件夹').fill(config.source);
    await page.getByLabel('执行方式').selectOption('publish');
    await page.getByRole('button',{name:'生成发布清单'}).click();
    await page.waitForFunction(()=>document.querySelector('#table').textContent.includes('浏览器检查用演示商品')||document.querySelector('#message').classList.contains('error'));
    assert.match(await page.locator('#table').innerText(),/浏览器检查用演示商品/,await page.locator('#message').innerText());
    assert.match(await page.locator('#table').innerText(),/29.90/);
    checks.push('商品、售价、库存清单');
    await page.getByRole('button',{name:'按清单执行',exact:true}).click();
    await page.getByText('这批商品已完成核对。',{exact:true}).waitFor({timeout:25000});
    assert.match(await page.locator('#table').innerText(),/已发布/);
    assert.match(await page.locator('#table').innerText(),/编号 100/);
    assert.match(await page.getByRole('link',{name:'查看商品'}).getAttribute('href'),/^https:\/\//);
    checks.push('执行与商品编号回读');
    await page.getByRole('button',{name:'再次执行',exact:true}).click();
    await page.getByText('正在执行，请保留此页面。',{exact:true}).waitFor();
    await page.getByText('这批商品已完成核对。',{exact:true}).waitFor({timeout:25000});
    assert.match(await page.locator('#table').innerText(),/编号 100/);
    checks.push('页面再次执行保留编号');
    await page.setViewportSize({width:390,height:844});
    await page.goto(config.url);
    await page.getByRole('heading',{name:'把商品资料交给店铺'}).waitFor();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'mobile.png'),fullPage:true});
    checks.push('手机宽度无横向溢出');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:checks.length,checks,errors}));
  } finally {
    await browser.close(); child.kill();
  }
})().catch(e=>{console.error(e.stack);process.exit(1);});
