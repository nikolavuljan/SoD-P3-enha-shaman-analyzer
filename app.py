from flask import Flask, render_template, request
import requests
import json
import os

app = Flask(__name__)
tokenURL = "https://www.warcraftlogs.com/oauth/token"
API_URL = "https://www.warcraftlogs.com/api/v2/client"

# Manually defined dictionary of spell IDs to names
# Needs to be updated every tier with spells and buffs that are the part of a rotation
spell_names = {
    437009: "Totemic Projection",
    10447: "Flame Shock",
    17364: "Stormstrike",
    15207: "Lightning Bolt",
    10413: "Earth shock",
    408507: "Lava Lash",
    2860: "Chain Lightning",
    10431: "Lightning Shield",
    20572: "Blood Fury",
    446698: "Fervor of the Temple Explorer",
    15366: "Songflower Serenade",
    23768: "Sayge's Dark Fortune of Damage",
    446335: "Atal'ai Mojo of War",
}


def get_token(store: bool = True):  # Gets token used for credential header
    data = {"grant_type": "client_credentials"}
    auth = (os.environ.get("userID"), os.environ.get("userSecret")
            )
    with requests.Session() as session:
        response = session.post(tokenURL, data=data, auth=auth)
    if store and response.status_code == 200:
        store_token(response)
    return response


def store_token(response):  # Stores token in a json .credentials.json
    try:
        with open(".credentials.json", mode="w+", encoding="utf-8") as f:
            json.dump(response.json(), f)
    except OSError as e:
        print(f"Failed to store token: {e}")
        return None

#The two functions above were only used in generating .credentials.json, as it is a permanent token

def retrieve_headers():  # Reads token from .credentials.json
    try:
        with open(".credentials.json", mode="r", encoding="utf-8") as f:
            access_token = json.load(f)["access_token"]
        return {"Authorization": f"Bearer {access_token}"}
    except Exception as e:
        print(f"Failed to load credentials: {e}")
        return {}


def fetch_report_details(
    report_id
):  # Fetches all fights and players as a json, and then returns them as two lists of dictionaries
    headers = retrieve_headers()
    query = """
    query ($code: String!) {
      reportData {
        report(code: $code) {
          fights {
            id
            name
            startTime
            endTime
            encounterID
            kill
          }
          masterData {
            actors {
              id
              name
              subType
              type
            }
          }
        }
      }
    }
    """
    response = requests.post(API_URL,
                             json={
                                 'query': query,
                                 'variables': {
                                     'code': report_id
                                 }
                             },
                             headers=headers)
    response_data = response.json()
    if 'errors' in response_data:
        print("Errors from API:", response_data['errors'])
        return [], []

    fights = [{
        "id": fight["id"],
        "name": fight["name"],
        "start": fight["startTime"],
        "end": fight["endTime"],
        "kill": fight["kill"]
    } for fight in response_data.get("data", {}).get("reportData", {}).get(
        "report", {}).get("fights", []) if fight.get("encounterID", 0) != 0]

    players = [{
        "id": actor["id"],
        "name": actor["name"],
        "class": actor["subType"]
    } for actor in response_data.get("data", {}).get("reportData", {}).get(
        "report", {}).get("masterData", {}).get("actors", [])
               if actor.get("type") == "Player"]

    return fights, players


def extract_report_code(input_link):
    # Split the input link by '/' and get the last part
    report_code = input_link.split("/")[-1]

    # Remove any URL fragments or query parameters
    report_code = report_code.split("#")[0].split("?")[0]

    # Validate the extracted report code
    if report_code.isalnum():
        return report_code
    else:
        raise ValueError(
            "Invalid input. Please provide a valid Warcraft Logs report link or report code."
        )


def get_cast_events(
        report_id, start_time, end_time,
        player_id):  # Fetches a json containing all casts important for analysis and the overview table
    variables = {
        "code": report_id,
        "startTime": start_time,
        "endTime": end_time,
        "sourceID": player_id,
        "dataType": "Casts",
    }
    headers = retrieve_headers()
    query = """
    query ($code: String!, $startTime: Float, $endTime: Float, $sourceID: Int, $dataType: EventDataType) {
      reportData {
        report(code: $code) {
          events(dataType: $dataType, startTime: $startTime, endTime: $endTime, sourceID: $sourceID) {
            data
            nextPageTimestamp
          }
        }
      }
    }
    """

    events_batch = []

    try:
        while True:
            response = requests.post(API_URL,
                                     json={
                                         "query": query,
                                         "variables": variables
                                     },
                                     headers=headers)
            response_data = response.json()

            if "errors" in response_data:
                print("Errors from API:", response_data["errors"])
                break

            events_data = response_data["data"]["reportData"]["report"][
                "events"]
            new_events_batch = events_data["data"]

            if new_events_batch:
                events_batch.extend(new_events_batch)
            else:
                print("No more data or unexpected response format:",
                      response_data)
                break

            next_page_timestamp = events_data.get("nextPageTimestamp")
            if not next_page_timestamp:
                break
            variables[
                "startTime"] = next_page_timestamp

    except Exception as e:
        print(f"An error occurred while fetching events: {str(e)}")

    return events_batch


