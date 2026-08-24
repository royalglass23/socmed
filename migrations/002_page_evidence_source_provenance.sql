-- Preserve every immutable Source Record when multiple records share identical page evidence.

ALTER TABLE page_evidence
    ADD CONSTRAINT page_evidence_id_validation_run_key UNIQUE (id, validation_run_id);

CREATE TABLE page_evidence_source_records (
    page_evidence_id uuid NOT NULL REFERENCES page_evidence(id) ON DELETE CASCADE,
    source_record_id uuid NOT NULL,
    validation_run_id uuid NOT NULL,
    PRIMARY KEY (page_evidence_id, source_record_id),
    FOREIGN KEY (source_record_id, validation_run_id) REFERENCES source_records(id, validation_run_id),
    FOREIGN KEY (page_evidence_id, validation_run_id) REFERENCES page_evidence(id, validation_run_id)
);

INSERT INTO page_evidence_source_records (page_evidence_id, source_record_id, validation_run_id)
SELECT id, source_record_id, validation_run_id
  FROM page_evidence;

CREATE INDEX page_evidence_source_records_source_record_id_idx
    ON page_evidence_source_records (source_record_id);

CREATE OR REPLACE FUNCTION validator_require_completed_run_audit_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.outcome = 'completed' THEN
        IF EXISTS (
            SELECT 1
              FROM source_records AS source
             WHERE source.validation_run_id = NEW.id
               AND NOT EXISTS (
                   SELECT 1
                     FROM classification_decisions AS decision
                    WHERE decision.source_record_id = source.id
                      AND decision.validation_run_id = NEW.id
               )
        ) THEN
            RAISE EXCEPTION 'a completed validation run requires a decision for every source record';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM classification_decisions AS decision
             WHERE decision.validation_run_id = NEW.id
               AND NOT EXISTS (
                   SELECT 1
                     FROM page_evidence_source_records AS evidence_link
                    WHERE evidence_link.source_record_id = decision.source_record_id
                      AND evidence_link.validation_run_id = NEW.id
               )
               AND NOT EXISTS (
                   SELECT 1
                     FROM fetch_failures AS failure
                    WHERE failure.source_record_id = decision.source_record_id
                      AND failure.validation_run_id = NEW.id
               )
        ) THEN
            RAISE EXCEPTION 'a completed validation decision requires evidence or a captured fetch failure';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
