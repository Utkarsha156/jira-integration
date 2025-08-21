import os
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================================================
# 1. DatabaseManager Class (UPDATED with IST timestamp and log message)
# ==============================================================================
class DatabaseManager:
    """A simple connection manager for the webhook."""
    def __init__(self):
        self.conn_string = os.environ.get('DATABASE_URL')
        if not self.conn_string:
            raise ValueError("FATAL: DATABASE_URL environment variable not set.")
        self.conn = None

    def __enter__(self):
        try:
            self.conn = psycopg2.connect(self.conn_string)
            return self.conn
        except psycopg2.OperationalError as e:
            print(f"❌ Error connecting to database: {e}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def update_mapping_timestamp(self, jira_key):
        """Updates the updated_at timestamp for a given mapping to IST."""
        with self as conn:
            with conn.cursor() as cur:
                # MODIFIED: Explicitly sets the timestamp to the 'Asia/Kolkata' time zone.
                cur.execute(
                    "UPDATE jira_cloobot_mapping SET updated_at = NOW() AT TIME ZONE 'Asia/Kolkata' WHERE jira_issue_key = %s",
                    (jira_key,)
                )
                conn.commit()
                print(f"  -> DB Record Updated: Timestamp for {jira_key} refreshed to IST.")

    def delete_mapping(self, jira_key):
        """Deletes a mapping record from the database."""
        with self as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM jira_cloobot_mapping WHERE jira_issue_key = %s",
                    (jira_key,)
                )
                conn.commit()
                # MODIFIED: Changed "removed" to "deleted"
                print(f"  -> DB Record Deleted: Mapping for {jira_key} deleted.")


# ==============================================================================
# 2. Webhook Endpoint (No changes needed here, logic is in DatabaseManager)
# ==============================================================================
@app.route('/webhook/jira', methods=['POST'])
def jira_webhook():
    print("\n--- Webhook Received from Jira ---")
    data = request.get_json()
    
    event_type = data.get('webhookEvent')
    issue = data.get('issue', {})
    jira_key = issue.get('key')
    
    if not jira_key:
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    print(f"Processing event '{event_type}' for Jira issue: {jira_key}")
    
    try:
        db_manager = DatabaseManager()
        
        with db_manager as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT cloobot_item_id FROM jira_cloobot_mapping WHERE jira_issue_key = %s', (jira_key,))
                mapping_result = cur.fetchone()

        if not mapping_result:
            print(f"No mapping found for Jira key: {jira_key}. Ignoring.")
            return jsonify({"status": "ok", "message": "No mapping found"})
            
        cloobot_id = mapping_result[0]
        print(f"Found corresponding Cloobot ID: {cloobot_id}")

        if event_type == 'jira:issue_updated':
            db_manager.update_mapping_timestamp(jira_key)
            print(f"Simulating update to Cloobot item {cloobot_id}...")

        elif event_type == 'jira:issue_deleted':
            db_manager.delete_mapping(jira_key)
            print(f"Simulating deletion of Cloobot item {cloobot_id}...")
        
        else:
            print(f"  - Received an unhandled event type: {event_type}")
            
        return jsonify({"status": "ok", "message": "Webhook processed"})

    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500

# This part is for running the server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)