import assert from 'node:assert/strict';
import {transform} from '../seo-metadata-consistency.mjs';
const canonical='https://xn--ru4bi8s1tac0p.kr/test/';
const graph={'@context':'https://schema.org','@graph':[
  {'@type':'WebPage','@id':canonical+'#webpage',description:'old'},
  {'@type':'Article','@id':canonical+'#article',description:'old',abstract:'Visible long first answer',dateModified:'2026-09-21'},
  {'@type':'Service','@id':canonical+'#service',description:'Do not change verified course details'},
  {'@type':'WebPage','@id':'https://other.example/#webpage',description:'Do not change other pages'}]};
const input=`<!doctype html><html><head><link rel="canonical" href="${canonical}"><meta name="description" content="New &amp; concise"><script type="application/ld+json">${JSON.stringify(graph)}</script></head><body>Unchanged body</body></html>`;
const result=transform(input);const parsed=JSON.parse(result.html.match(/<script[^>]*>(.*?)<\/script>/s)[1]);
assert.equal(result.changedNodes,2);
assert.equal(parsed['@graph'][0].description,'New & concise');
assert.equal(parsed['@graph'][1].abstract,'Visible long first answer');
assert.equal(parsed['@graph'][1].dateModified,'2026-09-21');
assert.deepEqual(parsed['@graph'].slice(2),graph['@graph'].slice(2));
assert.equal(result.html.split('</head>')[1],input.split('</head>')[1]);
assert.equal(transform(result.html).changed,false);
assert.equal(transform(input.replace('<head>','<head><meta name="robots" content="noindex">')).changed,false);
assert.throws(()=>transform(input.replace(JSON.stringify(graph),'{bad-json}')));
console.log('Metadata consistency: 9 assertions passed');
