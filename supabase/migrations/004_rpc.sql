CREATE OR REPLACE FUNCTION decrement_positions_after(p_session_id UUID, p_position INT)
RETURNS VOID LANGUAGE sql AS $$
  UPDATE roster_entries
  SET position = position - 1
  WHERE session_id = p_session_id
    AND position > p_position
    AND NOT is_waitlisted;
$$;
