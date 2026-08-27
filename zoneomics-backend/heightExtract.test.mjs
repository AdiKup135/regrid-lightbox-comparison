import extractHeight from './heightExtract.js';

const cases = [
  {
    name: 'Sunnyvale R1', expect: { ft: 30, floors: 2, status: 'ok' },
    cc: { type: 'fixed', value: '30' },
    zdc: { max_building_height_ft: '30', maximum_building_height_ft: '30 ft or 2 stories' },
  },
  {
    name: 'San Jose R-1-8', expect: { ft: 35, floors: 2.5, status: 'ok' },
    cc: { type: 'fixed', value: '35' },
    zdc: { max_building_height_ft: '35', maximum_building_height_ft: '35 or 2.5 stories' },
  },
  {
    name: 'Palo Alto R-1', expect: { ft: 30, floors: null, status: 'ok' },
    cc: { type: 'conditional', conditions: [
      { value: 30, condition: 'base height' },
      { value: 33, condition: 'Maximum Height for buildings with a roof pitch of 12:12 or greater' },
      { value: 33, condition: 'special flood hazard area - max (context 1)' },
      { value: 17, condition: '(S) Combining' },
      { value: 20, condition: 'special flood hazard area - max (context 2)' },
    ], best_case_value: 33, worst_case_value: 17 },
    zdc: { maximum_building_height_ft: '30, Maximum Height for buildings with a roof pitch of 12:12 or greater: 33, In a special flood hazard area the maximum heights are increased by one-half of the increase in elevation required to reach base flood elevation, up to a maximum building height of 33, With (S) Combining: 17, limited to one habitable floor, Habitable floors include lofts, mezzanines, and similar areas with interior heights of 5 or more from the roof to the floor, but shall exclude finished basements and shall exclude attics that have no stairway or built-in access, special flood hazard area, the maximum height is increased by one-half of the increase in elevation required to reach base flood elevations, up to a maximum building height of 20 feet', daylight_plane_ft: 'Side Yard Daylight Plane excludes street side yards: (Initial height: 10 feet at interior side lot line, , Angles: 45)' },
  },
  {
    name: 'Mountain View R1', expect: { ft: 28, floors: 2, status: 'ok' },
    cc: { type: 'conditional', conditions: [
      { value: 24, condition: 'For 1 story structure' },
      { value: 28, condition: 'For 2 story structure' },
      { value: 15, condition: '1st floor wall height at top of wall plate' },
      { value: 22, condition: '2nd floor wall height at top of wall plate' },
    ], best_case_value: 28, worst_case_value: 15 },
    zdc: { max_building_height_feet: 'For 1 story structure: 24, For 2 story structure: 28, 1st floor wall height at top of wall plate: 15, 2nd floor wall height at top of wall plate: 22', max_accessory_building_height_feet: 'Attached unit or detached unit: (For 1 or 2 story structure: 28 feet, including a basement level)' },
  },
  {
    name: 'SF RH-1(D)', expect: { ft: 40, floors: null, status: 'ok' },
    cc: { type: 'fixed', value: '40' },
    zdc: { max_building_height_ft: '40', maximum_building_height_ft: 'General Height Limit: 40, HC-SF Program Height Limit: 40', additional_heights_limits: 'Height Limits Applicable to the Entire Property: 35 ft, except that: (...)' },
  },
  {
    name: 'Oakland RH-4 (labels all General)', expect: { ft: 25, floors: null, status: 'ok' },
    cc: { type: 'conditional', conditions: [
      { value: 25, condition: 'General' }, { value: 30, condition: 'General' }, { value: 15, condition: 'General' },
      { value: 15, condition: 'General' }, { value: 32, condition: 'General' }, { value: 36, condition: 'General' },
      { value: 36, condition: 'General' }, { value: 18, condition: 'General' }, { value: 15, condition: 'General' },
      { value: 34, condition: 'General' }, { value: 38, condition: 'General' }, { value: 38, condition: 'General' },
      { value: 18, condition: 'General' }, { value: 15, condition: 'General' }, { value: 36, condition: 'General' },
      { value: 40, condition: 'General' }, { value: 40, condition: 'General' }, { value: 18, condition: 'General' },
      { value: 15, condition: 'General' }, { value: 32, condition: 'General' }, { value: 35, condition: 'General' },
      { value: 24, condition: 'General' }, { value: 24, condition: 'General' },
    ], best_case_value: 40, worst_case_value: 15 },
    zdc: { maximum_building_height_ft: 'Lots with a footprint slope of less than 20 percent: (Wall height primary building: 25, Pitched roof height primary building: 30, Accessory structures: 15), Lots with a footprint slope of greater than 20 percent: (Lots with greater than 20 percent and less than 40 percent footprint slope: Detached accessory structures: 15, Wall height primary building: 32, Wall height primary building with conditional use permit: 36, Pitched roof height primary building: 36, Above edge of pavement: 18)', minimum_height_of_ground_floor_nonresidential_facilities_ft: 'NA' },
  },
  {
    name: 'Berkeley R-1H overlay', expect: { ft: 28, floors: 3, status: 'ok' },
    cc: { type: 'conditional', conditions: [
      { value: 28, condition: 'New buildings and non residential additions' },
      { value: 35, condition: 'With administrative use permit' },
      { value: 14, condition: 'Residential additions' },
      { value: 28, condition: 'Height greater than 14 feet up to 28 feet allowed with an administrative use permit' },
      { value: 35, condition: 'Height greater than 28 feet up to 35 feet allowed with an additional administrative use permit' },
      { value: 28, condition: 'Overlay zone average allowed height' },
      { value: 35, condition: 'Overlay zone maximum allowed height' },
      { value: 'As required by the base district or the highest existing portion of the roof whichever is lower', condition: 'Overlay zone residential additions average height' },
      { value: 20, condition: 'Overlay zone residential additions maximum height' },
    ], best_case_value: 35, worst_case_value: 14 },
    zdc: { maximum_main_building_height_feet: 'New buildings and non residential additions: 28 ft or 3 stories, With administrative use permit: 35, Rear main buildings: 22 ft or 2 stories, Residential additions: 14', maximum_accessory_buildings_height_feet: '12 ft or 1 story' },
  },
  {
    name: 'Santa Clara R1-6L (stories in own key)', expect: { ft: 25, floors: 2, status: 'ok' },
    cc: { type: 'fixed', value: '25' },
    zdc: { max_building_height_ft: '25', maximum_building_height_ft: 'Within 20 feet of the R1-6L, R1-8L and R2 zones: 25, All other zones: 25', maximum_building_height_stories: '2 stories, Number of Stories and the Daylight Plane: All structures adjacent to R1 and R2 zones shall include a 45-degree daylight plan' },
  },
  {
    name: 'Redwood City R-2 (word fraction stories)', expect: { ft: 28, floors: 2.5, status: 'ok' },
    cc: { type: 'fixed', value: '28' },
    zdc: { max_building_height_ft: '28', maximum_building_height_ft: '28 ft or 2 and one half stories' },
  },
  {
    name: 'Cupertino R1-10 (word stories, odd key)', expect: { ft: 28, floors: 2, status: 'ok' },
    cc: { type: 'fixed', value: '28' },
    zdc: { max_building_height_ft: '28', maximum_height_limit_ft: '28 or two stories' },
  },
  {
    name: 'Sentinel NA', expect: { ft: null, floors: null, status: 'review' },
    cc: { type: 'fixed', value: 'NA' },
    zdc: {},
  },
  {
    name: 'unit_mismatch shape', expect: { ft: null, floors: null, status: 'review' },
    cc: { type: 'unit_mismatch', value: { best_case_value: null, condition_values: [{ value: '20 percent of lot width', condition: '20 percent of lot width' }], worst_case_value: null } },
    zdc: {},
  },
];

let fail = 0;
for (const c of cases) {
  const r = extractHeight(c.cc, c.zdc);
  const ok = r.ft === c.expect.ft && (r.floors ?? null) === c.expect.floors && r.status === c.expect.status;
  if (!ok) fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${c.name}: ft=${r.ft} floors=${r.floors} status=${r.status}` + (ok ? '' : `  (expected ft=${c.expect.ft} floors=${c.expect.floors} status=${c.expect.status})`));
}
console.log(fail ? `\n${fail} failures` : '\nall pass');
process.exit(fail ? 1 : 0);
