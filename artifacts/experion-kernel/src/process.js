// @artifact production
/*
 * ESS.Process — the plant orientation document. What the units actually process.
 *
 * Our own prose, describing THIS simulator's own plant. The plant does not exist:
 * it is a generic power-to-liquids train assembled from textbook unit operations
 * so operators can practise on realistic control problems. Nothing here is
 * modelled on, derived from, or intended to represent any company's plant, and
 * no proprietary flowsheet, catalyst, operating condition, separation train or
 * control scheme has been used or inferred.
 *
 * Every tag, setpoint, alarm limit and trip value below was read out of the tag
 * database and src/models.js before it was written down. tests/process-text.test.js
 * asserts that every tag named here exists in the runtime point list and that the
 * prose agrees with the point's configured description. If you edit this file and
 * that test goes red, the prose is wrong, not the test.
 *
 * API
 *   text()      -> the whole orientation document as plain text
 *   sections()  -> [{title, body}]  the same document, split for the PROC dialog
 *   tagsNamed() -> [tag, ...]       every point tag the prose names (for the gate)
 *   fidelity()  -> {modelled, notModelled, ceiling}   what the numbers are worth
 *   sources()   -> [{name, use}]    the published models this plant rests on
 *
 * The document body lives between the PROCESS-TEXT sentinels below so that
 * tools/coach/serve.py can read it as plain text without executing JavaScript,
 * and so there is exactly ONE copy of the prose for the operator and for PIP.
 * Section headings are ALL-CAPS, letters and spaces only, under 40 characters,
 * because serve.py's guide splitter rejects anything else (digits included) and
 * would silently fold the section into the one before it.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Process = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  /* PROCESS-TEXT-BEGIN */
  var TEXT = [
    'PLANT ORIENTATION — SYNTHETIC FUELS DEMONSTRATION PLANT',
    'What you are driving.',
    '',
    'READ THIS FIRST',
    '',
    'This is a training simulator. The plant described here does not exist.',
    'It is a generic power-to-liquids process assembled from textbook unit',
    'operations so that operators can practise on realistic control problems.',
    'It is not modelled on, derived from, or intended to represent any',
    "company's plant, and no proprietary flowsheet, catalyst, operating",
    'condition, separation train or control scheme has been used or inferred.',
    'Every number on this board is this simulator\'s own.',
    '',
    'Equipment tag numbers do not follow the unit layout. They follow the',
    'original demonstration train, and the later units were built around it.',
    'Read the tag, not the position: TIC301 is the flash preheater on Unit',
    'One and TIC311 is the fired heater on Unit Three, one digit apart on',
    'different graphics.',
    '',
    'WHAT THE PLANT MAKES',
    '',
    'The plant takes a crude oxygenate intermediate and hydrogen and makes a',
    'finished liquid hydrocarbon blendstock.',
    '',
    'The intermediate arrives at the battery limit from the carbon dioxide',
    'hydrogenation block, which runs on its own board and is not your',
    "responsibility. Hydrogen arrives at the battery limit from the site's",
    'electrolysis plant, which is also not yours. Your job starts where the',
    'intermediate is received and ends where crude liquid leaves for',
    'intermediate storage and finishing.',
    '',
    'The chemistry, at the level you need it. In Unit One the intermediate is',
    'condensed and dehydrated over a catalyst into a crude hydrocarbon liquid,',
    'and it makes water while it does it. In Unit Three that crude liquid is',
    'finished over a second catalyst with hydrogen, which saturates what is',
    'left unsaturated and strips out what oxygen is left, and it makes water',
    'again. Water is a co-product, not a contaminant. The reactions make it',
    'stoichiometrically and there is a great deal of it.',
    '',
    'THE ROUTE THROUGH THE PLANT',
    '',
    '  UNIT 01  receipt and conversion',
    '             then hot flash, crude liquid to intermediate storage',
    '  UNIT 03  hydrofinishing',
    '  UNIT 04  separation',
    '',
    'UNIT 02, the batch reactor, is on this board but is not in that path.',
    'See WHAT IS NOT SIMULATED at the end of this document.',
    '',
    'UNIT ONE RECEIPT AND CONVERSION',
    '',
    'Supply arrives at the battery limit on FI100, which is an indication',
    'only — you do not control it. Design supply is 60 M3/H.',
    '',
    'Crude intermediate is received into TK-101 on level control. LIC101 is a',
    'cascade master: it holds tank level by setting the flow setpoint of',
    'FIC102. That setpoint is limited to 80 M3/H because that is where R-201',
    'runs out of jacket cooling. TK-101 is a surge vessel: it takes the swing',
    'in supply so the reactor does not have to. Read its trend against FI100',
    'before you move anything.',
    '',
    'P-101 takes suction from the tank. Below 2 percent tank level it is',
    'tripped to protect it. That is a protection, not a nuisance. If you have',
    'hit it, you had already lost the tank. At the other end, 98 percent is an',
    'overflow interlock that isolates the feed supply and the unit loses',
    'production.',
    '',
    'R-201 is the conversion reactor: a well-stirred, jacket-cooled vessel',
    'running at about 150 DEG C. Two things about it matter more than',
    'everything else combined.',
    '',
    'First, it is temperature-controlled by a cascade. TIC201 measures reactor',
    'temperature and sets the setpoint of TIC202, which controls jacket',
    'coolant temperature through TV-202. If you break that cascade and drive',
    'the jacket by hand, you own the exotherm.',
    '',
    'Second, the reaction makes heat in proportion to how fast it is going,',
    'and it goes faster when it is hotter. That is positive feedback, and it',
    'is why this reactor has a hard trip at 185 DEG C which closes the feed',
    'valve. It does not reset until the reactor falls back to 160 DEG C. When',
    'you see reactor temperature rising with the jacket already cold and wide',
    'open, CUT FEED. You remove heat by removing reactants, not by asking the',
    'cooling water for something it does not have. Then watch TK-101, because',
    'feed is still arriving at the battery limit and the tank will fill.',
    'Cut feed to arrest the exotherm, then put it back. If you let TIC201',
    'fall past its Low alarm at 140 DEG C the reaction goes out, and there is',
    'no relight on this board: R-201 has no heater.',
    '',
    'AI205 reads conversion, nominally 85 percent, target band 75 to 95. It',
    'falls when the reaction is going out and it climbs above the band when',
    'the reactor is running away. Read it with TIC201, never alone.',
    '',
    'Reactor effluent is heated in E-301 and let down into V-401, the hot',
    'flash drum. E-301 is a PREHEATER on hot oil, not a cooler. It raises the',
    'effluent from reactor temperature to flash temperature, about 180 DEG C,',
    'so that light ends and reaction water go overhead and crude hydrocarbon',
    'liquid stays in the bottom. Open TV-301 further and the drum gets hotter',
    'and makes more vapour. TIC301 is the controller on that duty.',
    '',
    'LIC401 holds the drum level with LV-401; PIC401 holds the pressure with',
    'PV-401 at about 600 KPA. The level in V-401 is the liquid seal between',
    'the drum and the liquid line. On a real drum, losing it puts gas into',
    'the product line; this board does not model the blow-by, but the low',
    'level alarms are rationalised as if it did. Flood it and liquid',
    'carries over into the overhead. The relief valve lifts at 950 KPA and',
    'reseats below 900; lifting it is a reportable event, not a control',
    'action.',
    '',
    'E-301 fouls. It fouls slowly all the time and there is nothing you can do',
    'about the baseline. What you notice first is TIC301 output climbing',
    'across a shift to hold the same outlet temperature. That output is the',
    'whole tell: with TIC301 in AUTO nothing else moves. Leave TIC301 in MAN',
    'and the flash goes cold instead, less vapour, and PIC401 output backs',
    'off toward its low limit.',
    '',
    'Crude liquid from V-401 goes to intermediate storage. Overhead vapour and',
    'reaction water go off plot to the light ends and condensate header.',
    '',
    'UNIT TWO BATCH CAMPAIGN REACTOR',
    '',
    'R-202 is a jacketed semi-batch reactor with a dosed monomer feed, run',
    'under sequence control by SCM202. It is not in the',
    'fuel train. It is a campaign unit that shares this board, and boards',
    'covering a continuous train plus a campaign batch unit are ordinary.',
    '',
    'The sequence runs CHARGE, HEATUP, FEED, REACT, COOL, DRAIN, IDLE. During',
    'FEED the dose flow FIC211 belongs to the PROGRAM: the sequence owns it,',
    'and a manual write will be rejected. That rejection is the interlock',
    'working, not a fault.',
    '',
    'TIC212 measures batch temperature and cascades to TIC213 on the jacket',
    'medium. The hazard is accumulated unreacted feed: monomer that has been',
    'charged but has not yet reacted is stored energy, and TI216 reads the',
    'adiabatic end temperature it would reach if the cooling stopped. Watch',
    'TI216, not just TIC212. The batch trips at 110 DEG C and does not reset',
    'until 70. On this board the TI216 Urgent interlock sheds the feed first,',
    'so the trip is the backstop behind it, not the thing you will see.',
    'Losing the agitator M202 during FEED is the worst case: the contents',
    'stop mixing while feed is still going in.',
    '',
    'PI214 reads vapour pressure and LI215 reads batch level.',
    '',
    'UNIT THREE HYDROFINISHING',
    '',
    'Crude liquid is drawn on FIC310, fired to reaction temperature in H-310,',
    'and passed over the fixed catalyst bed in R-310, where hydrogen saturates',
    'residual unsaturates and removes residual oxygen. The hydrogen itself is',
    'a boundary condition here: there is no hydrogen rate, purity or reactor',
    'pressure point on this board, and R-310 is modelled on the thermal side.',
    '',
    'H-310 is a two-pass fired heater. It has two independent hazards and they',
    'are not the same thing.',
    '',
    'The process hazard is outlet temperature, TIC311, which strokes the fuel',
    'valve directly. There is no cascade on it.',
    '',
    'The equipment hazard is TUBE SKIN TEMPERATURE. TI314 reads pass 1 and',
    'TI315 reads pass 2. Both skins run hotter than the mixed outlet and pass',
    '2 runs hotter than pass 1, so watch them against the outlet. On this',
    'heater the bed will normally trip before either skin does; the skin trip',
    'is the backstop if firing is pushed with the bed cold. The two passes do',
    'not share limits: pass 1 is',
    'High at 440 and Urgent at 490 DEG C, pass 2 is High at 450 and Urgent at',
    '500. The tube-skin trip fires when EITHER pass reaches its own Urgent',
    'limit, and it closes the fuel valve. It does not reset until BOTH skins',
    'are back below 400 DEG C.',
    '',
    'AI316 reads excess oxygen in the flue gas. Below about 1.5 percent you',
    'are approaching incomplete combustion, and that is a firebox problem,',
    'not a temperature problem.',
    '',
    'R-310 is a fixed bed with exothermic reactions in it, which means it has',
    'a HOT SPOT: a point inside the bed hotter than either end. TI312 reads',
    'it. The hot spot moves, and it grows faster than linearly with inlet',
    'temperature — a 10 DEG C rise at the heater outlet is not a 10 DEG C rise',
    'in the bed. It is High at 440 and trips at 480 DEG C, shutting off fuel',
    'gas, and does not reset until 400.',
    '',
    'FIC313 is the bed quench, and it is the fast handle on the hot spot: it',
    'cools the bed directly and acts in seconds, and TIC311 will not move',
    'when you use it, because the quench goes to the bed, not the heater',
    'outlet. When TI312 starts to climb, RAISE QUENCH to buy time, then back',
    'off TIC311 and FIC310, because the heat is still being made in the bed',
    'and quench only carries it away.',
    '',
    'UNIT FOUR SEPARATION',
    '',
    'What leaves Unit Three is three things in one line: finished hydrocarbon',
    'liquid, the water the hydrofinishing made, and a little light gas. Unit',
    'Four takes them apart. It is the last thing on your board before the',
    'product goes to storage.',
    '',
    'E-502 is a trim cooler on cooling water. TIC502 holds the separator inlet',
    'at 45 DEG C through TV-502, and more controller output is more cooling.',
    '',
    'V-502 is a horizontal separator with a WEIR PLATE across it, which makes',
    'two chambers out of one vessel. The mixed liquid enters the FIRST chamber',
    'and sits there long enough for the water to settle out under the oil.',
    'LIC504 draws that water off the bottom through WV-504 and holds the',
    'interface at 25 percent. The oil floats on top of it, reaches the crest of',
    'the weir and overflows into the SECOND chamber, where LIC503 holds the',
    'level and sends product to storage through LV-503. Gas leaves overhead on',
    'pressure control: PIC505 holds 800 KPA with PV-505. Forget the recycle,',
    'there is none on this board. The gas simply leaves.',
    '',
    'The two liquid draws fail CLOSED and the two vapour-side valves fail OPEN.',
    'On an instrument air loss V-502 stops drawing water and stops drawing',
    'product, and goes on cooling and venting.',
    '',
    'THE WEIR HEIGHT IS SETTABLE. It is an instructor variable, not an operator',
    'handle: 55 percent of vessel height by default, adjustable from 30 to 90.',
    'It fixes how deep the oil layer sits over the interface in chamber 1,',
    'which is the same as saying it fixes how much room the interface has',
    'before water starts going over the crest.',
    '',
    'There are two ways to get the interface wrong and they fail in opposite',
    'directions. Interface TOO HIGH, up near the crest: water goes over the',
    'weir with the oil. AI509 reads water in the oil draw, High at 2 percent',
    'and Urgent at 5, and the liquid going to storage is off-spec. Nothing on',
    'the separator itself looks wrong. Quiet here, loud downstream.',
    '',
    'Interface TOO LOW, a thin water layer: the water draw pulls oil down under',
    'the interface and out with the water. AI510 reads oil in the water draw.',
    'That is an environmental excursion in the process water, not a process',
    'upset, and it carries a High alarm only.',
    '',
    'LIC504 is High at 40 percent and Urgent at 48. Those limits are about the',
    'crest, not about the vessel. Both analysers lag the interface that makes',
    'them by about half a minute, so when you correct an excursion watch LIC504',
    'come back FIRST and read AI509 or AI510 after it.',
    '',
    'The trap on this unit: RAISE THE WEIR AND CHAMBER 2 STARVES. Raise the',
    'crest and chamber 1 has to fill to the new level before anything overflows',
    'again. Meanwhile chamber 2 keeps draining to the product line, LIC503',
    'falls, and the loop closes LV-503 to protect the draw. That is a product',
    'interruption no operator caused with a valve, and the level comes back on',
    'its own once chamber 1 reaches the new crest. Lower the weir and the',
    'opposite happens: the oil layer dumps over and LIC503 swings. Read the',
    'weir height before you blame LV-503.',
    '',
    'Inlet temperature couples into the pressure. Run the inlet warm and more',
    'light gas breaks out, so PIC505 rises and PV-505 opens; the liquid split',
    'does not change with temperature in this model, so the interface holds',
    'while the vent margin shrinks. The relief valve PSV-502 lifts at 1100',
    'KPA and reseats below 1000. Lifting it is a reportable event, not a',
    'control action.',
    '',
    'How the separation itself is modelled: as gravity settling, represented by',
    'a declared correlation. The overflow over the weir follows the classic',
    'open-channel weir form. The two carry-over curves are this simulator\'s own',
    'shape, chosen so that each failure mode appears at the right interface',
    'height with the right time constant. There is no droplet size, no',
    'rise-velocity calculation and no phase equilibrium behind any of it.',
    '',
    'WHAT IS NOT SIMULATED',
    '',
    'Be clear about the edges of this trainer. The following are real parts of',
    'a plant like this and are NOT on your board:',
    '',
    'Carbon dioxide capture, compression and drying. Water electrolysis and',
    'the oxygen it co-produces. Hydrogen compression and purification. The',
    'crude oxygenate synthesis itself. All of these are upstream of the',
    'battery limit and are stated as boundary conditions, not modelled.',
    '',
    'Unit Four now does the separation, and only the separation. There is',
    'still no recycle gas compressor, no make-up hydrogen, no purge and no',
    'stabiliser column: the gas that leaves V-502 overhead goes off plot and',
    'does not come back, so nothing recycles into Unit Three. Finished liquid',
    'leaves to storage as a boundary stream, and the light ends and reaction',
    'water leaving V-401 are still accounted off plot.',
    '',
    'Inside V-502 the settling is a correlation, not a calculation. There is no',
    'property package and no flash solver anywhere on this board, so nothing',
    'here computes a phase split from composition. The weir overflow follows a',
    'published open-channel form, but the SHAPE of both carry-over curves — how',
    'quickly water starts going over the crest, how quickly oil starts going',
    'under the interface — is invented for training. The settling criterion is',
    'named rather than derived: no droplet size, no rise velocity, no',
    'retention-time check.',
    '',
    'Hydrogen rate, purity and reactor pressure in Unit Three: R-310 is',
    'modelled on the thermal side only. Gas blow-by through LV-401 is not',
    'modelled, and PI214 follows batch temperature rather than a vapour',
    'pressure curve; their alarms are rationalised for the real hazard, not',
    'reproduced by the board.',
    '',
    'Unit Two is a campaign reactor and is deliberately not part of the fuel',
    'train. Its chemistry is a semi-batch polymerisation and it is on this',
    'board to teach sequence control, PROGRAM mode, phase-based alarm limits',
    'and HOLD and ABORT.',
    '',
    'HOW GOOD ARE THE NUMBERS',
    '',
    'Each unit is a published model re-implemented from its equations, not a',
    'proprietary correlation and not a fitted curve. They are good enough to',
    'behave correctly in direction, magnitude and time constant, and to make',
    'the right operator action the one that works. They are NOT a process',
    'design tool. There is no property package, no flash solver and no',
    'composition tracking. Do not size equipment from this board.',
    ''
  ].join('\n');
  /* PROCESS-TEXT-END */

  // Every point tag the prose above names. tests/process-text.test.js asserts
  // each one exists in the runtime point list AND that this file's prose does
  // not contradict the point's configured description.
  var TAGS_NAMED = [
    'FI100', 'LIC101', 'FIC102', 'TIC201', 'TIC202', 'AI205', 'TIC301',
    'LIC401', 'PIC401',
    'FIC211', 'TIC212', 'TIC213', 'PI214', 'LI215', 'TI216',
    'FIC310', 'TIC311', 'TI312', 'FIC313', 'TI314', 'TI315', 'AI316',
    'TIC502', 'LIC503', 'LIC504', 'PIC505', 'AI509', 'AI510'
  ];

  var SOURCES = [
    { name: 'Henson and Seborg exothermic CSTR (APMonitor PDC / pc-gym)',
      use: 'R-201 conversion reactor: first-order Arrhenius kinetics, lumped jacket' },
    { name: 'Kantor CBE30338 notes',
      use: 'the R-201 jacket energy balance' },
    { name: 'LearnChemE flash drum',
      use: 'V-401 hot flash: vapour fraction rising with feed temperature' },
    { name: 'Lucia, Finkler and Engell semi-batch polymerization (do-mpc)',
      use: 'R-202: monomer/polymer/water balances, gel factor, adiabatic end temperature' },
    { name: 'Badgwell fired heater case study (APMonitor)',
      use: 'H-310: fuel gas to firebox, two tube passes with outlet and skin temperatures' },
    { name: 'LearnChemE PFR parametric sensitivity with heat exchange',
      use: 'R-310: exponential hot-spot growth in the fixed bed' },
    { name: 'Arnold and Stewart, Surface Production Operations volume 1 (Gulf Professional)',
      use: 'V-502: the bucket-and-weir three-phase separator layout, oil over a settled water leg' },
    { name: 'API Specification 12J, Oil and Gas Separators',
      use: 'V-502: retention time and chamber sizing as the basis of the settling correlation' },
    { name: 'Francis weir formula (open-channel hydraulics, public domain)',
      use: 'the V-502 weir: overflow rising with the 3/2 power of the head over the crest' }
  ];

  var FIDELITY = {
    modelled: [
      'Process dynamics in direction, magnitude and time constant',
      'Exothermic runaway and the jacket-margin limit on R-201',
      'Two-pass fired heater with independent tube-skin behaviour',
      'Fixed-bed hot spot growing faster than linearly with inlet temperature',
      'Flash vapour fraction as a function of feed temperature',
      'Exchanger fouling as a slow loss of duty',
      'Semi-batch sequence control with accumulated-feed hazard',
      'Two-chamber weir separation with a settable weir, and both interface failure modes'
    ],
    notModelled: [
      'Composition tracking of any kind',
      'A property package or a flash solver',
      'Carbon dioxide capture, electrolysis and hydrogen supply (boundary conditions)',
      'Recycle gas, make-up hydrogen, purge and product recovery downstream of Unit Four',
      'Droplet settling: the V-502 carry-over curves are a declared correlation, not a rise-velocity calculation',
      'Compressor surge'
    ],
    ceiling: 'Behavioural fidelity for operator training. Not a process design tool. '
           + 'Do not size equipment, rate exchangers or set real trip points from this board.'
  };

  function text() { return TEXT; }

  function tagsNamed() { return TAGS_NAMED.slice(); }

  function fidelity() {
    return {
      modelled: FIDELITY.modelled.slice(),
      notModelled: FIDELITY.notModelled.slice(),
      ceiling: FIDELITY.ceiling
    };
  }

  function sources() { return SOURCES.map(function (s) { return { name: s.name, use: s.use }; }); }

  // Split TEXT on its own ALL-CAPS headings, using the SAME rule serve.py:305
  // applies, so the operator's dialog and PIP's context can never disagree
  // about where a section starts.
  function isHeading(line) {
    var t = line.trim();
    if (!t || t.length >= 40) return false;
    if (t !== t.toUpperCase()) return false;
    return /^[A-Za-z ]+$/.test(t);
  }

  function sections() {
    var out = [];
    var cur = null;
    var lines = TEXT.split('\n');
    for (var i = 0; i < lines.length; i++) {
      if (isHeading(lines[i])) {
        if (cur) out.push({ title: cur.title, body: cur.body.join('\n').trim() });
        cur = { title: lines[i].trim(), body: [] };
      } else if (cur) {
        cur.body.push(lines[i]);
      }
    }
    if (cur) out.push({ title: cur.title, body: cur.body.join('\n').trim() });
    return out;
  }

  return {
    text: text,
    sections: sections,
    tagsNamed: tagsNamed,
    fidelity: fidelity,
    sources: sources
  };
});
