import os
import psycopg2
import requests
import base64
from flask import Flask, request, jsonify
import traceback

app = Flask(__name__)


JIRA_CONFIG = {
    'base_url': os.environ.get('JIRA_BASE_URL'),
    'email': os.environ.get('JIRA_EMAIL'),
    'api_token': os.environ.get('JIRA_API_TOKEN'),
}


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
            print(f"Error connecting to database: {e}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def update_mapping_timestamp(self, jira_key):
        """Silently updates the updated_at timestamp for a given mapping to IST."""
        with self as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE jira_cloobot_mapping SET updated_at = NOW() AT TIME ZONE 'Asia/Kolkata' WHERE jira_issue_key = %s",
                    (jira_key,)
                )
                conn.commit()

    def delete_mapping(self, jira_keys_to_delete):
        """Deletes one or more mapping records from the database."""
        if not jira_keys_to_delete: return
        with self as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM jira_cloobot_mapping WHERE jira_issue_key IN %s",
                    (tuple(jira_keys_to_delete),)
                )
                conn.commit()
                deleted_keys_str = ", ".join(jira_keys_to_delete)
                print(f"  -> DB Records Deleted: Mappings for {deleted_keys_str} deleted.")
    
    def insert_mapping(self, cloobot_item_id, jira_issue_id, jira_issue_key):
        """Inserts a new mapping record into the database."""
        with self as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jira_cloobot_mapping (cloobot_item_id, jira_issue_id, jira_issue_key)
                    VALUES (%s, %s, %s) ON CONFLICT (jira_issue_key) DO NOTHING;
                    """,
                    (str(cloobot_item_id), str(jira_issue_id), str(jira_issue_key))
                )
                conn.commit()
                print(f"  -> DB Record Inserted: Cloobot ID {cloobot_item_id} -> Jira Key {jira_issue_key}")



@app.route('/webhook/jira', methods=['POST'])
def jira_webhook():
    print("\n--- Webhook Received from Jira ---")
    data = request.get_json()
    
    event_type = data.get('webhookEvent')
    issue_data = data.get('issue', {})
    jira_key = issue_data.get('key')
    
    if not jira_key:
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    print(f"Processing event '{event_type}' for Jira issue: {jira_key}")
    db_manager = DatabaseManager()

    try:
        if not all([JIRA_CONFIG['email'], JIRA_CONFIG['api_token'], db_manager.conn_string]):
             print("FATAL: Server environment variables (JIRA_EMAIL, JIRA_API_TOKEN, DATABASE_URL) are not set.")
             return jsonify({"status": "error", "message": "Server configuration missing"}), 500

        if event_type == 'jira:issue_created':
            jira_issue_id = issue_data.get('id')
           
            cloobot_id_placeholder = f"JIRA_CREATED_{jira_key}"
            db_manager.insert_mapping(cloobot_id_placeholder, jira_issue_id, jira_key)
            print(f"  -> New issue created in Jira. Added to mapping table.")

        elif event_type == 'jira:issue_updated':
            db_manager.update_mapping_timestamp(jira_key)
            changelog = data.get('changelog', {})
            if changelog and 'items' in changelog:
                for item in changelog['items']:
                    if item.get('field', '').lower() == 'summary':
                        print(f"  -> Issue Renamed: from '{item.get('fromString')}' to '{item.get('toString')}'")
            print(f"Simulating update to Cloobot item...")

        elif event_type == 'jira:issue_deleted':
            issue_type = issue_data.get('fields', {}).get('issuetype', {}).get('name', '')
            keys_to_delete = [jira_key]

            if issue_type.lower() == 'epic':
                print(f"  -> Epic {jira_key} deleted. Finding all child issues to also delete from mapping...")
                auth_string = f"{JIRA_CONFIG['email']}:{JIRA_CONFIG['api_token']}"
                auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
                headers = {'Authorization': f'Basic {auth_b64}', 'Content-Type': 'application/json'}
                
                jql = f'parent = "{jira_key}"'
                search_url = f"{JIRA_CONFIG['base_url']}/rest/api/3/search"
                response = requests.post(search_url, headers=headers, json={"jql": jql, "fields": ["key"]})
                
                if response.status_code == 200:
                    child_issues = response.json().get('issues', [])
                    child_keys = [issue['key'] for issue in child_issues]
                    if child_keys:
                        print(f"  -> Found child issues: {', '.join(child_keys)}")
                        keys_to_delete.extend(child_keys)
                else:
                    print(f"  -> WARNING: Could not fetch child issues. API responded with {response.status_code}: {response.text}")

            db_manager.delete_mapping(keys_to_delete)
            print(f"Simulating deletion in Cloobot...")
            
        return jsonify({"status": "ok", "message": "Webhook processed"})

    except Exception as e:
        print(f"Error processing webhook: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
