// how "per status type" bonuses (Condition Overload, Galvanized Aptitude/Savvy/Shot, Secondary Shiver) apply,
// per wiki.warframe.com/w/Condition_Overload_(Mechanic) (pulled Oct 2026):
//   "Adding" type:      base x [(most bonuses x other multipliers) + CO]   (intended, most common)
//   "Multiplying" type: base x most bonuses x CO x other multipliers       (mostly projectiles, not intended)
// scale = the wiki's "CO relative to base" column: charged shots that only count the uncharged base (bows 50%,
// Ballistica 25%), hitscan explosions that count the hitscan hit (Opticor 250%)...
// which damage gets it at all (wiki): hitscan and its explosions on the directly hit enemy, projectiles, embedded
// clouds on the embedded enemy, beams. projectile explosion radii never do.
// the wiki page cut off for me partway through the secondaries (at Ballistica), so the rest of the secondaries and
// the melee rows come from rainy's GunCO sheet (38.0.12 edition, Feb 2025), marked source 'sheet'. wiki wins
// wherever both have a row
import type { Attack, Weapon } from '../types'

export type CoMode = 'add' | 'multiply' | 'none'

export interface CoBehavior {
  mode: CoMode
  scale: number // 1 = full bonus, 0.25 = Ballistica charged shot etc.
  source: 'wiki' | 'sheet' | 'default' | 'override'
  note?: string
}

interface CoRule {
  weapons: string[]
  attack: RegExp // matched against warframe-items attack names, which differ from the wiki's wording
  mode: CoMode
  scale?: number
  note?: string
  sheet?: boolean // from the GunCO sheet, not the wiki
}

const BOW_CHARGED = 'CO only counts the uncharged base damage'
const DIRECT_ONLY = 'Only on the enemy the hitscan shot hits directly, and scales off the hitscan damage'

