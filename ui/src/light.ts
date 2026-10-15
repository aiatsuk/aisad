/** Studio lighting for Braille surfaces, adapted from the Codex CLI welcome mark.
 * Colors are packed 0xRRGGBB. The terminal background is assumed dark (#1b1b1b),
 * matching the minimap fade; chalk downsamples hex colors for 256/16-color terminals. */
export type RGB = readonly [number, number, number];
export const BACKGROUND: RGB = [27, 27, 27];
const SHADOW: RGB = [52, 71, 105], RIM: RGB = [91, 196, 216], HIGHLIGHT: RGB = [255, 244, 218];
export const pack = (r: number, g: number, b: number): number => (clampByte(r) << 16) | (clampByte(g) << 8) | clampByte(b);
const clampByte = (value: number): number => Math.max(0, Math.min(255, Math.round(value)));
export const unpack = (rgb: number): RGB => [(rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255];
export const hexToRgb = (hex: string): number => parseInt(hex.slice(1, 7), 16) || 0;
/** Quantize to 16-unit steps: neighbouring cells share color codes, so frames stay small. */
export const rgbToHex = (rgb: number): string => '#' + unpack(rgb).map(c => (Math.min(255, (c + 8) & ~15)).toString(16).padStart(2, '0')).join('');
/** Blend a color toward the background; opacity 1 keeps it exact. */
export function fade(hex: string, opacity: number): string {
  if (opacity >= 1) return hex;
  const [r, g, b] = unpack(hexToRgb(hex)), o = Math.max(0, opacity);
  return rgbToHex(pack(BACKGROUND[0] + (r - BACKGROUND[0]) * o, BACKGROUND[1] + (g - BACKGROUND[1]) * o, BACKGROUND[2] + (b - BACKGROUND[2]) * o));
}
export function mix(a: number, b: RGB, t: number): number {
  const [r, g, bl] = unpack(a), k = Math.max(0, Math.min(1, t));
  return pack(r + (b[0] - r) * k, g + (b[1] - g) * k, bl + (b[2] - bl) * k);
}
/** Raised-cosine band (Codex shimmer): 1 at the center, 0 beyond `half`. */
export const band = (distance: number, half: number): number => Math.abs(distance) >= half ? 0 : .5 * (1 + Math.cos(Math.PI * distance / half));
export const HIGHLIGHT_RGB = HIGHLIGHT;
// Key light from the upper right, slightly in front. A surface facing the viewer
// is lit at exactly its tint, so a settled frame never shifts color.
const LIGHT = normalize([.30, -.25, .92]);
const REST = LIGHT[2];
function normalize(v: [number, number, number]): [number, number, number] {const l = Math.hypot(...v) || 1; return [v[0] / l, v[1] / l, v[2] / l];}
const halfway = [normalize([-.62, -.15, .77]), normalize([.62, -.15, .77])] as const;
/**
 * Shade one surface sample. `n` is the rotated unit normal, `depth` the camera-space
 * depth in half-widths (positive is nearer), `direction` picks the glint side so the
 * incoming face catches the specular sweep mid-turn.
 */
export function shade(tint: number, nx: number, ny: number, nz: number, depth: number, direction: number, grain = 0): number {
  const diffuse = Math.max(0, (nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]) / REST + grain);
  const [r, g, b] = unpack(tint), lit = Math.min(1, diffuse), boost = Math.max(0, Math.min(.15, diffuse - 1));
  let color = pack(
    SHADOW[0] + (r - SHADOW[0]) * lit + (255 - r) * boost,
    SHADOW[1] + (g - SHADOW[1]) * lit + (255 - g) * boost,
    SHADOW[2] + (b - SHADOW[2]) * lit + (255 - b) * boost);
  const edge = Math.pow(1 - Math.min(1, Math.abs(nz)), 2.4) * .78;
  color = mix(color, RIM, edge);
  const h = halfway[direction < 0 ? 1 : 0];
  const gloss = Math.pow(Math.max(0, nx * h[0] + ny * h[1] + nz * h[2]), 24) * .9;
  color = mix(color, HIGHLIGHT, gloss);
  const gain = Math.max(.5, Math.min(1, 1 + depth * .32));
  const [cr, cg, cb] = unpack(color);
  return pack(BACKGROUND[0] + (cr - BACKGROUND[0]) * gain, BACKGROUND[1] + (cg - BACKGROUND[1]) * gain, BACKGROUND[2] + (cb - BACKGROUND[2]) * gain);
}
