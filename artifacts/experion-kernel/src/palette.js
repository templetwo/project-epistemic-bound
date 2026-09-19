// @artifact production
/*
 * ESS.Palette — colour philosophy presets for the station display.
 *
 * Presets
 *   'representative'  the sim's current defaults (bright saturated priority
 *                     fills on the neutral grey chrome, as in the shipping
 *                     app: Urgent red, High yellow, Low cyan, Journal grey).
 *   'isa101'          the ISA-101-aligned values documented in the Rockwell
 *                     Process HMI Style Guide (RESOURCES 2.4): background
 *                     #E0E0E0, lines #A0A0A4, priority fills Urgent #E22028,
 *                     High #EC8629, Medium #F5E11B, Low #916AAD, equipment
 *                     stopped #808080, running #F0F0F0, manual #93C2E4.
 *                     The style guide's four alarm levels map onto the four
 *                     Experion priorities in rank order: Urgent -> Urgent red,
 *                     High -> High orange, Low -> Medium yellow, Journal
 *                     (event-only, lowest) -> Low magenta.
 *
 * API
 *   getPalette(name) -> {
 *     name, bg, line, text,
 *     prio:     {Urgent, High, Low, Journal}   fill behind an alarm row/badge
 *     prioText: {Urgent, High, Low, Journal}   text colour on that fill
 *     prioDim:  {Urgent, High, Low, Journal}   dark variant used as text on bg
 *     state:    {stopped, running, manual}     equipment state fills
 *     stateText:{stopped, running, manual}     text on those fills
 *     band:     {target, normal, range, marker}  limit-ladder band fills
 *               (target = operating band, normal = inside the standard
 *               limits, range = the rest of the instrument range, marker =
 *               the live PV pointer); critical and standard zones are drawn
 *               with the priority colour of the alarm that guards them.
 *   }  (unknown name falls back to 'representative')
 *   list() -> ['representative', 'isa101']
 *   contrastRatio(fg, bg) -> WCAG 2.x luminance contrast ratio (1..21)
 *   luminance(hex) -> relative luminance 0..1
 *   textPairs(palette) -> [{label, fg, bg}] every text/background pair the
 *     display draws, for auditing (tests require each >= 3:1).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else (root.ESS = root.ESS || {}).Palette = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var PRESETS = {
    representative: {
      name: 'representative', bg: '#BFBFBF', line: '#3A3A3A', text: '#000000',
      prio: { Urgent: '#FF0000', High: '#FFE000', Low: '#00D8D8', Journal: '#909090' },
      prioText: { Urgent: '#FFFFFF', High: '#000000', Low: '#000000', Journal: '#000000' },
      prioDim: { Urgent: '#A00000', High: '#7A6400', Low: '#00696D', Journal: '#666666' },
      state: { stopped: '#FFFFFF', running: '#4A4A4A', manual: '#FFE000' },
      stateText: { stopped: '#4A4A4A', running: '#FFFFFF', manual: '#000000' },
      band: { target: '#6E86A0', normal: '#F2F2F0', range: '#A8A8A4', marker: '#000000' }
    },
    isa101: {
      name: 'isa101', bg: '#E0E0E0', line: '#A0A0A4', text: '#000000',
      prio: { Urgent: '#E22028', High: '#EC8629', Low: '#F5E11B', Journal: '#916AAD' },
      prioText: { Urgent: '#FFFFFF', High: '#000000', Low: '#000000', Journal: '#FFFFFF' },
      prioDim: { Urgent: '#A9161D', High: '#8A4609', Low: '#6E6300', Journal: '#5C3E78' },
      state: { stopped: '#808080', running: '#F0F0F0', manual: '#93C2E4' },
      stateText: { stopped: '#000000', running: '#000000', manual: '#000000' },
      band: { target: '#93C2E4', normal: '#F0F0F0', range: '#A0A0A4', marker: '#000000' }
    },
    // NIGHT -- the dark console. Added 2026-09-14 from the facelift review
    // (docs/dev/FACELIFT-REVIEW-MEMO.md item 1 and item 5).
    //
    // Every pair is AA-clean at 4.5:1 against this palette's OWN surfaces -- text 15.03 on the
    // ground, and no priority fill or dim below 5.6. That is the point of it: the two light
    // presets each carry one pre-existing sub-AA pair (representative Urgent 4.00, isa101
    // Journal 4.31) that cannot be fixed without making them less faithful to what they claim
    // to represent. This palette owes nothing to a vendor default, so it is simply correct.
    //
    // ISA-101 does not mandate a light ground; it asks for a MUTED one with colour reserved for
    // abnormal (RESOURCES 2.4, 2.11). A dark console satisfies that reading, and here it also
    // buys a large accessibility margin over what the light presets can reach.
    night: {
      name: 'night', bg: '#12161C', line: '#5A6572', text: '#E6EAF0',
      surfaces: ['#12161C', '#1C232C'],   // the grounds this palette actually renders text on
      onDim: '#0E1116',                   // text colour when a dim tone is used as a fill
      prio: { Urgent: '#C62828', High: '#E6B422', Low: '#26C6C6', Journal: '#5A6068' },
      prioText: { Urgent: '#FFFFFF', High: '#111111', Low: '#111111', Journal: '#FFFFFF' },
      prioDim: { Urgent: '#FF8A80', High: '#FFD54F', Low: '#80DEEA', Journal: '#B9C0CC' },
      state: { stopped: '#2A313A', running: '#C5CCD6', manual: '#E6B422' },
      stateText: { stopped: '#E6EAF0', running: '#12161C', manual: '#111111' },
      band: { target: '#7EB6D6', normal: '#1C232C', range: '#3A424E', marker: '#E6EAF0' }
    }
  };

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function list() { return Object.keys(PRESETS); }
  function getPalette(name) { return clone(PRESETS[name] || PRESETS.representative); }

  function channel(v) {
    var c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  function parseHex(hex) {
    var h = String(hex).replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function luminance(hex) {
    var c = parseHex(hex);
    return 0.2126 * channel(c[0]) + 0.7152 * channel(c[1]) + 0.0722 * channel(c[2]);
  }

  function contrastRatio(fg, bg) {
    var a = luminance(fg), b = luminance(bg);
    var hi = Math.max(a, b), lo = Math.min(a, b);
    return (hi + 0.05) / (lo + 0.05);
  }

  // The surfaces a palette renders text on, and the text colour used when a dim tone is itself a
  // fill. Defaulting to white preserves EXACTLY the pairs the two light presets were checked
  // against before 2026-09-14, so adding this field changed no existing coverage.
  //
  // Hardcoding '#FFFFFF' here was a light-theme assumption baked into the contrast contract, and
  // it made a dark palette mathematically impossible rather than merely unfashionable: passing
  // 4.5:1 against a #12161C ground requires luminance >= 0.214, and against white requires
  // <= 0.183. No colour satisfies both. Deriving the surfaces from the palette fixes that.
  function surfacesOf(p) { return (p.surfaces && p.surfaces.length) ? p.surfaces : ['#FFFFFF']; }
  function onDimOf(p) { return p.onDim || '#FFFFFF'; }

  function textPairs(p) {
    var pairs = [{ label: 'text on bg', fg: p.text, bg: p.bg }];
    var surfaces = surfacesOf(p), onDim = onDimOf(p);
    Object.keys(p.prio).forEach(function (k) {
      pairs.push({ label: k + ' text on fill', fg: p.prioText[k], bg: p.prio[k] });
      pairs.push({ label: k + ' dim text on bg', fg: p.prioDim[k], bg: p.bg });
      surfaces.forEach(function (s) {
        pairs.push({ label: k + ' dim text on ' + s, fg: p.prioDim[k], bg: s });
      });
      pairs.push({ label: 'on-dim text on ' + k + ' dim', fg: onDim, bg: p.prioDim[k] });
    });
    Object.keys(p.state).forEach(function (k) {
      pairs.push({ label: k + ' state text', fg: p.stateText[k], bg: p.state[k] });
    });
    return pairs;
  }

  return { getPalette: getPalette, list: list, contrastRatio: contrastRatio, luminance: luminance, textPairs: textPairs };
});
