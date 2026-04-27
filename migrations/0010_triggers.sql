-- Migration 0010 : Fonction notify_event + triggers PG NOTIFY.
-- Référence : docs/specs/01-data-model.md § Section 6.

CREATE OR REPLACE FUNCTION notify_event() RETURNS trigger AS $$
DECLARE
    channel text;
    payload jsonb;
BEGIN
    channel := TG_ARGV[0];
    payload := jsonb_build_object(
        'table', TG_TABLE_NAME,
        'op', TG_OP,
        'tenant_id', NEW.tenant_id,
        'id', NEW.id,
        'status', NEW.status
    );
    PERFORM pg_notify(channel, payload::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER source_items_notify
    AFTER UPDATE OF status ON source_items
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('source_items_changes');

CREATE TRIGGER runs_notify
    AFTER INSERT OR UPDATE OF status ON runs
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('runs_changes');

CREATE TRIGGER workers_notify
    AFTER UPDATE OF status ON transcription_workers
    FOR EACH ROW
    EXECUTE FUNCTION notify_event('workers_changes');

CREATE TRIGGER keys_notify
    AFTER UPDATE OF status ON user_transcription_keys
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_event('keys_changes');
