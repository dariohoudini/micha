/**
 * Design tokens — Tier 8.
 *
 * Source of truth for colours, spacing, typography, shadows, radii.
 * Replaces the ad-hoc inline-hex values scattered across the codebase.
 *
 * Migration plan
 * ──────────────
 * New components import from here. Existing inline-hex components
 * can migrate at PR review time without a forced sweep.
 *
 * Buyer vs Admin palettes
 * ────────────────────────
 * Buyer is light-on-dark warm (gold + black). Admin is cool-dark
 * (indigo + near-black). Both share neutral greys.
 */


// ─── Neutral greys (shared) ─────────────────────────────────────

export const NEUTRAL = {
  0:   '#FFFFFF',
  50:  '#FAFAFA',
  100: '#F4F4F5',
  200: '#E4E4E7',
  300: '#D4D4D8',
  400: '#A1A1AA',
  500: '#71717A',
  600: '#52525B',
  700: '#3F3F46',
  800: '#27272A',
  900: '#18181B',
  950: '#09090B',
}


// ─── Brand: buyer (warm) ─────────────────────────────────────────

export const BUYER = {
  bg:         '#0A0A0A',
  surface:    '#141414',
  card:       '#1E1E1E',
  border:     '#2A2A2A',
  text:       '#FFFFFF',
  textMuted:  '#9A9A9A',
  textDim:    '#555555',
  accent:     '#C9A84C',  // gold
  accentSoft: 'rgba(201, 168, 76, 0.1)',
  accentRing: 'rgba(201, 168, 76, 0.3)',
}


// ─── Brand: admin (cool) ─────────────────────────────────────────

export const ADMIN = {
  bg:         '#060608',
  surface:    '#0D0D1A',
  card:       '#111120',
  border:     '#1A1A2E',
  text:       '#E2E8F0',
  textMuted:  '#64748B',
  accent:     '#6366F1',  // indigo
  accentSoft: 'rgba(99, 102, 241, 0.1)',
  accentRing: 'rgba(99, 102, 241, 0.25)',
}


// ─── Status colours (semantic, shared) ───────────────────────────

export const STATUS = {
  success: { fg: '#22C55E', bg: 'rgba(34, 197, 94, 0.1)',  border: 'rgba(34, 197, 94, 0.3)' },
  warning: { fg: '#FBBF24', bg: 'rgba(245, 158, 11, 0.1)', border: 'rgba(245, 158, 11, 0.3)' },
  danger:  { fg: '#EF4444', bg: 'rgba(239, 68, 68, 0.1)',  border: 'rgba(239, 68, 68, 0.3)' },
  info:    { fg: '#3B82F6', bg: 'rgba(59, 130, 246, 0.1)', border: 'rgba(59, 130, 246, 0.3)' },
  brand:   { fg: '#C9A84C', bg: 'rgba(201, 168, 76, 0.1)', border: 'rgba(201, 168, 76, 0.3)' },
}


// ─── Trust score badge palette (R4) ──────────────────────────────

export const TRUST_BADGE = {
  elite:    '#C9A84C',
  trusted:  '#A1A1AA',
  good:     '#CD7F32',
  verified: '#3B82F6',
  new:      '#71717A',
}


// ─── Spacing scale (rem-equivalent in px for inline-style use) ──

export const SPACING = {
  px:  '1px',
  0:   '0',
  0.5: '2px',
  1:   '4px',
  2:   '8px',
  3:   '12px',
  4:   '16px',
  5:   '20px',
  6:   '24px',
  8:   '32px',
  10:  '40px',
  12:  '48px',
  16:  '64px',
  20:  '80px',
  24:  '96px',
}


// ─── Border radius ───────────────────────────────────────────────

export const RADIUS = {
  none: '0',
  sm:   '4px',
  md:   '8px',
  lg:   '12px',
  xl:   '16px',
  '2xl': '20px',
  '3xl': '24px',
  full: '9999px',
}


// ─── Typography ──────────────────────────────────────────────────

export const FONT = {
  serif:  "'Playfair Display', serif",       // headlines
  sans:   "'DM Sans', sans-serif",           // body
  mono:   "ui-monospace, SFMono-Regular, monospace",
}

export const FONT_SIZE = {
  xs:   '10px',
  sm:   '11px',
  base: '13px',
  md:   '14px',
  lg:   '15px',
  xl:   '17px',
  '2xl': '20px',
  '3xl': '24px',
  '4xl': '32px',
}

export const FONT_WEIGHT = {
  regular: 400,
  medium:  500,
  semibold: 600,
  bold:    700,
}


// ─── Shadows ─────────────────────────────────────────────────────

export const SHADOW = {
  sm:   '0 1px 2px rgba(0, 0, 0, 0.2)',
  md:   '0 4px 12px rgba(0, 0, 0, 0.3)',
  lg:   '0 8px 24px rgba(0, 0, 0, 0.4)',
  xl:   '0 16px 48px rgba(0, 0, 0, 0.5)',
}


// ─── Z-index scale ───────────────────────────────────────────────

export const Z = {
  dropdown: 20,
  sticky:   30,
  banner:   40,
  modal:    100,
  popover:  200,
  toast:    1000,
  fullscreen: 9999,
}


// ─── Touch targets (a11y) ────────────────────────────────────────

export const TOUCH = {
  min:    '36px',  // minimum acceptable target
  ideal:  '44px',  // Apple HIG ideal target
  large:  '48px',  // primary CTAs
}


// ─── Default export for "import T from '.../design-tokens'" ─────

const TOKENS = {
  NEUTRAL, BUYER, ADMIN, STATUS, TRUST_BADGE,
  SPACING, RADIUS, FONT, FONT_SIZE, FONT_WEIGHT,
  SHADOW, Z, TOUCH,
}

export default TOKENS