def get_buff_events(
        report_id, start_time, end_time,
        player_id):  # Fetches a json containing events that affect players maelstrom stacks
    variables = {
        "code": report_id,
        "startTime": start_time,
        "endTime": end_time,
        "sourceID": player_id,
        "dataType": "Buffs",
        "abilityID": 408505,
    }
    headers = retrieve_headers()
    query = """
    query ($code: String!, $startTime: Float, $endTime: Float, $sourceID: Int, $dataType: EventDataType, $abilityID: Float) {
      reportData {
        report(code: $code) {
          events(dataType: $dataType, startTime: $startTime, endTime: $endTime, sourceID: $sourceID, abilityID: $abilityID) {
            data
            nextPageTimestamp
          }
        }
      }
    }
    """
    events_batch = []

    try:
        while True:
            response = requests.post(API_URL,
                                     json={
                                         "query": query,
                                         "variables": variables
                                     },
                                     headers=headers)
            response_data = response.json()

            if "errors" in response_data:
                print("Errors from API:", response_data["errors"])
                break

            events_data = response_data["data"]["reportData"]["report"][
                "events"]
            new_events_batch = events_data["data"]

            if new_events_batch:
                events_batch.extend(new_events_batch)
            else:
                print("No more data or unexpected response format:",
                      response_data)
                break

            next_page_timestamp = events_data.get("nextPageTimestamp")
            if not next_page_timestamp:
                break
            variables[
                "startTime"] = next_page_timestamp 

    except Exception as e:
        print(f"An error occurred while fetching events: {str(e)}")

    return events_batch


def get_buff_table(report_id, start_time, end_time, player_id): #Fetches a json containing a table of buffs during a specific combat on a player
    variables = {
        'code': report_id,
        'startTime': start_time,
        'endTime': end_time,
        'sourceID': player_id,
        'dataType': 'Buffs',
    }
    headers = retrieve_headers()
    query = """
    query ($code: String!, $startTime: Float, $endTime: Float, $sourceID: Int, $dataType: TableDataType) {
      reportData {
        report(code: $code) {
          table(dataType: $dataType, startTime: $startTime, endTime: $endTime, sourceID: $sourceID)
        }
      }
    }
    """

    response = requests.post(API_URL,
                             json={
                                 'query': query,
                                 'variables': variables
                             },
                             headers=headers)
    response_data = response.json()

    if 'errors' in response_data:
        print("Errors from API:", response_data['errors'])
        return []

    return response_data['data']['reportData']['report']['table']


def get_worldbuff_presence(buff_table, relevant_buffs): #Filters the table for world buffs and major buffs
    buff_presence = {buff_id: False for buff_id in relevant_buffs}
    abilities = buff_table.get('data', {}).get('auras', [])
    for buff in abilities:
        if buff['guid'] in relevant_buffs:
            buff_presence[buff['guid']] = buff['totalUptime'] > 0
    return buff_presence


def find_most_recent_relevant_buff(timestamp, buffs):
    # Crawl backwards through buffs to find the most recent 'removebuff' or 'applybuffstack' with stack 5
    counter = -1  # Extra count removed due to counter position in loop
    for buff in reversed(buffs):
        if buff["timestamp"] > timestamp:
            continue
        counter += 1
        if buff["type"] == "removebuff":
            return False
        if buff["type"] == "applybuffstack" and buff.get("stack", 0) == 5:
            time_since_last_stack5 = timestamp - buff["timestamp"]
            return f"{time_since_last_stack5} ms - {counter} stacks wasted"
    return False  # Default to False if no relevant buffs are found


