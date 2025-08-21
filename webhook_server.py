import os
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================================================
# 1. DatabaseManager Class (Webhook Version)
# ==============================================================================
class DatabaseManager:
    """A simple connection manager for the webhook."""
    def __init__(self):
        # You can hardcode the URL here if you prefer, but environment variables are safer
        self.conn_string = os.environ.get('DATABASE_URL', "postgresql://user:password@host/db")
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

# ==============================================================================
# 2. Webhook Endpoint (UPDATED WITH DETAILED LOGIC)
# ==============================================================================
@app.route('/webhook/jira', methods=['POST'])
def jira_webhook():
    print("\n--- Webhook Received from Jira ---")
    data = request.get_json()
    
    # --- Extract core information from the payload ---
    event_type = data.get('webhookEvent')
    issue = data.get('issue', {})
    jira_key = issue.get('key')
    
    if not jira_key:
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    print(f"Processing event '{event_type}' for Jira issue: {jira_key}")
    
    try:
        with DatabaseManager() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT cloobot_item_id FROM jira_cloobot_mapping WHERE jira_issue_key = %s', (jira_key,))
                mapping_result = cur.fetchone()
            
            if not mapping_result:
                print(f"No mapping found for Jira key: {jira_key}. Ignoring.")
                return jsonify({"status": "ok", "message": "No mapping found"})
                
            cloobot_id = mapping_result[0]
            print(f"Found corresponding Cloobot ID: {cloobot_id}")

            # --- Detailed Logging Logic ---
            if event_type == 'jira:issue_updated':
                changelog = data.get('changelog', {})
                if changelog and 'items' in changelog:
                    print("Change Details:")
                    for item in changelog['items']:
                        field = item.get('field', 'Unknown Field')
                        old_value = item.get('fromString', 'N/A')
                        new_value = item.get('toString', 'N/A')
                        print(f"  - Field '{field}' was changed from '{old_value}' to '{new_value}'")
                else:
                    print("  - Issue was updated, but no specific field changes were provided in the changelog.")

            elif event_type == 'jira:issue_deleted':
                print("Change Details:")
                print(f"  - Issue {jira_key} was deleted.")
            
            else:
                print(f"  - Received an unhandled event type: {event_type}")

            # TODO: Add your logic here to update the Cloobot system.
            print(f"Simulating update to Cloobot item {cloobot_id}...")
            
            return jsonify({"status": "ok", "message": "Webhook processed"})

    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500

# This part is for running the server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)