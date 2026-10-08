const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {allocate}=require('../web/calculator.js');
const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'calculator_cases.json'),'utf8'));
for(const test of cases){const actual=allocate(test.legs,test.budget,test.config);assert.equal(actual.payout,test.expected.payout);assert.equal(actual.profit,test.expected.profit);assert.deepEqual(actual.legs.map(l=>l.stake),test.expected.legs.map(l=>l.stake));assert.deepEqual(actual.legs.map(l=>l.payout),test.expected.legs.map(l=>l.payout));}
console.log(`Kalkulator strony zgadza się ze skanerem: ${cases.length} scenariuszy.`);