def process_events(events, buffs):
    processed_events = []
    last_when_free = 0  # Initialize last_when_free to the beginning of the fight or some logical start time

    # First, filter events to only include those in the spell_names dictionary
    whitelisted_events = [
        event for event in events if event["abilityGameID"] in spell_names
    ]

    # Now process only the filtered events
    for index, event in enumerate(whitelisted_events):
        ability_id = event["abilityGameID"]
        ability_name = spell_names[
            ability_id]  # Get the ability name from the dictionary

        if index == 0:
            # Special handling for the first event
            last_when_free = event[
                "timestamp"]  # Set last_when_free to the timestamp of the first event
            downtime = 0  # No downtime for the first event - too complicated due to prepull events
        else:
            prev_event = whitelisted_events[index - 1]
            prev_end_time = prev_event[
                "timestamp"] + 1500  # Assume 1.5 sec for the GCD

            if (prev_event["type"] == "begincast"
                    and (event["timestamp"] - prev_event["timestamp"]) < 1500
                ):  # If last event wasn't instant, check it against a GCD
                last_when_free = prev_event["timestamp"] + 1500
            else:
                last_when_free = max(prev_end_time,
                                     prev_event["timestamp"] + 1500)

            # Calculate downtime based on the last_when_free
            downtime = event["timestamp"] - last_when_free
            downtime = max(0, downtime)  # Ensure downtime doesn't go negative

        # Check if the buff is up at the time of this event
        buff_up = find_most_recent_relevant_buff(event["timestamp"], buffs)

        # Append the processed event with new fields
        processed_event = {
            **event,
            "abilityName": ability_name,
            "whenFree": last_when_free,
            "downtime": downtime,
            "buffUp": buff_up,
        }
        processed_events.append(processed_event)

    return processed_events


def get_player_dps(report_id, start_time, end_time, player_id): #Get players dps for the estimated gains parr of the UI
    variables = {
        'code': report_id,
        'startTime': start_time,
        'endTime': end_time,
        'sourceID': player_id
    }
    headers = retrieve_headers()
    query = """
    query ($code: String!, $startTime: Float, $endTime: Float, $sourceID: Int) {
      reportData {
        report(code: $code) {
          events(dataType: DamageDone, startTime: $startTime, endTime: $endTime, sourceID: $sourceID) {
            data
          }
        }
      }
    }
    """
    response = requests.post(API_URL,
                             json={
                                 'query': query,
                                 'variables': variables
                             },
                             headers=headers)
    response_data = response.json()
    if 'errors' in response_data:
        print("Errors from API:", response_data['errors'])
        return 0

    events = response_data.get('data',
                               {}).get('reportData',
                                       {}).get('report',
                                               {}).get('events',
                                                       {}).get('data', [])
    total_damage = sum(event.get('amount', 0) for event in events)
    fight_duration = end_time - start_time

    if fight_duration > 0:
        dps = total_damage / (fight_duration / 1000)
    else:
        dps = 0

    return dps


@app.route("/")
def index():
    fights, players = [], []
    if request.args.get("report_id"):
        report_id = extract_report_code(request.args.get("report_id"))
        fights, players = fetch_report_details(report_id)
    return render_template("index.html",
                           fights=fights,
                           players=players,
                           events=[])


@app.route('/events', methods=['GET'])
def events():
    report_id = extract_report_code(request.args.get('report_id'))
    fight_data = request.args.get('fightData')
    player_id = request.args.get('player_id')

    if not report_id or not fight_data or not player_id:
        return "All parameters are required.", 400

    fight_details = fight_data.split('-')
    if len(fight_details) != 3:
        return "Invalid fight data format.", 400

    fight_id, start_time, end_time = fight_details
    buffs = get_buff_events(report_id, float(start_time), float(end_time),
                            int(player_id))
    casts = get_cast_events(report_id, float(start_time), float(end_time),
                            int(player_id))
    buff_table = get_buff_table(report_id, float(start_time), float(end_time),
                                int(player_id))
    relevant_buffs = [446698, 15366, 23768, 446335]
    worldbuffs = get_worldbuff_presence(buff_table, relevant_buffs)
    events = process_events(casts, buffs)

    # Calculate total downtime
    total_downtime = sum(event['downtime'] for event in events)
    fight_duration = float(end_time) - float(
        start_time)  # Calculate fight duration
    downtime_percentage = (total_downtime / fight_duration
                           )  # Calculate downtime percentage

    # Calculate base DPS
    base_dps = get_player_dps(report_id, float(start_time), float(end_time),
                              int(player_id))

    fights, players = fetch_report_details(
        report_id)  # Optionally re-fetch to keep dropdowns populated

    return render_template('events.html',
                           events=events,
                           report_id=report_id,
                           fights=fights,
                           players=players,
                           start_time=start_time,
                           total_downtime=total_downtime,
                           downtime_percentage=downtime_percentage,
                           worldbuffs=worldbuffs,
                           base_dps=base_dps,
                           fight_duration=fight_duration)


if __name__ == "__main__":
    app.run(debug=True)
