/**
 * Thirty more Plenio Drop presets (owner's request 2026-10-23: hypnotic and rhythmic, unusual, or very
 * harmonious - MilkDrop's best, made anew). Each takes the idea of a classic of the MilkDrop preset packs - its
 * motion, its warp, what it draws - and rebuilds it in Plenio Drop's own format (format.ts) with the warp
 * families added for them (twist, fold, lens, tiles, spiral, drain): nothing of the originals' code is used.
 * The idea each one comes from is named above it.
 */
import type { PresetFile } from './format'

export const MILKDROP: PresetFile[] = [
  // Geiss - Cosmic Dust: a slow drift of fine points out of the middle
  {
    name: 'Cosmic Dust',
    blurb: 'Glittering dust drifting out of the middle, slowly turning - brighter where the highs sparkle.',
    suits: ['calm', 'electronic', 'any'],
    base: { decay: 0.982, warp: 0.5, warpScale: 1.4, hueShift: 0.003, gamma: 1.9, darkenCenter: 0.04 },
    frame: { zoom: '1.006 + 0.008 * bass_att', rot: '0.003 + 0.004 * sin(time * 0.1)' },
    waves: [{ mode: 'dots', repeat: 3, scale: '0.3 + 0.45 * i + 0.1 * treb_att', thick: 0.0035, alpha: '0.45 + 0.2 * treb', hue: 'time * 0.02 + i * 0.3' }],
  },
  // Geiss - Two-Pointed Spiral: the spiral's eye wanders between two points
  {
    name: 'Twin Spiral',
    blurb: 'An endless spiral whose eye wanders from one side to the other, winding the colours in.',
    suits: ['electronic', 'energetic'],
    base: { decay: 0.984, family: 'spiral', famB: 1, gamma: 1.6, hueShift: 0.006, darkenCenter: 0.05 },
    frame: {
      cx: '0.5 + 0.2 * sin(time * 0.31)',
      cy: '0.5 + 0.12 * cos(time * 0.23)',
      famA: '0.035 + 0.03 * bass_att',
      zoom: '1.016 + 0.012 * bass',
    },
    waves: [
      { mode: 'circle', x: '0.4 * sin(time * 0.31)', y: '0.24 * cos(time * 0.23)', scale: '0.3 + 0.25 * bass_att', thick: 0.006, alpha: 0.8, hue: 'time * 0.05' },
      { mode: 'circle', x: '0.4 * sin(time * 0.31)', y: '0.24 * cos(time * 0.23)', scale: '0.75 + 0.2 * treb_att', thick: 0.004, alpha: 0.5, hue: 'time * 0.05 + 0.5' },
    ],
  },
  // Geiss - Reaction Diffusion: an organic pattern growing out of itself
  {
    name: 'Living Coral',
    blurb: 'Coral-like veins growing and branching slowly, as if the picture were alive.',
    suits: ['calm', 'dark'],
    base: { decay: 0.992, family: 'waves', famA: 0.0045, famB: 15, warp: 1.6, warpScale: 2.6, warpSpeed: 0.4, gamma: 2.1, solarize: 0.25, zoom: 1.001 },
    frame: { famA: '0.0035 + 0.002 * mid_att' },
    waves: [{ mode: 'dots', repeat: 2, scale: '0.5 + 0.35 * i + 0.3 * mid_att', thick: 0.004, alpha: 0.6, hue: 'time * 0.015 + 0.4 * i' }],
  },
  // Geiss - Bipolar: two poles circling, the swirl changing its sense
  {
    name: 'Bipolar Swirl',
    blurb: 'Two lights circling each other, the swirl around them turning one way, then the other.',
    suits: ['energetic', 'electronic'],
    base: { decay: 0.968, family: 'swirl', famB: 1.2, hueShift: 0.004, gamma: 1.7 },
    frame: { famA: '0.16 * sin(time * 0.4)', zoom: '1.008 + 0.012 * bass' },
    shapes: [{ repeat: 2, sides: 32, radius: '0.04 + 0.05 * pulse', x: '0.32 * cos(time * 0.6 + i * pi) / aspect', y: '0.32 * sin(time * 0.6 + i * pi)', hue: 'i * 0.5 + time * 0.03', alpha: 0.5, inner: 1 }],
    waves: [{ mode: 'circle', scale: '0.62 + 0.15 * bass_att', thick: 0.004, alpha: 0.5, hue: 'time * 0.03 + 0.25' }],
  },
  // Rovastar - Fractopia: a fractal folding out of itself
  {
    name: 'Fractal Garden',
    blurb: 'The picture folded into itself frame by frame - a fractal of light that blooms and turns.',
    suits: ['electronic', 'dark'],
    base: { decay: 0.94, family: 'fold', gamma: 1.2, hueShift: 0.008, vignette: 0.5, darkenCenter: 0.04 },
    frame: {
      famA: '0.11 + 0.04 * sin(time * 0.21) + 0.02 * bass_att',
      famB: '0.4 + 0.15 * sin(time * 0.13)',
      zoom: '0.985 - 0.006 * bass',
    },
    waves: [{ mode: 'circle', scale: '0.28 + 0.12 * bass_att', thick: 0.005, alpha: 0.6, hue: 'time * 0.04' }],
  },
  // Rovastar - Altars of Madness: a tunnel with its echo turned over, burning on loud beats
  {
    name: 'Altar of Madness',
    blurb: 'A tunnel and its own image turned over, burning into negatives when the bass hits hard.',
    suits: ['dark', 'energetic'],
    base: { decay: 0.95, family: 'tunnel', famB: 9, echoAlpha: 0.45, echoZoom: 1.5, echoOrient: 3, gamma: 1.25, darkenCenter: 0.1 },
    frame: {
      zoom: '1.024 + 0.025 * bass',
      famA: '0.035 * bass_att',
      rot: '0.008 * sin(time * 0.19)',
      solarize: 'bass > 1.5 ? 0.55 : 0.08',
    },
    waves: [
      { mode: 'spiral', scale: '0.9 + 0.2 * mid_att', thick: 0.004, alpha: 0.55, hue: 'time * 0.06' },
      { mode: 'scope', scale: '0.7 + 0.3 * bass_att', thick: 0.005, alpha: 0.4, hue: 'time * 0.06 + 0.5' },
    ],
  },
  // Rovastar - Hallucinogenic Pyramids: triangles in a breathing lens, mirrored four ways
  {
    name: 'Pyramid Dream',
    blurb: 'Glowing triangles turning in a lens that breathes, mirrored into four.',
    suits: ['electronic', 'calm'],
    base: { decay: 0.966, family: 'lens', famB: 0.3, mirror: 'both', gamma: 1.7, hueShift: 0.005 },
    frame: { famA: '0.012 + 0.02 * bass_att', zoom: 1.004, rot: '0.004 * sin(time * 0.3)' },
    shapes: [{ repeat: 4, sides: 3, radius: '0.13 + 0.05 * pulse', x: '0.45 * cos(time * 0.25 + i * pi / 2) / aspect', y: '0.45 * sin(time * 0.25 + i * pi / 2)', angle: 'time * (0.4 + 0.1 * i)', hue: 'i / n + time * 0.02', alpha: 0.35, inner: 0.05 }],
  },
  // Rovastar - Northern Lights: curtains of light drifting sideways
  {
    name: 'Polar Night',
    blurb: 'Curtains of light swaying over a dark sky, drifting slowly sideways.',
    suits: ['calm', 'acoustic'],
    base: { decay: 0.978, family: 'waves', famA: 0.005, famB: 4, dy: -0.0015, gamma: 1.8, vignette: 0.5 },
    frame: { dx: '0.0025 * sin(time * 0.07)', famA: '0.004 + 0.003 * mid_att' },
    waves: [{ mode: 'vertical', repeat: 3, x: '-0.6 + 0.6 * i + 0.1 * sin(time * 0.3 + i)', scale: '0.5 + 0.3 * mid_att', thick: 0.006, alpha: 0.55, hue: '0.35 + 0.12 * i + 0.05 * sin(time * 0.1)' }],
  },
  // Flexi - mindblob: a soft blob that swells and wobbles
  {
    name: 'Mind Blob',
    blurb: 'A soft glowing blob that swells with the bass and wobbles in a breathing lens.',
    suits: ['calm', 'electronic'],
    base: { decay: 0.972, family: 'lens', famB: 0.28, warp: 1.1, warpSpeed: 0.7, gamma: 1.7 },
    frame: { famA: '0.03 * (bass_att - 0.8)', rot: '0.006 * sin(time * 0.23)' },
    shapes: [{ sides: 40, radius: '0.12 + 0.08 * bass_att + 0.04 * pulse', x: '0.1 * sin(time * 0.37) / aspect', y: '0.08 * cos(time * 0.29)', hue: 'time * 0.03', alpha: 0, inner: 0.45 }],
    waves: [{ mode: 'circle', x: '0.1 * sin(time * 0.37)', y: '0.08 * cos(time * 0.29)', scale: '0.45 + 0.25 * bass_att', thick: 0.004, alpha: 0.5, hue: 'time * 0.03 + 0.5' }],
  },
  // Flexi - infinite fractal: the picture tiled into itself (three by three: an odd count keeps a tile in the
  // middle; with two the copies sat on the edges)
  {
    name: 'Infinite Mosaic',
    blurb: 'The picture in tiles of itself, tiles in tiles - on every beat a step deeper.',
    suits: ['electronic', 'energetic'],
    base: { decay: 0.968, family: 'tiles', famB: 3, gamma: 1.3, hueShift: 0.01 },
    frame: {
      famA: 'min(1, beat + (fract(time / 2) < dt / 2 ? 1 : 0))',
      zoom: '1.02 + 0.008 * bass',
      rot: '0.004 * sin(time * 0.2)',
    },
    waves: [
      { mode: 'circle', scale: '0.6 + 0.25 * bass_att', thick: 0.007, alpha: 0.8, hue: 'time * 0.05' },
      { mode: 'scope', scale: '0.5 + 0.3 * mid_att', thick: 0.004, alpha: 0.45, hue: 'time * 0.05 + 0.5' },
    ],
  },
  // Flexi - predator-prey spirals: two spirals winding against each other
  {
    name: 'Predator Prey',
    blurb: 'Two spirals winding against each other - one hunts, the other turns away.',
    suits: ['electronic', 'dark'],
    base: { decay: 0.963, family: 'spiral', famB: 1, gamma: 1.7 },
    frame: { famA: '0.018 * sin(time * 0.17)', zoom: '1.006 + 0.01 * bass_att', rot: '-0.01 * sin(time * 0.17)' },
    shapes: [{ repeat: 6, sides: 12, radius: '0.025 + 0.02 * pulse', x: '(0.15 + 0.1 * i) * cos(time * 0.8 - i * 0.6) / aspect', y: '(0.15 + 0.1 * i) * sin(time * 0.8 - i * 0.6)', hue: 'i / n', alpha: 0.3, inner: 1 }],
    waves: [{ mode: 'spiral', scale: 1, thick: 0.004, alpha: 0.55, hue: 'time * 0.04 + 0.5' }],
  },
  // Martin - frosty caves: a cold cave pulling into its middle
  {
    name: 'Frost Caves',
    blurb: 'Cold light whirling slowly into the depth of an ice cave, its mirror image above.',
    suits: ['calm', 'dark'],
    base: { decay: 0.972, family: 'drain', famB: 0.15, echoAlpha: 0.3, echoZoom: 0.8, echoOrient: 2, gamma: 1.5, vignette: 0.55 },
    frame: { famA: '0.004 + 0.004 * mid_att', zoom: '0.992 - 0.004 * bass_att' },
    waves: [
      { mode: 'dots', scale: '0.85 + 0.2 * treb_att', thick: 0.004, alpha: 0.55, hue: '0.55 + 0.05 * sin(time * 0.1)' },
      { mode: 'circle', scale: '0.9 + 0.2 * bass_att', thick: 0.003, alpha: 0.4, hue: 0.62 },
    ],
  },
  // Martin - liquid diamonds: diamonds turning in a four-way kaleidoscope
  {
    name: 'Liquid Diamonds',
    blurb: 'Diamonds turning in a four-fold mirror, their light melting into soft facets.',
    suits: ['acoustic', 'calm'],
    base: { decay: 0.962, family: 'kaleidoscope', famB: 4, famA: 0.3, solarize: 0.25, gamma: 1.6 },
    frame: { zoom: '1.01 + 0.012 * bass_att', rot: '0.005 * sin(time * 0.15)' },
    shapes: [{ repeat: 4, sides: 4, radius: '0.09 + 0.04 * pulse', x: '0.3 * cos(time * 0.3 + i * pi / 2) / aspect', y: '0.3 * sin(time * 0.3 + i * pi / 2)', angle: 'time * 0.5', hue: 'i / n + time * 0.02', alpha: 0.35, inner: 0.15 }],
  },
  // Unchained - Unified Drag: everything dragged along by the music's push
  {
    name: 'Unified Drag',
    blurb: 'The whole picture dragged along by the beat, its flow drawn as a field of strokes.',
    suits: ['energetic', 'electronic'],
    base: { decay: 0.93, mvec: 28, mvAlpha: 0.35, gamma: 1.9 },
    frame: {
      dx: '0.006 * sin(time * 0.37) * (0.6 + 0.6 * bass)',
      dy: '0.006 * cos(time * 0.29) * (0.6 + 0.6 * mid)',
      zoom: '1.004 + 0.012 * pulse',
    },
    waves: [{ mode: 'line', scale: '0.7 + 0.4 * bass_att', thick: 0.009, alpha: 0.9, hue: 'time * 0.06' }],
  },
  // Aderrasi - Ambient Fire: embers rising in a warm turbulence
  {
    name: 'Ember Rise',
    blurb: 'Sparks of the spectrum rising from the ground in a warm, turbulent draught.',
    suits: ['dark', 'acoustic'],
    base: { decay: 0.966, dy: 0.008, warp: 1.8, warpScale: 1.3, warpSpeed: 1.2, sx: 1.003, gamma: 1.7 },
    frame: { warp: '1.4 + 0.8 * treb_att', dy: '0.006 + 0.004 * bass_att' },
    waves: [{ mode: 'spectrum', y: -0.82, scale: '0.5 + 0.3 * bass_att', thick: 0.007, alpha: 0.9, hue: '0.05 + 0.05 * sin(time * 0.2)' }],
  },
  // Aderrasi - Halls of Frozen Time: still rooms of mirrors
  {
    name: 'Frozen Time',
    blurb: 'Rings standing still in a hall of mirrors, the image within the image slowly fading.',
    suits: ['calm', 'dark'],
    base: { decay: 0.986, echoAlpha: 0.55, echoZoom: 2, echoOrient: 1, mirror: 'left-right', gamma: 1.5, rot: 0.002 },
    frame: { zoom: '0.998 + 0.004 * bass_att' },
    waves: [{ mode: 'circle', repeat: 3, x: 0.35, scale: '0.25 + 0.3 * i + 0.1 * bass_att', thick: 0.004, alpha: 0.5, hue: 'i * 0.2 + time * 0.01' }],
  },
  // Krash - Digital Flame: the spectrum as a flame that licks upward
  {
    name: 'Digital Flame',
    blurb: 'The spectrum as a flame at the bottom, licking upward and narrowing to a point.',
    suits: ['energetic', 'electronic'],
    base: { decay: 0.948, dy: 0.012, sx: 0.994, warp: 0.7, gamma: 1.8, vignette: 0.3 },
    frame: { dy: '0.01 + 0.006 * bass' },
    waves: [{ mode: 'spectrum', y: -0.88, scale: '0.7 + 0.4 * bass_att', thick: 0.008, alpha: 1, hue: 'time * 0.03' }],
  },
  // Eo.S. - glowsticks: thick glowing figures, mirrored, short trails
  {
    name: 'Glowsticks',
    blurb: 'Thick glowing figures of the sound swung through the dark, mirrored into four.',
    suits: ['electronic', 'energetic'],
    base: { decay: 0.915, mirror: 'both', gamma: 1.45 },
    frame: { rot: '0.02 * sin(time * 0.5)', zoom: '1.004 + 0.01 * bass' },
    waves: [{ mode: 'scope', repeat: 2, x: '-0.45 + 0.2 * sin(time * 0.4 + i * 2)', y: '0.4 + 0.15 * cos(time * 0.3 + i)', scale: '1.5 + 0.5 * i + 0.4 * bass_att', thick: 0.009, alpha: 0.75, hue: 'i * 0.4 + time * 0.07' }],
  },
  // Zylot - Rainbow Orb Peacock: concentric rings of colour in a swirl
  {
    name: 'Peacock Orb',
    blurb: 'Rings of colour inside one another, swirled into the eyes of a peacock’s tail.',
    suits: ['calm', 'electronic'],
    base: { decay: 0.97, family: 'swirl', famB: 1, gamma: 1.6, hueShift: 0.003 },
    frame: { famA: '0.06 + 0.06 * mid_att', zoom: '1.006 + 0.008 * bass_att' },
    waves: [{ mode: 'circle', repeat: 5, scale: '0.15 + 0.17 * i + 0.05 * bass_att', thick: 0.005, alpha: 0.7, hue: 'i / n + time * 0.03' }],
  },
  // Geiss - Tokamak: a ring of plasma twisted in its field
  {
    name: 'Tokamak',
    blurb: 'A ring of plasma held in a field, twisted round and round - flaring on the kick.',
    suits: ['electronic', 'dark'],
    base: { decay: 0.958, family: 'twist', famB: 2, darkenCenter: 0.06, gamma: 1.7 },
    frame: { famA: '0.02 + 0.03 * bass_att', rot: '0.01 + 0.01 * mid', zoom: '1.002 + 0.006 * pulse' },
    waves: [
      { mode: 'circle', scale: '0.55 + 0.12 * bass_att', thick: '0.01 + 0.012 * pulse', alpha: 0.9, hue: 'time * 0.04' },
      { mode: 'dots', scale: 0.7, thick: 0.004, alpha: 0.4, hue: 'time * 0.04 + 0.5' },
    ],
  },
  // Geiss - Inkblot: a symmetric blot spreading slowly
  {
    name: 'Inkblot',
    blurb: 'A symmetric blot of ink spreading, folding and turning - what do you see in it?',
    suits: ['calm', 'dark'],
    base: { decay: 0.992, mirror: 'left-right', family: 'swirl', famA: 0.08, famB: 1.5, warp: 1.5, warpSpeed: 0.6, zoom: 1.002, gamma: 1.5 },
    waves: [{ mode: 'dots', scale: '0.3 + 0.15 * bass_att', thick: 0.004, alpha: 0.55, hue: 'time * 0.015' }],
  },
  // Geiss - Jelly Parade: soft glowing jellies floating upward
  {
    name: 'Jelly Lanterns',
    blurb: 'Soft glowing jellies floating upward like lanterns, pulsing gently with the beat.',
    suits: ['calm'],
    base: { decay: 0.972, family: 'lens', famA: 0.006, famB: 0.3, dy: 0.0015, gamma: 1.6 },
    shapes: [{ repeat: 6, sides: 30, radius: '0.05 + 0.025 * sin(time * 1.3 + i) + 0.025 * pulse', x: '0.75 * sin(i * 2.4 + time * 0.15)', y: 'fract(time * 0.04 + i / n) * 2.4 - 1.2', hue: 'i / n', alpha: 0.04, inner: 0.65 }],
  },
  // Warp of Doom: everything pulled into a whirling drain, flashing negative on the hardest beats
  {
    name: 'Warp of Doom',
    blurb: 'Everything pulled into a whirling drain, flashing into a negative on the hardest beats.',
    suits: ['dark', 'energetic'],
    base: { decay: 0.95, family: 'drain', famB: 0.1, gamma: 1.35, darkenCenter: 0.12 },
    frame: {
      famA: '0.015 + 0.02 * bass_att',
      zoom: '1.025 + 0.02 * bass',
      invert: 'beat && bass > 1.7 ? 0.5 : 0',
    },
    waves: [{ mode: 'scope', scale: '1 + 0.4 * bass_att', thick: 0.006, alpha: 0.6, hue: 'time * 0.07' }],
  },
  // Geiss - Starfish: a five-fold star of light
  {
    name: 'Sea Star',
    blurb: 'A five-armed star of light opening and closing in a five-fold mirror.',
    suits: ['acoustic', 'calm'],
    base: { decay: 0.964, family: 'kaleidoscope', famB: 5, gamma: 1.6 },
    frame: { famA: '0.5 * sin(time * 0.2)', rot: 0.004, zoom: '1.008 + 0.01 * bass_att' },
    shapes: [{ repeat: 5, sides: 5, radius: '0.05 + 0.03 * pulse', x: '0.35 * cos(i * 2 * pi / 5 + time * 0.2) / aspect', y: '0.35 * sin(i * 2 * pi / 5 + time * 0.2)', angle: '-time * 0.6', hue: 'i / n * 0.5 + time * 0.02', alpha: 0.3, inner: 0.7 }],
    waves: [{ mode: 'spiral', scale: 0.8, thick: 0.004, alpha: 0.5, hue: 'time * 0.02 + 0.3' }],
  },
  // Geiss - Smoke: velvet smoke curling upward
  {
    name: 'Velvet Smoke',
    blurb: 'Soft smoke curling upward from a quiet line of sound - slow, deep and warm.',
    suits: ['calm', 'acoustic'],
    base: { decay: 0.99, warp: 2.2, warpScale: 0.45, warpSpeed: 0.6, dy: 0.003, gamma: 1.35, hueShift: 0.002 },
    waves: [{ mode: 'line', y: -0.7, scale: '0.4 + 0.25 * bass_att', thick: 0.01, alpha: 0.4, hue: 'time * 0.02' }],
  },
  // a hypnotic disc: rings in an endless spiral that turns the other way every four beats
  {
    name: 'Hypno Disc',
    blurb: 'Rings winding into an endless spiral that turns the other way every four beats.',
    suits: ['energetic', 'electronic'],
    base: { decay: 0.962, family: 'spiral', famB: 1, gamma: 1.45 },
    init: { count: 0 },
    frame: {
      count: 'beat ? count + 1 : count',
      famA: '0.022 * (floor(count / 4) % 2 * 2 - 1)',
      zoom: '0.993 - 0.006 * pulse',
    },
    waves: [{ mode: 'circle', repeat: 5, scale: '0.3 * (i + 1) + 0.06 * pulse', thick: 0.008, alpha: 0.7, hue: 'i / n + time * 0.05' }],
  },
  // a lattice of tiles that strobes on the beat
  {
    name: 'Strobe Lattice',
    blurb: 'A lattice of the picture in nine tiles, flashing on every beat - for the dance floor.',
    suits: ['energetic', 'electronic'],
    base: { decay: 0.972, family: 'tiles', famB: 3, gamma: 1.5 },
    frame: { famA: 'min(1, beat + (fract(time / 2) < dt / 2 ? 1 : 0))', invert: 'pulse > 0.85 ? 0.35 : 0', zoom: '1.0 + 0.01 * bass' },
    waves: [
      { mode: 'line', scale: '0.6 + 0.4 * bass_att', thick: 0.008, alpha: 0.9, hue: 'time * 0.08' },
      { mode: 'vertical', scale: '0.6 + 0.4 * mid_att', thick: 0.008, alpha: 0.9, hue: 'time * 0.08 + 0.5' },
    ],
  },
  // a mandala that breathes: twelve mirrors, the zoom in and out with the bass
  {
    name: 'Mandala Breath',
    blurb: 'A twelve-fold mandala breathing in and out with the music - calm, round and endless.',
    suits: ['calm', 'acoustic'],
    base: { decay: 0.968, family: 'kaleidoscope', famB: 12, famA: 0.3, gamma: 1.6, hueShift: 0.002 },
    frame: { zoom: '1 + 0.018 * (bass_att - 1)', rot: '0.004 * sin(time * 0.1)' },
    shapes: [{ repeat: 3, sides: 4, radius: '0.045 + 0.03 * pulse', x: '(0.12 + 0.6 * fract(time * 0.06 + i / n)) * cos(0.13 + 0.1 * sin(time * 0.3)) / aspect', y: '(0.12 + 0.6 * fract(time * 0.06 + i / n)) * sin(0.13 + 0.1 * sin(time * 0.3))', angle: 'time * 0.5', hue: 'i / n + time * 0.01', alpha: 0.4, inner: 0.25 }],
    waves: [{ mode: 'circle', scale: '0.3 + 0.1 * bass_att', thick: 0.004, alpha: 0.5, hue: 'time * 0.02' }],
  },
  // a rose curve: lights travelling along a three-petalled rose
  {
    name: 'Harmonic Rose',
    blurb: 'Lights travelling along a three-petalled rose, their trails weaving a slow, harmonious flower.',
    suits: ['calm', 'acoustic'],
    base: { decay: 0.986, family: 'swirl', famA: 0.03, famB: 1, zoom: 1.002, gamma: 1.6 },
    shapes: [{ repeat: 16, sides: 16, radius: '0.016 + 0.012 * pulse', x: '0.65 * cos(3 * (time * 0.2 + i / n * 2 * pi)) * cos(time * 0.2 + i / n * 2 * pi) / aspect', y: '0.65 * cos(3 * (time * 0.2 + i / n * 2 * pi)) * sin(time * 0.2 + i / n * 2 * pi)', hue: 'i / n', alpha: 0.2, inner: 0.9 }],
  },
  // the cover in an endless spiral of itself (the Droste effect)
  {
    name: 'Cover Droste',
    blurb: 'The song’s cover inside itself, again and again, winding into an endless spiral.',
    suits: ['calm', 'electronic', 'any'],
    base: { decay: 0.975, family: 'spiral', famB: 1, gamma: 1.4 },
    frame: { famA: '0.012 + 0.008 * bass_att', zoom: '0.986 - 0.004 * bass_att' },
    sprites: [{ source: 'cover', size: '0.32 + 0.02 * pulse', angle: 'time * 0.1', alpha: 0.5, blend: 'over' }],
    waves: [{ mode: 'circle', scale: '0.75 + 0.1 * bass_att', thick: 0.004, alpha: 0.45, hue: 'time * 0.03' }],
  },
]
