import { readFileSync, writeFileSync } from 'node:fs';
import { labelEdges } from './engine.mjs';
const cases = JSON.parse(readFileSync('cases.json', 'utf8'));
const out = cases.map((c) => {
  try {
    return { name: c.name, result: labelEdges({
      subject: c.subject, neighbors: c.neighbors, frontRule: c.frontRule,
      frontRuleOverrides: c.frontRuleOverrides, zone: c.zone,
      userFrontOverrideEdgeIndex: c.userFrontOverrideEdgeIndex }) };
  } catch (e) { return { name: c.name, error: String(e.message || e) }; }
});
writeFileSync('ts_out.json', JSON.stringify(out));
console.log('ts cases:', out.length, 'errors:', out.filter(o => o.error).length);
