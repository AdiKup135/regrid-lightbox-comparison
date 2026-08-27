import aduHeight from './aduHeight.js';

// Fixtures = real zoneDetail (output_fields=controls&replace_STF=true) responses, Aug 2026 sweep,
// trimmed to the keys the ADU branch reads.
const cases = [
  { name: 'Sunnyvale R1 (no ADU keys)', expect: { ft: 16, floors: null, status: 'review', transit: true },
    zdc: { max_building_height_ft: '30', maximum_building_height_ft: '30 ft or 2 stories' } },

  { name: 'San Jose R-1-8 (no ADU keys)', expect: { ft: 16, floors: null, status: 'review', transit: true },
    zdc: { max_building_height_ft: '35', maximum_building_height_ft: '35 or 2.5 stories' } },

  { name: 'Palo Alto R-1 (no ADU keys)', expect: { ft: 16, floors: null, status: 'review', transit: true },
    zdc: { maximum_building_height_ft: '30, Maximum Height for buildings with a roof pitch of 12:12 or greater: 33', daylight_plane_ft: 'Side Yard Daylight Plane: (Initial height: 10 feet at interior side lot line, Angles: 45)' } },

  { name: 'Mountain View R1 (full ADU block)', expect: { ft: 28, floors: 2, status: 'ok', transit: false },
    zdc: {
      max_building_height_feet: 'For 1 story structure: 24, For 2 story structure: 28',
      max_accessory_building_height_feet: 'Attached unit or detached unit: (For 1 or 2 story structure: 28 feet, including a basement level), Above an accessory structure: (For 2 story structure: 28 feet maximum if the accessory dwelling unit is proposed on the second story of an accessory structure)',
      max_accessory_gross_floor_area_sq_feet: '850 square feet for one bedroom or fewer, and 1000 square feet for two bedrooms or more',
      min_accessory_rear_yard_feet: '4',
    } },

  { name: 'San Francisco RH-1(D) (no ADU keys)', expect: { ft: 16, floors: null, status: 'review', transit: true },
    zdc: { max_building_height_ft: '40', maximum_dwelling_unit_sq_ft: 'Maximum Dwelling Unit Size: (P up to 4,000 sq ft of Gross Floor Area)' } },

  { name: 'Oakland RH-4 (accessory clause embedded in main key)', expect: { ft: 16, floors: null, status: 'ok', transit: true },
    zdc: { maximum_building_height_ft: 'Lots with a footprint slope of less than 20 percent: (Wall height primary building: 25, Pitched roof height primary building: 30, Accessory structures: 15), Lots with a footprint slope of greater than 20 percent: (Detached accessory structures: 15, Wall height primary building: 32)' } },

  { name: 'Berkeley R-1H (local 12 ft preempted)', expect: { ft: 16, floors: null, status: 'ok', transit: true },
    zdc: { maximum_main_building_height_feet: 'New buildings and non residential additions: 28 ft or 3 stories', maximum_accessory_buildings_height_feet: '12 ft or 1 story' } },

  { name: 'Santa Clara R1-6L (accessory req text)', expect: { ft: 16, floors: null, status: 'ok', transit: true },
    zdc: { max_building_height_ft: '25', minimum_accessory_structure_requirements: 'Height and Roof: Maximum height of a residential accessory structure shall be 16 feet provided that the height of such a structure is no greater than the height of the primary building', minimum_seperation_between_multi_building_ft: 'Accessory: Residential accessory structures shall maintain a six-foot separation from other structures including the primary structure on the parcel' } },

  { name: 'Redwood City R-2 (no ADU keys)', expect: { ft: 16, floors: null, status: 'review', transit: true },
    zdc: { max_building_height_ft: '28', maximum_building_height_ft: '28 ft or 2 and one half stories' } },

  { name: 'Cupertino R1-10 (no ADU keys)', expect: { ft: 16, floors: null, status: 'review', transit: true },
    zdc: { max_building_height_ft: '28', maximum_height_limit_ft: '28 or two stories' } },
];

let fail = 0;
for (const c of cases) {
  const r = aduHeight(c.zdc);
  const transitShown = r.detail.some(d => /transit/.test(d));
  const ok = r.ft === c.expect.ft && (r.floors ?? null) === c.expect.floors
    && r.status === c.expect.status && transitShown === c.expect.transit;
  if (!ok) fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${c.name}: ft=${r.ft} floors=${r.floors} status=${r.status} transitNote=${transitShown}`
    + (ok ? '' : `  (expected ft=${c.expect.ft} floors=${c.expect.floors} status=${c.expect.status} transitNote=${c.expect.transit})`));
}
console.log(fail ? `\n${fail} failures` : '\nall pass');
process.exit(fail ? 1 : 0);
