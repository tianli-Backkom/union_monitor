const {defineConfig}=require('@playwright/test');

module.exports=defineConfig({
  testDir:'./tests/browser',
  timeout:30_000,
  expect:{timeout:5_000},
  fullyParallel:false,
  workers:1,
  retries:0,
  reporter:[['list'],['junit',{outputFile:'test-results/browser-junit.xml'}]],
  use:{
    baseURL:process.env.DASHBOARD_TEST_URL || 'http://dashboard.test:8877',
    browserName:'chromium',
    headless:true,
    trace:'retain-on-failure',
    screenshot:'only-on-failure',
    acceptDownloads:true,
    launchOptions:{args:['--host-resolver-rules=MAP dashboard.test 127.0.0.1','--no-proxy-server']},
  },
  webServer:process.env.DASHBOARD_TEST_URL ? undefined : {
    command:(process.env.PYTHON || 'python')+' serve.py --port 8877',
    url:'http://127.0.0.1:8877',
    timeout:20_000,
    reuseExistingServer:false,
  },
});
