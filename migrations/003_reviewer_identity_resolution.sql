-- Permit protected human overrides after an explicit reviewer entity resolution,
-- including decisions that were intentionally left unlinked by automation.

ALTER TABLE human_overrides
    ADD COLUMN source_record_id uuid;

ALTER TABLE human_overrides DISABLE TRIGGER human_overrides_are_immutable;

UPDATE human_overrides AS override
   SET source_record_id = decision.source_record_id
  FROM classification_decisions AS decision
 WHERE decision.id = override.classification_decision_id;

ALTER TABLE human_overrides ENABLE TRIGGER human_overrides_are_immutable;

ALTER TABLE human_overrides
    ALTER COLUMN source_record_id SET NOT NULL;

ALTER TABLE human_overrides
    DROP CONSTRAINT human_overrides_classification_decision_id_competitor_enti_fkey,
    ADD CONSTRAINT human_overrides_classification_decision_id_fkey
        FOREIGN KEY (classification_decision_id) REFERENCES classification_decisions(id),
    ADD CONSTRAINT human_overrides_source_record_id_fkey
        FOREIGN KEY (source_record_id) REFERENCES source_records(id);

CREATE INDEX human_overrides_source_record_id_idx
    ON human_overrides (source_record_id);

CREATE FUNCTION validator_require_override_entity_link()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    linked_entity_id uuid;
    decision_source_record_id uuid;
BEGIN
    SELECT decision.source_record_id
      INTO decision_source_record_id
      FROM classification_decisions AS decision
     WHERE decision.id = NEW.classification_decision_id;

    IF decision_source_record_id IS DISTINCT FROM NEW.source_record_id THEN
        RAISE EXCEPTION 'a protected override source record must match its classification decision';
    END IF;

    SELECT link.competitor_entity_id
      INTO linked_entity_id
      FROM entity_links AS link
     WHERE link.source_record_id = NEW.source_record_id;

    IF linked_entity_id IS NULL OR linked_entity_id IS DISTINCT FROM NEW.competitor_entity_id THEN
        RAISE EXCEPTION 'a protected override requires an entity link for its source record';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER human_overrides_require_reviewer_entity_link
BEFORE INSERT ON human_overrides
FOR EACH ROW EXECUTE FUNCTION validator_require_override_entity_link();
