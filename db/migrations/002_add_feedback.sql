-- FEN-7: feedback logging (thumbs up / down per query-response pair)

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    interaction_id UUID NOT NULL REFERENCES chat_interactions(id),
    rating VARCHAR(10) NOT NULL CHECK (rating IN ('up', 'down')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feedback_interaction_id ON feedback(interaction_id);