export type SkillLevel = 'LB' | 'MB' | 'HB' | 'LI' | 'MI' | 'HI' | 'A';
export type PaymentStatus = 'unpaid' | 'pending_verification' | 'verified_paid';
export type SessionStatus = 'internal' | 'published' | 'completed' | 'cancelled';
export type PlayerType = 'registered' | 'guest';

export const SKILL_LEVELS: SkillLevel[] = ['LB', 'MB', 'HB', 'LI', 'MI', 'HI', 'A'];

export function skillRangeLabel(min: SkillLevel, max: SkillLevel): string {
  return min === max ? min : `${min} – ${max}`;
}

export interface Player {
  id: string;
  name: string;
  skill_level: SkillLevel;
  phone: string | null;
  is_internal: boolean;
  is_admin: boolean;
  telegram_id: number | null;
  notes: string | null;
}

export interface Venue {
  id: string;
  name: string;
  court_cost_per_hour: number;
  default_pub_fee: number;
}

export interface CourtSlot {
  id: string;
  session_id: string;
  court_label: string;
  from_time: string;
  to_time: string;
  booker_player_id: string;
}

export interface CourtSlotCreate {
  court_label: string;
  from_time: string;
  to_time: string;
  booker_player_id: string;
}

export interface Session {
  id: string;
  date: string;
  start_time: string;
  end_time: string;
  duration_hours: number;
  venue_id: string;
  courts_booked: string;
  num_courts: number;
  min_skill_level: SkillLevel;
  max_skill_level: SkillLevel;
  pub_fee: number;
  max_pax: number;
  status: SessionStatus;
  telegram_message_id: string | null;
  paynow_player_id: string | null;
}

export interface RosterEntry {
  id: string;
  session_id: string;
  player_id: string | null;
  guest_name: string | null;
  position: number;
  is_waitlisted: boolean;
  player_type: PlayerType;
  payment_status: PaymentStatus;
}

export interface ShuttleBatch {
  id: string;
  batch_name: string;
  brand: string;
  cost_per_tube: number;
  shuttles_per_tube: number;
  cost_per_shuttle: number;
  remaining_count: number;
  is_active: boolean;
  owner_label: string | null;
}

export interface BookerReimbursement {
  player_id: string;
  player_name: string;
  amount: number;
}

export interface PnLResult {
  session_id: string;
  total_fees_collected: number;
  court_cost: number;
  shuttle_cost: number;
  net: number;
  external_paid_count: number;
  total_roster_count: number;
  booker_breakdown: BookerReimbursement[];
}

export interface FundEntry {
  id: string
  description: string
  amount: number  // positive = income; negative = expense
  created_at: string
}

export interface FundBalance {
  entries: FundEntry[]
  entries_total: number
}
