// @artifact production
/*
 * ESS.AlarmHelp — alarm rationalisation table (Alarm Help) for every alarm
 * condition in the simulator.
 *
 * The six fields follow the rationalisation pop-up described in the PAS /
 * Hollifield white papers (RESOURCES 2.10): Priority, Setting, Response time,
 * Consequence, Probable cause, Corrective action. The idea of an Alarm Help
 * pane beside the Alarm Summary comes from the Experion Alarming PIN feature
 * list (RESOURCES 2.2). All prose here is our own and describes this
 * simulator's process models (CODE-MAP section 2.6), not any real plant.
 *
 * Priority and Setting are never authored twice: `resolve()` builds them from
 * the live point configuration passed in by the app (`cfg`), so the help can
 * never disagree with the trip point or priority the operator sees elsewhere.
 * Equipment-level trips (TK-101, R-201, ...) are not in the tag database, so
 * their settings live in EQUIPMENT_TRIPS and are exported for the app to use as
 * trip values.
 *
 * API
 *   resolve(tag, cond, cfg) -> { found, tag, cond, priority, setting,
 *       responseTime, consequence, probableCause, correctiveAction }
 *     cfg (optional): { prio, subprio, tripPoint, eu, kind }
 *   has(tag, cond) -> boolean
 *   keys() -> ['TAG.COND', ...]
 *   EQUIPMENT_TRIPS -> { 'TK-101.HIHI TRIP': { value, eu, prio }, ... }
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).AlarmHelp = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Equipment-level protective trips raised by the process models. The values
  // are the model thresholds listed as fixed in UPGRADE-PLAN rule 4.
  var EQUIPMENT_TRIPS = {
    'TK-101.HIHI TRIP': { value: 98, eu: '%', prio: 'Urgent' },
    'R-201.HI TEMP TRIP': { value: 185, eu: 'DEG C', prio: 'Urgent' },
    'V-401.PSV LIFT': { value: 950, eu: 'KPA', prio: 'Urgent' },
    'R-202.HI TEMP TRIP': { value: 110, eu: 'DEG C', prio: 'Urgent' },
    'R-310.HI TEMP TRIP': { value: 480, eu: 'DEG C', prio: 'Urgent' },
    'H-310.TUBE SKIN TRIP': { value: 500, eu: 'DEG C', prio: 'Urgent' },
    'V-502.PSV LIFT': { value: 1100, eu: 'KPA', prio: 'Urgent' }
  };

  // Response time bands used across the table. Urgent conditions get minutes,
  // Low conditions get the length of a normal round.
  var RT = { now: 'Immediately (under 2 min)', short: '5 min', medium: '10 min', long: '30 min' };

  function e(rt, cons, cause, act, setting) {
    var o = { rt: rt, cons: cons, cause: cause, act: act };
    if (setting) o.setting = setting;
    return o;
  }

  var TABLE = {
    // ---- Unit 01: feed tank TK-101 -------------------------------------------
    'LIC101.PVLL': e(RT.now,
      'Feed pump P-101 loses suction and cavitates; below 2 % level the pump trips and reactor feed stops, and R-201 cools as the reaction runs down.',
      'Feed supply FI100 lost or reduced; FV-102 driven fully open in MAN; level transmitter failure reading low.',
      'Put FIC102 in MAN and reduce outlet flow, read FI100 (an indication; the supply is not under station control), and stop P-101 before the level reaches 2 % if the supply does not return.'),
    'LIC101.PVLO': e(RT.medium,
      'Loss of surge capacity; a further supply dip will reach the low-low trip.',
      'Supply flow FI100 running below the 60 M3/H design point; LIC101 setpoint moved down; outlet flow above supply.',
      'Check FI100 against FIC102, trim the LIC101 setpoint or move FIC102 to AUTO with a lower setpoint to hold inventory.'),
    'LIC101.PVHI': e(RT.medium,
      'Tank approaches the overflow interlock; feed to the reactor may have to be raised beyond the reactor cooling capacity to catch up.',
      'Feed surge on FI100; FV-102 stuck or throttled; FIC102 in MAN with a low output; pump P-101 stopped or tripped.',
      'Confirm P-101 is running, raise FIC102 flow (AUTO or CAS), and check FV-102 position against output.'),
    'LIC101.PVHH': e(RT.now,
      'At 98 % the overflow protection isolates the feed supply and the unit loses production; a real tank would spill to the bund.',
      'Same causes as PVHI left unattended; outlet valve failed closed on instrument air loss.',
      'Open FV-102 by hand from the FIC102 faceplate in MAN and verify P-101 status; FI100 supply is not under station control.'),
    'FIC102.PVLL': e(RT.now,
      'Reaction rate falls with the reactant feed: R-201 cools, conversion collapses, and TK-101 fills toward its high level while supply keeps arriving.',
      'P-101 tripped; FV-102 closed or stuck; TK-101 empty; transmitter failure reading zero.',
      'Restart P-101 when the restart lockout clears and open FV-102 in MAN; restore feed before TIC201 falls past 140 DEG C, because the reaction does not relight on this board.'),
    'FIC102.PVLO': e(RT.short,
      'Less reactant reaches R-201; residence time rises, conversion drifts and the reactor cools slightly.',
      'Cascade output from LIC101 low; valve stiction on FV-102; suction pressure low from a low tank level.',
      'Compare OP with the valve position, check the TK-101 level, and consider MAN control of FIC102 while the cause is fixed.'),
    'FIC102.PVHI': e(RT.short,
      'Reactor over-fed; conversion drops and downstream V-401 level and pressure rise.',
      'LIC101 driving hard after a feed surge; FIC102 in MAN with a high output.',
      'Reduce the LIC101 setpoint or take FIC102 to AUTO with a normal setpoint; watch LIC401 and PIC401.'),
    'FIC102.PVHH': e(RT.now,
      'Reactor hydraulically flooded; carry-over to E-301 and V-401 with a pressure excursion toward the PSV.',
      'FV-102 stuck open, or an operator output error in MAN.',
      'Close FV-102 in MAN, verify PIC401 is in AUTO and the flare path is clear.'),
    'FIC102.BADPV': e(RT.short,
      'The loop sheds to MAN and holds the last output; the level cascade is broken so TK-101 will drift.',
      'Transmitter failure on the feed flow; impulse line blocked or loop power lost.',
      'Control FV-102 by hand using LIC101 and FI100 as the reference, and request maintenance on the transmitter.'),
    'P101.TRIP': e(RT.now,
      'Reactor feed stops; TK-101 fills toward the HIHI trip and R-201 cools as the reaction runs down.',
      'Pump electrical fault; suction loss from a low tank level.',
      'Check the trip reason on the P101 faceplate, wait for the 30 s restart lockout, confirm the TK-101 level permissive, then START.'),
    'P101.CMDFAIL': e(RT.short,
      'The pump stays stopped; feed cannot be restored until the permissive clears.',
      'Start requested with the TK-101 level below the 5 % permissive.',
      'Restore the tank level above 5 % (reduce FIC102 flow and wait for FI100 supply, which is not under station control) and repeat the START command.'),
    'TK-101.HIHI TRIP': e(RT.now,
      'Feed supply is isolated by the overflow interlock; the unit loses feed until the level falls below 90 %.',
      'Tank level reached 98 % because the outlet could not keep up with the inflow.',
      'Raise the outlet flow with FIC102, confirm P-101 running, and acknowledge the trip once the level is falling.',
      '98 % level'),

    // ---- Unit 01: reactor R-201 ------------------------------------------------
    'TIC201.PVLL': e(RT.short,
      'The reaction is out. Near its Low alarm at 140 DEG C it stops relighting on this board: R-201 has no heater, and conversion goes to zero.',
      'Feed cut and not restored; cooling water loss recovered with TV-202 still wide open; TIC202 cascade wound down.',
      'If TIC201 is still falling through the 130s, restore feed and the normal jacket setpoint at once; once it is out the run is lost and the unit needs a fresh start.'),
    'TIC201.PVLO': e(RT.short,
      'The reaction is going out: conversion falls, and below about 140 DEG C it cannot be restarted on this board.',
      'Feed cut to arrest an exotherm and left cut; setpoint lowered; jacket over-cooling.',
      'Restore feed now if it was cut, verify the TIC201 setpoint and mode, and ease the jacket warmer through the cascade.'),
    'TIC201.PVHI': e(RT.short,
      'The exotherm accelerates with temperature; without action the reactor reaches the 185 DEG C trip.',
      'Cooling water loss, TV-202 stiction, or a reaction rate step.',
      'Confirm TIC202 output is opening TV-202, then reduce feed flow FIC102 toward 20 % output to remove reaction heat. Never add feed to a rising reactor.'),
    'TIC201.PVHH': e(RT.now,
      'Runaway imminent; the trip will close the feed valve and the reactor contents will still need to be cooled.',
      'Same causes as PVHI with the jacket at its limit.',
      'Cut feed with FIC102 in MAN to zero, open TV-202 fully in MAN, and monitor the trend until the temperature is falling.'),
    'TIC201.DEVHI': e(RT.short,
      'The loop is not holding its setpoint; a growing deviation is the earliest sign of a cooling problem.',
      'Cascade secondary TIC202 not in CAS, valve stiction, or cooling capacity lost.',
      'Check TIC202 mode and its output-to-position match, then act as for TIC201 PVHI.'),
    'TIC202.PVLL': e(RT.long,
      'Journal only: jacket colder than expected; over-cooling reduces conversion.',
      'Cooling water supply colder than design or TV-202 fully open with a low load.',
      'No immediate action; review the cascade setpoint if the reactor temperature is also low.'),
    'TIC202.PVLO': e(RT.medium,
      'Jacket is over-cooling; reactor temperature will fall below its operating band.',
      'TIC202 in MAN with a high output; cascade driving cooling after a load step.',
      'Return TIC202 to CAS and let TIC201 restore the balance.'),
    'TIC202.PVHI': e(RT.short,
      'Jacket cannot remove the reaction heat; reactor temperature will rise.',
      'Cooling water loss, TV-202 stuck, or reaction load higher than design.',
      'Confirm cooling water is available, check TV-202 position, and reduce reactor load by cutting feed.'),
    'TIC202.PVHH': e(RT.now,
      'Cooling has effectively been lost; the reactor is heading for the high-temperature trip.',
      'Total loss of cooling water supply, or TV-202 stuck.',
      'Cut feed to R-201 (FIC102 to MAN, output low) to arrest the exotherm, open TV-202 by hand if it responds, then restore feed before TK-101 reaches high level and confirm TIC201 is falling.'),
    'TIC202.DEVHI': e(RT.short,
      'Jacket loop not following its cascade setpoint; reactor control will degrade.',
      'Valve stiction or saturation on TV-202; cooling water temperature above design.',
      'Compare output with valve position and stroke the valve in MAN if it is sticking.'),
    'R-201.HI TEMP TRIP': e(RT.now,
      'Feed valve FV-102 is driven closed by the interlock; production stops and the reactor must be cooled to below 160 DEG C before reset.',
      'Reactor temperature reached 185 DEG C after a cooling loss, stiction or reaction rate step.',
      'Keep maximum jacket cooling, confirm feed is isolated, acknowledge the trip, and restart only after the temperature has recovered.',
      '185 DEG C reactor temperature'),

    // ---- Unit 01: flash preheater E-301 and flash drum V-401 -------------------
    // E-301 HEATS reactor effluent on hot oil up to flash temperature (src/models.js
    // exchangerAndDrum: hxT rises with TV-301 opening; TIC301 is REV-acting, i.e. heating).
    // Opening TV-301 makes the drum hotter and more vapour. Fouling UNDER-heats: its tell is
    // TIC301 output climbing across a shift to hold the same outlet (about 47 to 84 % at the
    // modelled floor, foulF 0.6), and at that floor it reaches no TIC301 alarm on its own
    // (tests/golden-upsets.test.js records zero alarms for the foul upset). It never causes
    // a HIGH, and it belongs in no HIGH entry on this unit.
    'TIC301.PVLL': e(RT.long,
      'Journal only: the flash feed is too cold, V-401 makes little vapour, LIC401 works harder and drum pressure sags.',
      'TV-301 closed or the hot-oil supply cold; reactor outlet cold; TIC301 in MAN with the output low.',
      'No immediate action; check TIC301 output and mode, then review the setpoint. Fouling does not reach this alarm on its own; its tell is TIC301 output climbing across a shift.'),
    'TIC301.PVLO': e(RT.medium,
      'Flash duty drops; LIC401 will have to open LV-401 further and PIC401 output falls toward its low limit.',
      'Reactor temperature low; TIC301 in MAN with too little output.',
      'Check TIC301 mode and output, then the reactor temperature. Fouling does not reach this alarm on its own: its tell is TIC301 output climbing across a shift to hold the same outlet.'),
    'TIC301.PVHI': e(RT.short,
      'More vapour flashes in V-401; PIC401 opens PV-401 to hold pressure, and if PIC401 is in MAN or already wide open the drum pressure rises toward the PSV.',
      'TV-301 stuck open, or TIC301 in MAN with output too high; a reactor temperature excursion carried through the preheater.',
      'Cut heat: close TV-301 down by taking TIC301 to MAN and lowering the output, or lower the setpoint; watch PIC401 output for saturation.'),
    'TIC301.PVHH': e(RT.now,
      'Drum pressure will exceed PIC401 capacity; PSV lift likely.',
      'A reactor temperature excursion arriving at the flash with TV-301 open; the preheater alone cannot reach this limit.',
      'Cut heat first: close TV-301 (TIC301 to MAN, output down), reduce reactor feed, take PIC401 to AUTO if it is not, and prepare for a relief event.'),
    'LIC401.PVLL': e(RT.now,
      'Gas blow-by through LV-401 to the product line: the real hazard behind this limit; the board does not model the blow-by itself.',
      'LV-401 stuck open; liquid feed to the drum lost.',
      'Close LV-401 in MAN until the level recovers, then return LIC401 to AUTO.'),
    'LIC401.PVLO': e(RT.medium,
      'Reduced liquid seal; a further drop risks blow-by.',
      'LIC401 setpoint low; feed reduced upstream.',
      'Check the feed and the LIC401 setpoint.'),
    'LIC401.PVHI': e(RT.short,
      'Liquid carry-over into the overhead line and the flare.',
      'LV-401 stiction or failed closed on air loss; feed surge from the reactor.',
      'Open LV-401 in MAN and verify the valve stroke.'),
    'LIC401.PVHH': e(RT.now,
      'Drum floods and liquid enters the vapour system.',
      'Outlet valve failed closed; excessive feed.',
      'Cut reactor feed, open LV-401 by hand, and watch PIC401.'),
    'PIC401.PVLL': e(RT.short,
      'Loss of separation pressure; vapour product is lost to flare at low pressure.',
      'PV-401 stuck open; feed lost.',
      'Close PV-401 in MAN and confirm feed to the drum.'),
    'PIC401.PVLO': e(RT.medium,
      'Flash runs at reduced pressure; product quality drifts.',
      'PIC401 setpoint lowered; PV-401 over-open.',
      'Verify the setpoint and return PIC401 to AUTO.'),
    'PIC401.PVHI': e(RT.short,
      'Pressure approaching the PSV set pressure of 950 KPA.',
      'Vapour surge from a hot feed; PV-401 stuck or PIC401 in MAN; TIC301 driven high.',
      'Open PV-401 further in MAN, reduce TIC301 setpoint, and cut reactor feed if the pressure keeps rising.'),
    'PIC401.PVHH': e(RT.now,
      'PSV will lift to flare; flaring is an environmental event.',
      'Same causes as PVHI left unattended.',
      'Cut feed to R-201 and open PV-401 fully; expect V-401 PSV LIFT.'),
    'V-401.PSV LIFT': e(RT.now,
      'Relief to flare until pressure falls; the event must be reported.',
      'Drum pressure reached 950 KPA because PIC401 could not vent enough vapour.',
      'Reduce the vapour load (cut feed, cool the product), then confirm the PSV reseats and acknowledge.',
      '950 KPA drum pressure'),

    // ---- Unit 02: semi-batch reactor R-202 -------------------------------------
    'FIC211.PVLO': e(RT.short,
      'The FEED phase is running without monomer: the batch clock keeps counting, conversion stalls and the sequence will move to REACT with an under-charged reactor (limit active in FEED only, ISA-TR18.2.6 state-based pattern).',
      'MV-211 stuck or closed; FIC211 shed to MAN; supply lost; sequence held from another station.',
      'Check MV-211 position against output, return FIC211 to AUTO, or HOLD the sequence until the feed is available.'),
    'FIC211.PVHI': e(RT.short,
      'Monomer accumulates faster than it reacts; the adiabatic temperature rise potential grows.',
      'Setpoint too high for the FEED phase; MV-211 over-open in MAN.',
      'Reduce the FIC211 setpoint or place it in MAN at a lower output; check the monomer inventory bar.'),
    'TIC212.PVHI': e(RT.short,
      'Reaction accelerates with temperature; at 110 DEG C the batch trip cuts feed and floods the jacket with coolant.',
      'Agitator M-202 trip reduces heat transfer; jacket JV-213 stuck; monomer over-feed.',
      'Cut monomer feed with FIC211, confirm M-202 running, and reduce the TIC213 cascade setpoint.'),
    'TIC212.PVHH': e(RT.now,
      'Runaway imminent; the trip will force the sequence to COOL.',
      'Same causes as PVHI with the jacket at its limit.',
      'Cut monomer feed to zero, set TIC213 to MAN with full cooling, and be ready to ABORT the batch.'),
    'TIC213.PVHI': e(RT.short,
      'The jacket medium is heating rather than cooling the batch; reactor temperature will follow.',
      'TIC213 in MAN with a high output; cascade demanding heat during HEATUP for too long.',
      'Return TIC213 to CAS or reduce its output; check the SCM202 phase.'),
    'TI216.PVHI': e(RT.short,
      'If cooling were lost now, the unreacted monomer alone would carry the batch above the alarm value; the safety margin to the 110 DEG C trip is shrinking.',
      'Monomer fed faster than it reacts (high FIC211 setpoint, low batch temperature, agitator stopped, jacket too cold).',
      'Reduce the FIC211 setpoint or HOLD the sequence, confirm M-202 is running, and watch the monomer inventory bar fall before resuming.'),
    'TI216.PVHH': e(RT.now,
      'The accumulated monomer can reach the 110 DEG C trip on its own; the station sheds the monomer feed (FIC211 to MAN, MV-211 closed) and HOLDS the sequence automatically.',
      'Loss of agitation or cooling with the feed still running; an over-fed batch.',
      'Confirm the feed is shed and the sequence is HELD, restore agitation and jacket cooling; RESUME is refused until the Urgent alarm clears, then the SCM returns FIC211 to AUTO.'),
    'PI214.PVHI': e(RT.short,
      'Vapour pressure rising with batch temperature; a further rise threatens the vessel rating.',
      'Batch over-temperature; monomer inventory high.',
      'Act on TIC212 first: reduce temperature and cut monomer feed.'),
    'PI214.PVHH': e(RT.now,
      'Vessel pressure near its design limit; relief or rupture disc actuation likely.',
      'Uncontrolled exotherm.',
      'Cut monomer feed, full jacket cooling, ABORT the batch if the temperature is still rising.'),
    'LI215.PVLO': e(RT.short,
      'Reactor contents below the level expected for this phase: the agitator can draw air and the jacket area per unit volume changes the heat balance (limit active from HEATUP to COOL only).',
      'Leak or drain valve open; charge lost; level transmitter drift.',
      'Check the drain line and the DRAIN phase valve, then HOLD the sequence and inspect before continuing.'),
    'LI215.PVHI': e(RT.short,
      'Batch volume near the agitator and overflow limit; heat transfer per unit volume falls.',
      'Over-charge or over-feed of monomer.',
      'Stop the monomer feed with FIC211 and HOLD the sequence.'),
    'M202.TRIP': e(RT.now,
      'Loss of agitation halves heat transfer; a hot spot forms and the batch can run away with no warning from the bulk temperature.',
      'Agitator motor or drive fault.',
      'Cut monomer feed immediately, apply full jacket cooling, and restart M-202 when the lockout clears.'),
    'R-202.HI TEMP TRIP': e(RT.now,
      'Batch is forced to COOL: feed cut and the jacket flooded cold; the batch is lost.',
      'Batch temperature reached 110 DEG C.',
      'Confirm the monomer valve MV-211 is closed and the jacket is on full cooling, then acknowledge and prepare to DRAIN.',
      '110 DEG C batch temperature'),

    // ---- Unit 03: fired preheater H-310 and fixed-bed reactor R-310 -----------
    'FIC310.PVLO': e(RT.short,
      'Low feed through the preheater raises the outlet temperature for the same firing and reduces bed cooling.',
      'FV-310 stiction; upstream supply reduced.',
      'Check FV-310 position, and lower TIC311 firing until the flow is restored.'),
    'FIC310.PVHI': e(RT.medium,
      'Preheater outlet drops and conversion falls.',
      'FV-310 over-open in MAN.',
      'Return FIC310 to AUTO at the normal setpoint.'),
    'TIC311.PVLO': e(RT.medium,
      'Bed inlet too cold; reaction extinguishes and unconverted feed passes through.',
      'Fuel gas shut off by the R-310 trip; TIC311 in MAN with low firing.',
      'Check the R-310 trip status before raising firing; return TIC311 to AUTO.'),
    'TIC311.PVHI': e(RT.short,
      'Hot inlet feeds the bed exotherm; hotspot TI312 will rise.',
      'Firing too high; feed flow low.',
      'Reduce the TIC311 setpoint and confirm FIC310 flow.'),
    'TIC311.PVHH': e(RT.now,
      'Preheater tubes and the bed are both at risk; the bed trip at 480 DEG C follows.',
      'Runaway firing; TIC311 in MAN with a high output.',
      'Cut firing in MAN and raise quench flow FIC313.'),
    'TI314.PVHI': e(RT.short,
      'Pass 1 tube metal is above its continuous rating; coke forms inside the tube and creep life is consumed.',
      'Firing raised too fast; low feed flow FIC310 through the pass; flame impingement.',
      'Reduce the TIC311 setpoint or firing, confirm FIC310 flow, and let the skin cool before raising duty again.'),
    'TI314.PVHH': e(RT.now,
      'Tube rupture risk; at this value the tube-skin trip shuts off the fuel gas.',
      'Same causes as PVHI left unattended; firing pushed with the bed cold.',
      'Cut firing at TIC311 in MAN now, keep feed flowing through the tubes, and expect the H-310 TUBE SKIN TRIP.'),
    'TI315.PVHI': e(RT.short,
      'Pass 2 (the hotter pass) tube metal is above its continuous rating; coke forms inside the tube and creep life is consumed.',
      'Firing raised too fast; low feed flow FIC310 through the pass; flame impingement.',
      'Reduce the TIC311 setpoint or firing, confirm FIC310 flow, and let the skin cool before raising duty again.'),
    'TI315.PVHH': e(RT.now,
      'Tube rupture risk; at this value the tube-skin trip shuts off the fuel gas.',
      'Same causes as PVHI left unattended; firing pushed with the bed cold.',
      'Cut firing at TIC311 in MAN now, keep feed flowing through the tubes, and expect the H-310 TUBE SKIN TRIP.'),
    'AI316.PVLO': e(RT.short,
      'Sub-stoichiometric firing: unburnt fuel in the firebox, afterburning in the convection section and a tube-skin excursion follow.',
      'Fuel raised faster than the air register can follow; air register stuck; fuel gas heating value change.',
      'Slow the firing change, confirm the register is moving, and hold the TIC311 output until O2 recovers above 2 %.'),
    'H-310.TUBE SKIN TRIP': e(RT.now,
      'Fuel gas is shut off; the preheater cools and the bed reaction dies out; restart only after both tube skins are below 400 DEG C.',
      'A tube-skin temperature reached its Urgent limit (TI314 490 DEG C or TI315 500 DEG C).',
      'Confirm firing is off and feed is still flowing through the tubes, acknowledge, and plan the relight at reduced duty.',
      '500 DEG C tube skin (TI314 490 / TI315 500)'),
    'TI312.PVHI': e(RT.short,
      'Hotspot growing; catalyst sinters above the trip and the reactor is lost for the run.',
      'Catalyst activity step after a regeneration or a fresh charge; low quench; high inlet temperature.',
      'Raise the quench flow FIC313, lower the TIC311 setpoint, and watch the hotspot trend.'),
    'TI312.PVHH': e(RT.now,
      'At 480 DEG C the fuel gas is shut off; the bed continues to react on stored heat.',
      'Same causes as PVHI left unattended.',
      'Maximum quench, cut firing in MAN, and reduce fresh feed to remove the reactant.'),
    'FIC313.PVLO': e(RT.short,
      'Reduced quench lets the bed hotspot rise.',
      'QV-313 stiction; FIC313 in MAN.',
      'Check the valve position and return FIC313 to AUTO.'),
    'FIC313.PVLL': e(RT.now,
      'Quench lost; the bed will overheat within minutes.',
      'QV-313 stuck closed; quench supply lost.',
      'Open QV-313 in MAN, reduce TIC311 firing and the fresh feed.'),
    'R-310.HI TEMP TRIP': e(RT.now,
      'Fuel gas is shut off; the preheater cools and the bed reaction dies out; restart only after the bed is below 400 DEG C.',
      'Bed hotspot reached 480 DEG C.',
      'Keep quench at maximum, confirm firing is off, acknowledge, and plan the restart.',
      '480 DEG C bed hotspot'),

    // ---- Unit 04: two-chamber weir separator V-502 ---------------------------
    // The unit is a horizontal three-phase separator split by a weir plate
    // (src/models.js stepU4, RESOURCES 4.12). Unit 03 effluent is trimmed to
    // 45 DEG C in E-502 (TIC502 -> TV-502; MORE output is MORE cooling water),
    // then water settles under the oil in chamber 1 and is drawn from the bottom
    // on interface control (LIC504 -> WV-504) while the oil overflows the weir
    // into chamber 2, whose level goes to the product draw (LIC503 -> LV-503).
    // Gas leaves overhead on pressure control (PIC505 -> PV-505).
    // Two failure modes, and they are mirror images of each other:
    //   interface HIGH, within carryBand of the crest -> water over the weir
    //     -> AI509 rises -> product off-spec (quiet here, loud downstream);
    //   interface LOW, thinner than thinBand -> the water draw pulls oil
    //     -> AI510 rises -> a process-water excursion.
    // The weir height is an instructor variable, not an operator handle, and it
    // is the first thing to read when chamber 2 starves: raising the weir stops
    // the overflow until chamber 1 fills to the new crest, and LIC503 closes
    // LV-503 on a level fall no operator caused with a valve.
    // Fail-safe: TV-502 and PV-505 fail OPEN (cooling and venting on air loss);
    // LV-503 and WV-504 fail CLOSED (both liquid draws shut).
    // The analysers AI509 and AI510 are lagged about 30 s behind the interface
    // that makes them, so the interface is the recovery to watch, not the reading.
    'TIC502.PVLO': e(RT.medium,
      'The separator runs cold. Below the 45 DEG C design nothing downstream changes in this model: the gas make does not fall, so PIC505 and PV-505 hold, and the interface and both levels are untouched. What the alarm tells you is that TV-502 is putting on more cooling than the feed needs, which is a TIC502 control problem and cooling-water duty wasted, not a separation problem.',
      'TV-502 driven wide open (it fails open, so an air loss or a MAN output at 100 % puts full cooling on); cooling water colder than design; Unit 03 running cool so the feed arrives cold.',
      'Compare the TIC502 output with the TV-502 position, return TIC502 to AUTO at 45 DEG C, and check the Unit 03 outlet before blaming the trim cooler.'),
    'TIC502.PVHI': e(RT.short,
      'Hot feed to V-502: more light gas flashes off, so PIC505 climbs and PV-505 opens toward its limit; the liquid split is unchanged, so the interface holds while the vent margin shrinks.',
      'TV-502 closed or stuck; cooling water lost; TIC502 in MAN with too little output; a Unit 03 temperature excursion carried through to the separator inlet.',
      'Open TV-502 (TIC502 to AUTO at 45 DEG C, or MAN with the output up), confirm cooling water is available, and watch PIC505 output for saturation.'),
    'TIC502.PVHH': e(RT.now,
      'Pressure climbs toward the PSV-502 lift at 1100 KPA: the gas make doubles at 40 DEG C above design and keeps rising with it, and once PV-505 is wide open nothing but the relief valve holds the vessel.',
      'Cooling water lost with TV-502 unable to help, or a Unit 03 temperature excursion arriving at the separator.',
      'Full cooling on TV-502 (TIC502 to MAN, output 100), cut the Unit 03 feed FIC310 to reduce the heat arriving, and confirm PIC505 is in AUTO with PV-505 opening before the relief lifts.'),
    'LIC503.PVLL': e(RT.now,
      'Chamber 2 is nearly empty: the product draw loses its liquid seal and LIC503 closes LV-503 to protect it, interrupting product to storage.',
      'Read the weir first. If the weir has been raised, chamber 1 is below the new crest and nothing is overflowing into chamber 2; the alternatives are LV-503 stuck open and feed to the separator lost upstream.',
      'Check the weir height and the chamber 1 level before blaming LV-503: after a weir raise the level returns on its own once chamber 1 fills to the new crest. Otherwise close LV-503 in MAN until the level recovers, then confirm the Unit 03 feed.'),
    'LIC503.PVLO': e(RT.medium,
      'Reduced seal on the product draw; a further fall reaches the low-low limit and the draw is interrupted.',
      'Weir raised, so less oil overflows into chamber 2 until chamber 1 fills to the new crest; LV-503 drawing faster than the overflow feeds it; feed reduced upstream.',
      'Check the weir height and chamber 1 first, then compare LV-503 position with the LIC503 output, and reduce the draw or lower the setpoint until the overflow re-establishes.'),
    'LIC503.PVHI': e(RT.short,
      'Chamber 2 is filling faster than the product draw removes it. The overflow is one way, so chamber 1 and the interface are untouched; what is at risk is product to storage, which is not keeping up with what the weir delivers.',
      'LV-503 stiction or failed closed on instrument air loss (it is a fail-closed valve, so an air loss shuts the product draw); LIC503 in MAN with too little output; the weir lowered, dumping the oil layer over.',
      'Open LV-503 in MAN and verify the stroke, then return LIC503 to AUTO. If the weir was just lowered, expect one swing and let the loop settle rather than chasing it.'),
    'LIC503.PVHH': e(RT.now,
      'Chamber 2 floods: the level pins at the top of the vessel and the overflow the weir delivers has nowhere to go, so product is lost. Chamber 1, the interface and the pressure are not disturbed in this model; the failure is the product draw.',
      'LV-503 stuck closed or shut on an air loss with feed still arriving; LIC503 left in MAN with the output low.',
      'Open LV-503 by hand, cut the Unit 03 feed FIC310 if it does not respond, and watch LIC503 for the recovery.'),
    'LIC504.PVLL': e(RT.now,
      'The water layer is too thin to seal the water draw: WV-504 pulls oil under the interface, AI510 climbs and hydrocarbon leaves in the process water. Environmental, not a process upset on the separator.',
      'WV-504 open too far (LIC504 in MAN with a high output); lower water make from Unit 03 (the water is made by the hydrofinishing reaction, so a feed cut or a deactivated bed shows here first).',
      'Close WV-504 down (LIC504 to AUTO at 25 %, or MAN with a lower output), watch LIC504 recover and AI510 fall about half a minute behind it, and check the Unit 03 feed and bed if the layer keeps thinning.'),
    'LIC504.PVLO': e(RT.medium,
      'The interface is approaching the thin-layer band where the water draw starts to pull oil; AI510 begins to rise before the low-low limit is reached.',
      'WV-504 over-open; less water being made upstream (a deactivated R-310 bed, since the reaction makes the water, or a Unit 03 feed cut).',
      'Reduce the LIC504 output or return it to AUTO at 25 %, and read AI510 with it rather than on its own.'),
    'LIC504.PVHI': e(RT.short,
      'The interface is climbing toward the weir crest; inside the last 10 % of height below the crest, water starts going over the weir with the oil, AI509 rises and the product goes off-spec. Quiet here, loud downstream.',
      'WV-504 stuck or shut (it fails closed on instrument air loss, so an air loss stops the water draw); LIC504 in MAN with too little output; more water arriving after a Unit 03 activity step.',
      'Open WV-504 in MAN and verify the stroke, return LIC504 to AUTO at 25 %, and read AI509 as the consequence: the interface is the cause and it is what you fix.'),
    'LIC504.PVHH': e(RT.now,
      'Water is going over the weir into the product chamber: AI509 rises, the liquid to storage carries free water, and the separator itself still looks normal on the graphic.',
      'Same causes as PVHI left unattended; WV-504 failed closed; the weir lowered toward the interface so the crest is nearer than it was.',
      'Open WV-504 fully in MAN, and cut the Unit 03 feed FIC310 if the interface is still rising. The weir is the slow handle, not the fast one: raising it moves the crest away from the interface but starves chamber 2 until chamber 1 refills. Confirm LIC504 is falling before returning it to AUTO.'),
    'PIC505.PVLL': e(RT.now,
      'The separator has vented more gas than the process makes and the gas blanket is lost. The liquid draws do not depend on the vessel pressure in this model, so the levels hold; what is gone is the margin over the 100 KPA off-gas header, and at the header pressure the vent passes nothing at all, so PIC505 has nothing left to hold with.',
      'PV-505 stuck open or driven open in MAN (it fails open, so an instrument air loss vents the separator); feed to the unit lost, so no gas is made.',
      'Close PV-505 in MAN, confirm the Unit 03 feed FIC310 is arriving, then return PIC505 to AUTO at 800 KPA.'),
    'PIC505.PVLO': e(RT.medium,
      'Separation runs at reduced pressure: less margin over the 100 KPA off-gas header, so PV-505 has to open further for the same gas make. The liquid draws are unaffected in this model.',
      'PIC505 setpoint lowered; PV-505 over-open; a Unit 03 feed cut reducing the gas make.',
      'Verify the PIC505 setpoint and mode, and check the Unit 03 feed FIC310 before adjusting the vent.'),
    'PIC505.PVHI': e(RT.short,
      'Pressure is approaching the PSV-502 set pressure of 1100 KPA; the vent is not keeping up with the gas the separator is making.',
      'PV-505 stuck or closed; PIC505 in MAN with too little output; a warm inlet (TIC502 high) breaking out more light gas than design.',
      'Open PV-505 further in MAN, restore cooling to bring TIC502 back to 45 DEG C, and cut the Unit 03 feed if the pressure keeps rising. Watch the PIC505 output for saturation.'),
    'PIC505.PVHH': e(RT.now,
      'PSV-502 lifts at 1100 KPA and relieves to flare; flaring is a reportable event, not a control action.',
      'Same causes as PVHI left unattended: PV-505 failed closed, or PIC505 left in MAN with a hot inlet.',
      'Open PV-505 fully in MAN, put full cooling on TIC502, cut the Unit 03 feed FIC310, and expect V-502 PSV LIFT.'),
    'AI509.PVHI': e(RT.short,
      'Water is going over the weir with the oil, so the liquid leaving to storage carries free water and is off-spec. This is the consequence of a high interface, read about 30 s after the interface that made it.',
      'The interface in chamber 1 has climbed within about 10 % of the weir crest (read LIC504 against the weir height); WV-504 shut or stuck; the weir lowered toward the interface.',
      'Fix the interface, not the analyser: open WV-504 or return LIC504 to AUTO at 25 %, and expect LIC504 to fall first and AI509 to follow about half a minute later.'),
    'AI509.PVHH': e(RT.now,
      'The product to storage carries enough free water to be rejected downstream, and the water is no longer leaving through the draw it should.',
      'The interface has reached the weir crest with the water draw shut or unable to keep up.',
      'Open WV-504 fully in MAN, cut the Unit 03 feed FIC310 if the interface is still rising, and judge the recovery on LIC504 falling, because AI509 lags it by about 30 s.'),
    'AI510.PVHI': e(RT.short,
      'Hydrocarbon is leaving with the process water: an environmental excursion downstream of this board, not a process upset on the separator.',
      'The water layer in chamber 1 is thin (LIC504 low), so the water draw is pulling oil under the interface; WV-504 open too far; less water arriving from Unit 03.',
      'Raise the interface: close WV-504 down (LIC504 to AUTO at 25 %, or MAN with a lower output) and check the Unit 03 feed if the water make has fallen. AI510 lags the interface by about 30 s, so read LIC504 for the recovery.'),
    'V-502.PSV LIFT': e(RT.now,
      'Relief to flare until the pressure falls below 1000 KPA; separator gas is going to the flare header and the event must be reported.',
      'Separator pressure reached 1100 KPA because PIC505 could not vent enough gas: PV-505 closed or stuck, PIC505 left in MAN, or a hot inlet making more gas than design.',
      'Reduce the gas load — full cooling on TIC502, PV-505 open in MAN, Unit 03 feed FIC310 cut — then confirm the PSV reseats below 1000 KPA and acknowledge.',
      '1100 KPA separator pressure')
  };

  function keyOf(tag, cond) { return tag + '.' + cond; }

  function has(tag, cond) { return Object.prototype.hasOwnProperty.call(TABLE, keyOf(tag, cond)); }

  function keys() { return Object.keys(TABLE); }

  function settingText(cond, cfg, entry) {
    if (entry.setting) return entry.setting;
    var tp = cfg.tripPoint, eu = cfg.eu ? ' ' + cfg.eu : '';
    if (typeof tp !== 'number') return 'Discrete condition';
    if (cond === 'DEVHI') return 'PV minus SP above ' + tp + eu;
    if (cond === 'PVLO' || cond === 'PVLL') return 'PV below ' + tp + eu;
    return 'PV above ' + tp + eu;
  }

  function priorityText(cfg) {
    var p = cfg.prio ? String(cfg.prio).toUpperCase() : 'UNSET';
    return typeof cfg.subprio === 'number' ? p + ' ' + cfg.subprio : p;
  }

  function resolve(tag, cond, cfg) {
    cfg = cfg || {};
    var entry = TABLE[keyOf(tag, cond)];
    var eq = EQUIPMENT_TRIPS[keyOf(tag, cond)];
    if (eq) {
      if (typeof cfg.tripPoint !== 'number') cfg.tripPoint = eq.value;
      if (!cfg.eu) cfg.eu = eq.eu;
      if (!cfg.prio) cfg.prio = eq.prio;
    }
    if (!entry) {
      return { found: false, tag: tag, cond: cond, priority: priorityText(cfg), setting: settingText(cond, cfg, {}),
        responseTime: 'Not rationalised', consequence: 'No alarm help has been authored for this condition.',
        probableCause: 'Not rationalised', correctiveAction: 'Follow the standard response: silence, acknowledge, read the condition, check the trend, act, verify.' };
    }
    return { found: true, tag: tag, cond: cond, priority: priorityText(cfg), setting: settingText(cond, cfg, entry),
      responseTime: entry.rt, consequence: entry.cons, probableCause: entry.cause, correctiveAction: entry.act };
  }

  return { resolve: resolve, has: has, keys: keys, EQUIPMENT_TRIPS: EQUIPMENT_TRIPS, RESPONSE_TIMES: RT };
});
