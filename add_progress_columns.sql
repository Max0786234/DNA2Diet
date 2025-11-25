-- Add progress tracking columns
ALTER TABLE analyses ADD COLUMN progress_step VARCHAR(255) DEFAULT NULL;
ALTER TABLE analyses ADD COLUMN progress_percent INT DEFAULT 0;

