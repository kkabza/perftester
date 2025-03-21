import requests
from datetime import datetime, timedelta
import json

class AppInsightsClient:
    def __init__(self, api_key, app_id):
        self.api_key = api_key
        self.app_id = app_id
        self.base_url = "https://api.applicationinsights.io/v1/apps"
        self.headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json"
        }

    def _get_time_range(self, time_range):
        now = datetime.utcnow()
        ranges = {
            "1h": timedelta(hours=1),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30)
        }
        delta = ranges.get(time_range, timedelta(hours=24))
        start_time = now - delta
        return start_time.isoformat(), now.isoformat()

    def search_command(self, command_id, time_range="24h"):
        start_time, end_time = self._get_time_range(time_range)
        
        # Query for command details
        query = f"""
        traces
        | where customDimensions.commandId == "{command_id}"
        | where timestamp between(datetime("{start_time}") .. datetime("{end_time}"))
        | project timestamp, message, severityLevel, customDimensions
        | order by timestamp asc
        """
        
        try:
            response = requests.post(
                f"{self.base_url}/{self.app_id}/query",
                headers=self.headers,
                json={"query": query}
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Process the results
            if not data.get("tables") or not data["tables"][0].get("rows"):
                return {
                    "success": False,
                    "message": "No command data found for the specified ID",
                    "commandDetails": None,
                    "timeline": None
                }
            
            # Extract command details and timeline
            rows = data["tables"][0]["rows"]
            command_details = {
                "start_time": rows[0][0],
                "end_time": rows[-1][0],
                "total_events": len(rows),
                "severity_levels": list(set(row[2] for row in rows)),
                "custom_dimensions": rows[0][3] if rows[0][3] else {}
            }
            
            timeline = [
                {
                    "timestamp": row[0],
                    "message": row[1],
                    "severity": row[2],
                    "details": row[3]
                }
                for row in rows
            ]
            
            return {
                "success": True,
                "message": "Command data retrieved successfully",
                "commandDetails": command_details,
                "timeline": timeline
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "message": f"Error querying App Insights: {str(e)}",
                "commandDetails": None,
                "timeline": None
            } 