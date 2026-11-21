import {test,expect} from '@playwright/test';

test('seeded demo uses live authorized documents and measured evaluations',async({page})=>{
  test.skip(process.env.TEST_LIVE_DEMO!=='1','Requires seeded API at localhost:8000; enabled explicitly.');
  await page.goto('/');
  await page.getByRole('button',{name:'Explore demo workspace'}).click();
  await expect(page.getByRole('navigation',{name:'Main navigation'})).toBeVisible();
  await page.getByRole('link',{name:'Knowledge library'}).click();
  await expect(page.getByRole('cell',{name:'ready',exact:true}).first()).toBeVisible();
  await page.getByRole('link',{name:'Search explorer'}).click();
  await page.getByRole('textbox',{name:'Search query'}).fill('leave approval');
  await page.getByRole('button',{name:'Compare retrieval'}).click();
  await expect(page.getByRole('button',{name:'Compare retrieval'})).toBeEnabled({timeout:90000});
  await expect(page.getByRole('button',{name:'View source'}).first()).toBeVisible();
  await expect(page.getByRole('main').getByRole('alert')).toHaveCount(0);
  await page.getByRole('link',{name:'Evaluation studio'}).click();
  await expect(page.getByRole('columnheader',{name:'Recall@K'}).first()).toBeVisible();
  await page.screenshot({path:'test-results/live-evaluations.png',fullPage:true});
});
