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

# ==============================================================================
# 2. Webhook Endpoint
# ==============================================================================
@app.route('/webhook/jira', methods=['POST'])
def jira_webhook():
    print("Webhook received from Jira...")
    data = request.get_json()
    issue = data.get('issue', {})
    jira_key = issue.get('key')
    
    if not jira_key:
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    print(f"Processing update for Jira issue: {jira_key}")
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
            
            # TODO: Add your logic here to update the Cloobot system.
            print(f"Simulating update to Cloobot item {cloobot_id}...")
            
            return jsonify({"status": "ok", "message": "Webhook processed"})

    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500

# This part is for running the server (e.g., when deployed on Render)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)