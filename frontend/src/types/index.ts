export type SkillLevel = 'HB' | 'LI' | 'MB';
export type PaymentStatus = 'unpaid' | 'pending_verification' | 'verified_paid';
export type SessionStatus = 'internal' | 'published' | 'completed';
export type PlayerType = 'registered' | 'guest';

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

export interface Session {
  id: string;
  date: string;
  time: string;
  venue_id: string;
  courts_booked: number;
  skill_level: SkillLevel;
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

export interface PnLResult {
  total_income: number;
  court_cost: number;
  shuttle_cost: number;
  net: number;
  external_paid_count: number;
  shuttles_used: number;
}
