// @artifact production
/*
 * ESS.Philosophy — the "why the screens look like this" help page.
 *
 * Our own prose. Sources are cited by name only (RESOURCES 2.4, 2.10, 2.11,
 * 2.19); nothing here is copied from a standard or a vendor document.
 *
 * API
 *   sections(ctx) -> [{title, body}]   ctx = {paletteName, urgentPct, highPct,
 *     lowPct, isaLow, isaHigh, isaUrgent, shelveMaxMin, defaultDeadbandPct}
 *     (all optional; defaults are the sim's configuration)
 *   sources() -> [{name, use}]         the public sources the page rests on
 *   limitLadder() -> [{level, param, meaning}] the eight rungs, outermost first
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Philosophy = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var SOURCES = [
    { name: 'ISA-18.2', use: 'alarm states, shelving, suppression and out-of-service, alarm performance targets' },
    { name: 'EEMUA 191', use: 'alarm-rate and priority-distribution guidance behind the KPI thresholds' },
    { name: 'ASM Consortium gray-background paper', use: 'the luminance argument for grey backgrounds and the priority split used here' },
    { name: 'Rockwell process HMI style guide', use: 'the ISA-101 aligned colour values in the ISA-101 preset' }
  ];

  var LADDER = [
    { level: 'Range high', param: 'PVEUHI', meaning: 'top of the instrument range; the bar cannot show more' },
    { level: 'Critical high', param: 'PVHH', meaning: 'trip or safety limit; an Urgent alarm and normally an interlock' },
    { level: 'Standard high', param: 'PVHI', meaning: 'the operator must act; a High or Low alarm' },
    { level: 'Target high', param: 'TGTHI', meaning: 'upper edge of the operating band; no alarm, just the aim' },
    { level: 'Target low', param: 'TGTLO', meaning: 'lower edge of the operating band' },
    { level: 'Standard low', param: 'PVLO', meaning: 'the operator must act' },
    { level: 'Critical low', param: 'PVLL', meaning: 'trip or safety limit' },
    { level: 'Range low', param: 'PVEULO', meaning: 'bottom of the instrument range' }
  ];

  function pct(v, d) { return (v == null ? d : v); }

  function sections(ctx) {
    ctx = ctx || {};
    var pal = ctx.paletteName || 'representative';
    var u = pct(ctx.urgentPct, 5), h = pct(ctx.highPct, 10), l = pct(ctx.lowPct, 85);
    var il = pct(ctx.isaLow, 80), ih = pct(ctx.isaHigh, 15), iu = pct(ctx.isaUrgent, 5);
    var shelve = pct(ctx.shelveMaxMin, 60), db = pct(ctx.defaultDeadbandPct, 1);
    return [
      { title: 'Why the screens are grey',
        body: 'Everything that is not asking for attention sits on a mid-grey ground with low-contrast equipment outlines. Colour then means one thing only: an abnormal situation. A saturated red box on a grey page is visible from across the room; the same red on a colourful page is just another colour. The grey also keeps the luminance contrast between text and background in a range that stays readable over a twelve-hour shift and does not glare in a darkened control room. Running and stopped equipment is told apart by brightness and a word, never by red and green alone. The ASM Consortium gray-background paper is the source of this rationale.' },
      { title: 'What priority means',
        body: 'Priority answers one question: if two alarms arrive together, which one do I work first? It is set from the consequence of ignoring the alarm and the time available to respond, not from how loud the equipment owner argued. Urgent is reserved for conditions with a severe consequence and little time; High needs prompt action; Low needs action before the end of the shift; Journal is recorded but never annunciated. A healthy system is heavily weighted to the low end. The ASM guidance used here aims at about ' + u + ' % Urgent, ' + h + ' % High and ' + l + ' % Low; the ISA-derived key performance indicators state the same idea as ' + il + ' / ' + ih + ' / ' + iu + ' for Low / High / Urgent. The Alarm KPI display measures this station against those numbers. Active palette: ' + pal + '.' },
      { title: 'Alarm states and what blinking means',
        body: 'ISA-18.2 describes an alarm as a small state machine. A new alarm is unacknowledged and active: it flashes and sounds the horn. Acknowledging it stops the flashing and the sound, but the box stays lit while the cause is present. If the process returns to normal before anyone acknowledges, the alarm shows an inverse flash so the operator knows something happened and cleared on its own. Flashing therefore always means "nobody has seen this yet"; a steady colour means "seen, still present". Shelved, suppressed and out-of-service alarms are drawn grey and never flash or sound.' },
      { title: 'Shelving, suppression and out of service',
        body: 'These three all silence an alarm and are easy to confuse. Shelving is the operator\'s tool: a nuisance alarm is parked for a stated reason and a bounded time (at most ' + shelve + ' minutes here) and comes back on its own. Suppression by design is the system\'s tool: when a trip has already fired, the alarms that inevitably follow are hidden automatically so the operator sees the cause and not the consequences; they return when the trigger clears. Out of service is the engineer\'s tool: the alarm is removed while an instrument is under maintenance and stays out until it is deliberately returned to service. Each is journaled with who, when and why.' },
      { title: 'Deadband and on-delay',
        body: 'An alarm that flickers around its limit is worse than no alarm, because the operator learns to ignore it. Two settings stop the chatter. The deadband makes the alarm clear only when the value has moved a little way back inside the limit (default ' + db + ' % of range on this station). The on-delay makes the value stay past the limit for a few seconds before the alarm is raised at all, so measurement noise and pump starts do not annunciate; flow loops wait longest, temperature loops least. Both are shown on the Alarms tab of every point.' },
      { title: 'The limit ladder',
        body: 'Every measurement carries a ladder of eight values, drawn as a vertical band beside the value box on the overview and behind the bar on the faceplate. Reading from the outside in: the range is what the instrument can measure; the critical limits are the trip points; the standard limits are where the operator must act; and the target band is where the loop should live. When the pointer sits inside the target band nothing is required. When it leaves the standard band an alarm says so. Engineers set the target band on Point Detail; the alarm limits belong to the Alarms tab.' }
    ];
  }

  function sources() { return SOURCES.map(function (s) { return { name: s.name, use: s.use }; }); }
  function limitLadder() { return LADDER.map(function (r) { return { level: r.level, param: r.param, meaning: r.meaning }; }); }

  return { sections: sections, sources: sources, limitLadder: limitLadder };
});