const CO_RULES: CoRule[] = [
  // ---- primaries (wiki) ----
  { weapons: ['Acceltra'], attack: /^Rocket Impact$/, mode: 'add', scale: 0.743, note: 'CO uses 26 damage instead of the listed 35' },
  { weapons: ['Aeolak'], attack: /^(Normal Attack|Alt-Fire)$/, mode: 'multiply' },
  { weapons: ['Alternox', 'Alternox Prime'], attack: /^Normal Attack$/, mode: 'multiply' },
  { weapons: ['Ambassador'], attack: /^Charged AoE$/, mode: 'add', scale: 0.75, note: DIRECT_ONLY },
  { weapons: ['Arca Plasmor', 'Tenet Arca Plasmor'], attack: /^Normal Attack$/, mode: 'multiply' },
  { weapons: ['Basmu'], attack: /^Auto$/, mode: 'multiply' },
  { weapons: ['Battacor'], attack: /^Normal Attack$/, mode: 'multiply' },
  { weapons: ['Braton', 'Mk1-Braton', 'Braton Prime', 'Braton Vandal'], attack: /^Incarnon Form AoE$/, mode: 'add', scale: 0.95, note: DIRECT_ONLY },
  { weapons: ['Bubonico'], attack: /^(Auto|Burst)$/, mode: 'multiply' },
  { weapons: ['Burston', 'Burston Prime'], attack: /^Incarnon Form Radial Attack$/, mode: 'add', scale: 0.24, note: DIRECT_ONLY },
  { weapons: ['Buzlok'], attack: /^(Normal Attack|Beacon)$/, mode: 'multiply' },
  { weapons: ['Cedo', 'Cedo Prime'], attack: /^Alt-Fire Glaive$/, mode: 'multiply' },
  { weapons: ['Cernos', 'Cernos Prime', 'Rakta Cernos', 'Mutalist Cernos', 'Daikyu Prime', 'Dread', 'Paris', 'Paris Prime', 'Mk1-Paris', 'Kuva Drakgoon'],
    attack: /^Charged( Horizontal\/Vertical)? Shot$/, mode: 'add', scale: 0.5, note: BOW_CHARGED },
  { weapons: ['Coda Bassocyst'], attack: /^Normal Attack$/, mode: 'multiply' },
  { weapons: ['Coda Bassocyst'], attack: /^Alt-Fire$/, mode: 'none' },
  { weapons: ['Coda Hema', 'Hema', 'Exergis', 'Steflos', 'Shedu'], attack: /^Normal Attack$/, mode: 'multiply' },
  { weapons: ['Mutalist Cernos'], attack: /^Uncharged Shot$/, mode: 'multiply' },
  // the data has one cloud for both shots. uncharged multiplies, the charged one adds off the 205 arrow base (4100%),
  // I go with the uncharged one so it isn't overrated
  { weapons: ['Mutalist Cernos'], attack: /^Toxin Cloud$/, mode: 'multiply', note: 'Uncharged cloud. The charged cloud instead adds CO based on the arrow\'s 205 damage' },
  { weapons: ['Cinta'], attack: /^(Quick Shot|Charged Shot|Perfect Shot)$/, mode: 'multiply' },
  { weapons: ['Drakgoon'], attack: /^Charged Shot$/, mode: 'add', scale: 0.57, note: BOW_CHARGED },
  { weapons: ['Dread', 'Paris', 'Paris Prime', 'Mk1-Paris'], attack: /^Incarnon Form/, mode: 'multiply' },
  { weapons: ['Evensong'], attack: /^Charged Shot$/, mode: 'add', scale: 0.65, note: BOW_CHARGED },
  { weapons: ['Evensong'], attack: /^Charged Radial Attack$/, mode: 'none' },
  { weapons: ['Felarx'], attack: /^(Normal Attack|Incarnon Form)$/, mode: 'multiply' },
  { weapons: ['Ferrox'], attack: /^Radial Attack$/, mode: 'add', scale: 3.5, note: DIRECT_ONLY },
  { weapons: ['Tenet Ferrox'], attack: /^Radial Attack$/, mode: 'add', scale: 3.33, note: DIRECT_ONLY },
  { weapons: ['Fulmin', 'Fulmin Prime'], attack: /^Semi-Auto Mode$/, mode: 'multiply' },
  { weapons: ['Harpak'], attack: /^Harpoon$/, mode: 'multiply' },
  { weapons: ['Javlok'], attack: /^Projectile Impact$/, mode: 'multiply' },
  { weapons: ['Lanka'], attack: /^Charged Shot$/, mode: 'add', scale: 0.38, note: 'CO only counts the partially charged base damage' },
  { weapons: ['Latron', 'Latron Prime', 'Latron Wraith', 'Miter'], attack: /^Incarnon Form$/, mode: 'multiply' },
  { weapons: ['Latron', 'Latron Prime', 'Latron Wraith'], attack: /^Incarnon Form AoE$/, mode: 'none', note: 'CO does not apply to the AoE in any way' },
  { weapons: ['Miter'], attack: /^Charged Shot$/, mode: 'add', scale: 0.4, note: 'CO only counts the partially charged base damage' },
  { weapons: ['Nataruk'], attack: /^(Charged Shot|Perfect Shot)$/, mode: 'multiply' },
  { weapons: ['Nunchasa'], attack: /^Alt-Fire$/, mode: 'multiply' },
  { weapons: ['Opticor'], attack: /^(Charged|Quick) Shot AoE$/, mode: 'add', scale: 2.5, note: DIRECT_ONLY },
  { weapons: ['Opticor Vandal'], attack: /^Charged Shot AoE$/, mode: 'add', scale: 2, note: DIRECT_ONLY },
  { weapons: ['Paracyst'], attack: /^Infested Harpoon/, mode: 'multiply' },
  { weapons: ['Phantasma', 'Phantasma Prime'], attack: /^Cluster Bombs Impact$/, mode: 'multiply' },
  { weapons: ['Proboscis Cernos'], attack: /^(Appendages|Charged Shot Explosion)$/, mode: 'none' },
  { weapons: ['Quellor'], attack: /^Alt-Fire$/, mode: 'multiply' },
  { weapons: ['Scourge', 'Scourge Prime'], attack: /^Spear Throw( Impact)?$/, mode: 'multiply' },
  { weapons: ['Stahlta'], attack: /^(Auto|Alt-Fire)$/, mode: 'multiply' },
  { weapons: ['Tenet Envoy'], attack: /^Grenade Impact$/, mode: 'multiply' },
  { weapons: ['Torid'], attack: /^(Grenade Impact|Poison Cloud)$/, mode: 'multiply' },
  { weapons: ['Trumna', 'Trumna Prime'], attack: /^Auto AoE$/, mode: 'add', scale: 1.64, note: DIRECT_ONLY },
  { weapons: ['Trumna', 'Trumna Prime'], attack: /^Grenade Impact$/, mode: 'multiply' },
  { weapons: ['Zarr'], attack: /^Cannon Mode Cluster Bomb Contact$/, mode: 'add', scale: 1.67, note: 'Uses the main projectile\'s 25 damage' },
  { weapons: ['Kuva Zarr'], attack: /^Cannon Mode Cluster Bomb Contact$/, mode: 'add', scale: 3.33, note: 'Uses the main projectile\'s 50 damage' },
  { weapons: ['Zhuge Prime'], attack: /^Arrow Explosion$/, mode: 'none' },
  // ---- primaries the wiki table doesn't have (sheet) ----
  { weapons: ['Kuva Bramma'], attack: /^Cluster Bomb Contact$/, mode: 'add', scale: 4.92, note: 'Uses the main arrow\'s damage', sheet: true },
  { weapons: ['Zylok', 'Zylok Prime'], attack: /^Incarnon Form Radial Attack$/, mode: 'add', scale: 0.59, note: DIRECT_ONLY, sheet: true },
  // ---- secondaries (wiki, down to Ballistica) ----
  { weapons: ['Akarius Prime'], attack: /^Rocket Impact$/, mode: 'multiply' },
  { weapons: ['Aegrit'], attack: /^Direct Hit$/, mode: 'multiply' },
  { weapons: ['Angstrum', 'Prisma Angstrum'], attack: /^Incarnon Form$/, mode: 'multiply' },
  { weapons: ['Azima'], attack: /^Turret/, mode: 'none', note: 'Bug: should count as hitscan but gets nothing' },
  { weapons: ['Balefire Charger', 'Balefire Charger Prime'], attack: /./, mode: 'none', note: 'Bug: should apply but doesn\'t' },
  { weapons: ['Ballistica'], attack: /^Charged Shot$/, mode: 'add', scale: 0.25, note: BOW_CHARGED },
  // ---- the rest of the secondaries (sheet) ----
  { weapons: ['Akarius'], attack: /^Rocket Impact$/, mode: 'multiply', sheet: true },
  { weapons: ['Rakta Ballistica'], attack: /^Charged Shot$/, mode: 'add', scale: 0.25, note: BOW_CHARGED, sheet: true },
  { weapons: ['Ballistica Prime'], attack: /^Charged Shot$/, mode: 'add', scale: 0.5, note: BOW_CHARGED, sheet: true },
  // Secondary Shiver's wiki page: multiplicative with Hornet Strike on these. the sheet agrees
  { weapons: ['Cyanex', 'Catchmoon', 'Epitaph', 'Epitaph Prime', 'Seer', 'Kuva Seer', 'Sepulcrum', 'Tenet Spirex'],
    attack: /^(?!.*(AoE|Explosion|Radial)).*/, mode: 'multiply', note: 'From the Secondary Shiver wiki page' },
  { weapons: ['Glory'], attack: /./, mode: 'none', sheet: true },
  { weapons: ['Kulstar'], attack: /^Cluster Bombs$/, mode: 'add', scale: 2.67, note: 'Uses the main rocket\'s damage', sheet: true },
  { weapons: ['Kunai'], attack: /^Incarnon Form$/, mode: 'multiply', note: 'Gets the Evolution base damage too', sheet: true },
  { weapons: ['Onos'], attack: /^Normal Attack$/, mode: 'multiply', sheet: true },
  { weapons: ['Pox'], attack: /^Poison Cloud$/, mode: 'add', scale: 2.5, note: 'Embedded enemy only, scales off the contact hit', sheet: true },
  { weapons: ['Sonicor'], attack: /./, mode: 'none', note: 'Bug: should apply but doesn\'t', sheet: true },
  { weapons: ['Stug'], attack: /./, mode: 'none', sheet: true },
  { weapons: ['Tenet Diplos'], attack: /^Lock-on Mode$/, mode: 'multiply', sheet: true },
  { weapons: ['Tenet Plinx'], attack: /^Alt-Fire$/, mode: 'multiply', sheet: true },
  { weapons: ['Zakti', 'Zakti Prime'], attack: /^(Dart Impact|Normal Attack)$/, mode: 'multiply', sheet: true },
  { weapons: ['Zymos'], attack: /^Homing Spore Contact$/, mode: 'multiply', sheet: true },
]

export function resolveCoBehavior(weapon: Weapon, attack: Attack): CoBehavior {
  const rule = CO_RULES.find((candidate) => candidate.weapons.includes(weapon.name) && candidate.attack.test(attack.name))
  if (rule) return { mode: rule.mode, scale: rule.scale ?? 1, source: rule.sheet ? 'sheet' : 'wiki', note: rule.note }
  // unlisted hitscan/beam explosions: the wiki says the directly hit enemy gets it ("Hitscan explosions (directly hit
  // target only)", "Beams, including beam AoE"), projectile explosions never do
  if (attack.hitscanAoE) return { mode: 'add', scale: 1, source: 'default', note: DIRECT_ONLY }
  return attack.isAoE
    ? { mode: 'none', scale: 1, source: 'default', note: 'Projectile explosion radius doesn\'t get CO' }
    : { mode: 'add', scale: 1, source: 'default' }
}

export const CO_MODE_LABELS: Record<CoMode, string> = { add: 'Additive', multiply: 'Multiplicative', none: 'Doesn\'t apply' }
