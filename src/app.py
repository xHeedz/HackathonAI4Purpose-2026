from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Tuple
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from datetime import datetime, timezone
import mimetypes
import csv
import io
import os
import json
import urllib.request
import urllib.error

app = FastAPI(title="Emergency Dispatch Coordinator")
BASE_DIR = Path(__file__).resolve().parent

mimetypes.add_type("text/html", ".html")

# Serve static dashboard
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ----------------------------
# In-memory "database"
# ----------------------------
INCIDENTS: Dict[str, dict] = {}
RESOURCES: Dict[str, dict] = {}
DISPATCH_EVENTS: List[dict] = []

# Station registry (replace with your DB later)
STATIONS: List[dict] = [
    {
        "stationId": "AUBMC",
        "name": "American University of Beirut Medical Center",
        "latitude": 33.8978065,
        "longitude": 35.4858978,
        "phone": "+961 1 350000",
        "email": "info@aub.edu.lb",
        "region": "Beirut",
        "stationType": "HOSPITAL",
    },
    {
        "stationId": "RIZK",
        "name": "LAU Medical Center-Rizk Hospital",
        "latitude": 33.885264,
        "longitude": 35.515033,
        "phone": "+961 1 200800",
        "email": "rizk_hospital@aist.edu.lb",
        "region": "Beirut",
        "stationType": "HOSPITAL",
    },
    {
        "stationId": "HDF",
        "name": "Hotel-Dieu de France",
        "latitude": 33.8815681,
        "longitude": 35.5189752,
        "phone": "+961 1 615300",
        "email": "hdfr@hdfr.edu.lb",
        "region": "Beirut",
        "stationType": "HOSPITAL",
    },
    {
        "stationId": "SGUMC",
        "name": "Saint George Hospital University Medical Center",
        "latitude": 33.8937793,
        "longitude": 35.5236590,
        "phone": "+961 1 441000",
        "email": "info@sgumc.org.lb",
        "region": "Beirut",
        "stationType": "HOSPITAL",
    },
    {
        "stationId": "BATROUN",
        "name": "Dr Emile Joachim Bitar Hospital - Batroun",
        "latitude": 34.2512896,
        "longitude": 35.6660919,
        "phone": "+961 6 640071",
        "email": "info@batrounhospital.org.lb",
        "region": "North",
        "stationType": "HOSPITAL",
    },
    {
        "stationId": "SAIDA",
        "name": "Sidon Governmental Hospital",
        "latitude": 33.545985,
        "longitude": 35.3818494,
        "phone": "+961 7 723007",
        "email": "info@saidahospital.org.lb",
        "region": "South",
        "stationType": "HOSPITAL",
    },
    {
        "stationId": "BEI_FIRE",
        "name": "Beirut Central Fire Station",
        "latitude": 33.892731,
        "longitude": 35.505341,
        "phone": "+961 1 444 000",
        "email": "",
        "region": "Beirut",
        "stationType": "FIRE",
    },
    {
        "stationId": "TRI_FIRE",
        "name": "Tripoli Fire Department",
        "latitude": 34.435106,
        "longitude": 35.834196,
        "phone": "+961 6 411 555",
        "email": "",
        "region": "North",
        "stationType": "FIRE",
    },
    {
        "stationId": "SAI_FIRE",
        "name": "Saida Fire Department",
        "latitude": 33.560735,
        "longitude": 35.375556,
        "phone": "+961 7 723 000",
        "email": "",
        "region": "South",
        "stationType": "FIRE",
    },
]

# ----------------------------
# Helpers
# ----------------------------

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance on Earth in kilometers."""
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def severity_to_initial_needs(event_type: str, severity: float) -> Tuple[int, int, int]:
    """Simple, readable policy: severity -> radiusKm, ambulances, fire trucks."""
    s = clamp(severity, 0, 100)

    if s < 40:
        radius = 5
    elif s < 65:
        radius = 10
    elif s < 85:
        radius = 15
    else:
        radius = 25

    et = event_type.upper()

    if et == "FIRE":
        amb = 1 if s < 40 else 2 if s < 65 else 5 if s < 85 else 10
        fire = 1 if s < 40 else 3 if s < 65 else 6 if s < 85 else 10
    elif et == "BOMBING":
        amb = 3 if s < 40 else 6 if s < 65 else 10 if s < 85 else 14
        fire = 0 if s < 40 else 2 if s < 65 else 4 if s < 85 else 6
    else:
        amb = int(round(clamp(1 + s / 20, 0, 12)))
        fire = int(round(clamp(s / 15, 0, 10)))

    return radius, amb, fire


def estimate_eta_minutes(distance_km: float, resource_type: str) -> int:
    """Rough ETA using average speeds by resource type."""
    # Simple defaults; tweak as needed for your city
    speed_kmh = 60 if resource_type == "AMBULANCE" else 50
    if speed_kmh <= 0:
        return 0
    return int(round((distance_km / speed_kmh) * 60))


def fetch_route_ors(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        raise HTTPException(500, "ORS_API_KEY not set")

    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    payload = {
        "coordinates": [[from_lon, from_lat], [to_lon, to_lat]],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"ORS error: {e.code}")
    except urllib.error.URLError:
        raise HTTPException(502, "ORS unavailable")

    route = json.loads(body)
    if not route.get("features"):
        raise HTTPException(502, "ORS empty route")

    geom = route["features"][0]["geometry"]["coordinates"]
    summary = route["features"][0]["properties"]["summary"]
    # Convert [lon, lat] -> [lat, lon]
    coords = [[c[1], c[0]] for c in geom]
    return {
        "coordinates": coords,
        "distanceKm": round(summary.get("distance", 0) / 1000, 2),
        "durationMin": round(summary.get("duration", 0) / 60, 1),
    }


def stations_within_radius(incident: dict, radius_km: float) -> List[dict]:
    nearby = []
    for s in STATIONS:
        d = haversine_km(
            incident["latitude"], incident["longitude"], s["latitude"], s["longitude"]
        )
        if d <= radius_km:
            nearby.append(
                {
                    "stationId": s["stationId"],
                    "name": s["name"],
                    "phone": s["phone"],
                    "email": s["email"],
                    "region": s["region"],
                    "stationType": s.get("stationType"),
                    "distanceKm": round(d, 2),
                    "etaMinutes": estimate_eta_minutes(d, "AMBULANCE"),
                }
            )
    nearby.sort(key=lambda x: x["distanceKm"])
    return nearby


def closest_station_by_type(incident: dict, station_type: str) -> Optional[dict]:
    candidates = [s for s in STATIONS if s.get("stationType") == station_type]
    if not candidates:
        return None
    ranked = []
    for s in candidates:
        d = haversine_km(
            incident["latitude"], incident["longitude"], s["latitude"], s["longitude"]
        )
        ranked.append((d, s))
    ranked.sort(key=lambda x: x[0])
    d, s = ranked[0]
    return {
        "stationId": s["stationId"],
        "name": s["name"],
        "phone": s["phone"],
        "email": s["email"],
        "region": s["region"],
        "stationType": s.get("stationType"),
        "distanceKm": round(d, 2),
        "etaMinutes": estimate_eta_minutes(d, "AMBULANCE"),
    }


def stations_for_notification(incident: dict, radius_km: float) -> List[dict]:
    # Prefer all stations within radius; if none for a type, fall back to closest.
    nearby = stations_within_radius(incident, radius_km)
    result = list(nearby)

    for station_type in ("HOSPITAL", "FIRE"):
        has_type = any(s.get("stationType") == station_type for s in nearby)
        if not has_type:
            fallback = closest_station_by_type(incident, station_type)
            if fallback:
                fallback["fallback"] = True
                result.append(fallback)

    # Keep closest first
    result.sort(key=lambda x: x["distanceKm"])
    return result


def closest_station(incident: dict, station_type: str) -> Optional[dict]:
    candidates = [s for s in STATIONS if s.get("stationType") == station_type]
    if not candidates:
        return None
    ranked = []
    for s in candidates:
        d = haversine_km(
            incident["latitude"], incident["longitude"], s["latitude"], s["longitude"]
        )
        ranked.append((d, s))
    ranked.sort(key=lambda x: x[0])
    d, s = ranked[0]
    return {
        "stationId": s["stationId"],
        "name": s["name"],
        "phone": s["phone"],
        "email": s["email"],
        "region": s["region"],
        "stationType": s.get("stationType"),
        "distanceKm": round(d, 2),
        "etaMinutes": estimate_eta_minutes(d, "AMBULANCE"),
    }


def ensure_chiefs(incident: dict) -> None:
    if incident.get("chiefHospital") is None:
        incident["chiefHospital"] = closest_station(incident, "HOSPITAL")
    if incident.get("chiefFireStation") is None:
        incident["chiefFireStation"] = closest_station(incident, "FIRE")


def group_incidents_by_type_and_distance(distance_km: float) -> List[dict]:
    """Greedy clustering by eventType + distance threshold."""
    groups = []
    used = set()
    incidents = list(INCIDENTS.values())

    for i, inc in enumerate(incidents):
        if inc["incidentId"] in used:
            continue

        group = {
            "eventType": inc["eventType"],
            "incidentIds": [inc["incidentId"]],
            "center": {"latitude": inc["latitude"], "longitude": inc["longitude"]},
        }
        used.add(inc["incidentId"])

        # grow group with same type and within distance of group center
        changed = True
        while changed:
            changed = False
            for other in incidents:
                if other["incidentId"] in used:
                    continue
                if other["eventType"] != group["eventType"]:
                    continue
                d = haversine_km(
                    group["center"]["latitude"],
                    group["center"]["longitude"],
                    other["latitude"],
                    other["longitude"],
                )
                if d <= distance_km:
                    group["incidentIds"].append(other["incidentId"])
                    used.add(other["incidentId"])
                    # recompute center as average for stability
                    lats = [INCIDENTS[x]["latitude"] for x in group["incidentIds"]]
                    lons = [INCIDENTS[x]["longitude"] for x in group["incidentIds"]]
                    group["center"]["latitude"] = sum(lats) / len(lats)
                    group["center"]["longitude"] = sum(lons) / len(lons)
                    changed = True

        groups.append(group)

    return groups


def fill_missing_incident_fields(row: dict, index: int) -> dict:
    """Fill missing fields with safe defaults (no AI, just simple rules)."""
    incident_id = (row.get("incidentId") or "").strip() or f"AUTO_{index}"
    event_type = (row.get("eventType") or "OTHER").strip().upper()
    severity_raw = (row.get("severity") or "").strip()
    severity = float(severity_raw) if severity_raw else 50.0

    lat_raw = (row.get("latitude") or row.get("lat") or "").strip()
    lon_raw = (row.get("longitude") or row.get("lon") or "").strip()
    latitude = float(lat_raw) if lat_raw else None
    longitude = float(lon_raw) if lon_raw else None

    return {
        "incidentId": incident_id,
        "eventType": event_type,
        "latitude": latitude,
        "longitude": longitude,
        "severity": severity,
    }


# ----------------------------
# Schemas
# ----------------------------

class CreateIncidentReq(BaseModel):
    incidentId: str
    eventType: str
    latitude: float = Field(..., alias="lat")
    longitude: float = Field(..., alias="lon")
    severity: float

    class Config:
        allow_population_by_field_name = True
        allow_population_by_alias = True


class UpdateNeedsReq(BaseModel):
    needAmbulances: int
    needFireTrucks: int


class AddResourceReq(BaseModel):
    resourceId: str
    stationId: str
    type: str  # FIRE_TRUCK or AMBULANCE
    latitude: float = Field(..., alias="lat")
    longitude: float = Field(..., alias="lon")

    class Config:
        allow_population_by_field_name = True
        allow_population_by_alias = True


class BulkAddResourcesReq(BaseModel):
    stationId: str
    type: str  # FIRE_TRUCK or AMBULANCE
    count: int
    latitude: float = Field(..., alias="lat")
    longitude: float = Field(..., alias="lon")

    class Config:
        allow_population_by_field_name = True
        allow_population_by_alias = True


class DispatchReq(BaseModel):
    maxAmbulances: Optional[int] = None
    maxFireTrucks: Optional[int] = None


class DispatchFromStationReq(BaseModel):
    stationId: str
    ambulances: int = 0
    fireTrucks: int = 0


# ----------------------------
# Endpoints
# ----------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    html_path = BASE_DIR / "static" / "dashboard.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/incidents/create")
def create_incident(req: CreateIncidentReq):
    if req.incidentId in INCIDENTS:
        raise HTTPException(400, "Incident already exists")

    radius, need_amb, need_fire = severity_to_initial_needs(req.eventType, req.severity)

    INCIDENTS[req.incidentId] = {
        "incidentId": req.incidentId,
        "eventType": req.eventType.upper(),
        "latitude": req.latitude,
        "longitude": req.longitude,
        "severity": req.severity,
        "radiusKm": radius,
        "needAmbulances": need_amb,
        "needFireTrucks": need_fire,
        "assignedAmbulancesByStation": {},
        "assignedFireTrucksByStation": {},
        "chiefHospital": None,
        "chiefFireStation": None,
    }

    inc_ref = INCIDENTS[req.incidentId]
    inc_ref["chiefHospital"] = closest_station(inc_ref, "HOSPITAL")
    inc_ref["chiefFireStation"] = closest_station(inc_ref, "FIRE")

    return {"ok": True, "incident": INCIDENTS[req.incidentId]}


@app.get("/incidents")
def list_incidents():
    for inc in INCIDENTS.values():
        ensure_chiefs(inc)
    return list(INCIDENTS.values())


@app.get("/incidents/groups")
def list_incident_groups(distanceKm: float = 1.0):
    return group_incidents_by_type_and_distance(distanceKm)


@app.get("/stations")
def list_stations():
    return STATIONS


@app.get("/incidents/{incident_id}/notifications")
def list_notifications(incident_id: str):
    inc = INCIDENTS.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    return stations_for_notification(inc, inc["radiusKm"])


@app.get("/dispatch/events")
def list_dispatch_events():
    return DISPATCH_EVENTS


@app.get("/route")
def get_route(fromLat: float, fromLon: float, toLat: float, toLon: float):
    return fetch_route_ors(fromLat, fromLon, toLat, toLon)


@app.post("/incidents/uploadCsv")
async def upload_incidents_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 encoded CSV")

    reader = csv.DictReader(io.StringIO(text))
    created = []
    skipped = []

    for idx, row in enumerate(reader, start=1):
        filled = fill_missing_incident_fields(row, idx)

        if filled["latitude"] is None or filled["longitude"] is None:
            skipped.append({"row": idx, "reason": "Missing latitude/longitude"})
            continue

        if filled["incidentId"] in INCIDENTS:
            skipped.append({"row": idx, "reason": "Duplicate incidentId"})
            continue

        radius, need_amb, need_fire = severity_to_initial_needs(
            filled["eventType"], filled["severity"]
        )

        INCIDENTS[filled["incidentId"]] = {
            "incidentId": filled["incidentId"],
            "eventType": filled["eventType"],
            "latitude": filled["latitude"],
            "longitude": filled["longitude"],
            "severity": filled["severity"],
            "radiusKm": radius,
            "needAmbulances": need_amb,
            "needFireTrucks": need_fire,
            "assignedAmbulancesByStation": {},
            "assignedFireTrucksByStation": {},
            "chiefHospital": None,
            "chiefFireStation": None,
        }
        ensure_chiefs(INCIDENTS[filled["incidentId"]])
        created.append(INCIDENTS[filled["incidentId"]])

    return {"ok": True, "created": created, "skipped": skipped, "count": len(created)}


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    inc = INCIDENTS.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    ensure_chiefs(inc)
    return inc


@app.post("/incidents/{incident_id}/updateNeeds")
def update_needs_overwrite(incident_id: str, req: UpdateNeedsReq):
    inc = INCIDENTS.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")

    inc["needAmbulances"] = max(0, req.needAmbulances)
    inc["needFireTrucks"] = max(0, req.needFireTrucks)
    inc["chiefHospital"] = closest_station(inc, "HOSPITAL")
    inc["chiefFireStation"] = closest_station(inc, "FIRE")

    return {"ok": True, "incident": inc}


@app.post("/resources/add")
def add_resource(req: AddResourceReq):
    if req.resourceId in RESOURCES:
        raise HTTPException(400, "Resource already exists")

    RESOURCES[req.resourceId] = {
        "resourceId": req.resourceId,
        "stationId": req.stationId,
        "type": req.type.upper(),
        "status": "AVAILABLE",
        "latitude": req.latitude,
        "longitude": req.longitude,
        "assignedIncidentId": None,
    }

    return {"ok": True, "resource": RESOURCES[req.resourceId]}


@app.post("/resources/bulkAdd")
def bulk_add_resources(req: BulkAddResourcesReq):
    if req.count <= 0:
        raise HTTPException(400, "count must be > 0")

    created = []
    type_upper = req.type.upper()
    # Generate predictable IDs: ST01-AMB-1, ST01-AMB-2, ...
    for i in range(1, req.count + 1):
        rid = f"{req.stationId}-{type_upper[:3]}-{i}"
        # Avoid collisions by bumping suffix
        suffix = i
        while rid in RESOURCES:
            suffix += 1
            rid = f"{req.stationId}-{type_upper[:3]}-{suffix}"

        RESOURCES[rid] = {
            "resourceId": rid,
            "stationId": req.stationId,
            "type": type_upper,
            "status": "AVAILABLE",
            "latitude": req.latitude,
            "longitude": req.longitude,
            "assignedIncidentId": None,
        }
        created.append(RESOURCES[rid])

    return {"ok": True, "created": created, "count": len(created)}


@app.get("/resources")
def list_resources(status: Optional[str] = None, incidentId: Optional[str] = None):
    resources = list(RESOURCES.values())
    if status:
        resources = [r for r in resources if r["status"] == status.upper()]
    if incidentId:
        resources = [r for r in resources if r.get("assignedIncidentId") == incidentId]
    return resources


@app.post("/incidents/{incident_id}/dispatchFromStation")
def dispatch_from_station(incident_id: str, req: DispatchFromStationReq):
    inc = INCIDENTS.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")

    station = next((s for s in STATIONS if s["stationId"] == req.stationId), None)
    if not station:
        raise HTTPException(404, "Station not found")

    send_amb = max(0, req.ambulances)
    send_fire = max(0, req.fireTrucks)

    d = haversine_km(inc["latitude"], inc["longitude"], station["latitude"], station["longitude"])
    dispatched_at = datetime.now(timezone.utc).isoformat()

    for i in range(1, send_amb + 1):
        rid = f"{req.stationId}-AMB-{dispatched_at}-{i}"
        inc["assignedAmbulancesByStation"].setdefault(req.stationId, []).append(rid)

    for i in range(1, send_fire + 1):
        rid = f"{req.stationId}-FIRE-{dispatched_at}-{i}"
        inc["assignedFireTrucksByStation"].setdefault(req.stationId, []).append(rid)

    if send_amb > 0:
        DISPATCH_EVENTS.append(
            {
                "resourceId": f"{req.stationId}-AMB-{dispatched_at}",
                "stationId": req.stationId,
                "incidentId": incident_id,
                "type": "AMBULANCE",
                "units": send_amb,
                "dispatchedAt": dispatched_at,
                "distanceKm": round(d, 2),
                "etaMinutes": estimate_eta_minutes(d, "AMBULANCE"),
            }
        )

    if send_fire > 0:
        DISPATCH_EVENTS.append(
            {
                "resourceId": f"{req.stationId}-FIRE-{dispatched_at}",
                "stationId": req.stationId,
                "incidentId": incident_id,
                "type": "FIRE_TRUCK",
                "units": send_fire,
                "dispatchedAt": dispatched_at,
                "distanceKm": round(d, 2),
                "etaMinutes": estimate_eta_minutes(d, "FIRE_TRUCK"),
            }
        )

    inc["needAmbulances"] = max(0, inc["needAmbulances"] - send_amb)
    inc["needFireTrucks"] = max(0, inc["needFireTrucks"] - send_fire)

    return {
        "ok": True,
        "sentAmbulances": send_amb,
        "sentFireTrucks": send_fire,
        "remainingNeedAmbulances": inc["needAmbulances"],
        "remainingNeedFireTrucks": inc["needFireTrucks"],
        "incident": inc,
    }


@app.post("/incidents/{incident_id}/dispatch")
def dispatch_resources(incident_id: str, req: DispatchReq = DispatchReq()):
    inc = INCIDENTS.get(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")

    def resources_within_radius(resource_type: str) -> List[dict]:
        available = [
            r for r in RESOURCES.values()
            if r["type"] == resource_type and r["status"] == "AVAILABLE"
        ]
        # filter by radius
        within = []
        for r in available:
            d = haversine_km(inc["latitude"], inc["longitude"], r["latitude"], r["longitude"])
            if d <= inc["radiusKm"]:
                within.append((d, r))
        within.sort(key=lambda x: x[0])
        return [r for _, r in within]

    def pick_resources(resource_type: str, needed: int) -> Tuple[List[dict], bool]:
        """Pick closest resources. If none within radius, fall back to global closest."""
        within = resources_within_radius(resource_type)
        if within:
            return within[:needed], True

        available = [
            r for r in RESOURCES.values()
            if r["type"] == resource_type and r["status"] == "AVAILABLE"
        ]
        ranked = []
        for r in available:
            d = haversine_km(inc["latitude"], inc["longitude"], r["latitude"], r["longitude"])
            ranked.append((d, r))
        ranked.sort(key=lambda x: x[0])
        return [r for _, r in ranked[:needed]], False

    remaining_amb = inc["needAmbulances"]
    remaining_fire = inc["needFireTrucks"]

    if req.maxAmbulances is not None:
        remaining_amb = min(remaining_amb, max(0, req.maxAmbulances))
    if req.maxFireTrucks is not None:
        remaining_fire = min(remaining_fire, max(0, req.maxFireTrucks))

    within_amb = resources_within_radius("AMBULANCE")
    within_fire = resources_within_radius("FIRE_TRUCK")
    picked_amb, used_radius_amb = pick_resources("AMBULANCE", remaining_amb)
    picked_fire, used_radius_fire = pick_resources("FIRE_TRUCK", remaining_fire)

    # lock and assign
    for r in picked_amb:
        d = haversine_km(inc["latitude"], inc["longitude"], r["latitude"], r["longitude"])
        r["status"] = "DISPATCHED"
        r["assignedIncidentId"] = incident_id
        r["dispatchedAt"] = datetime.now(timezone.utc).isoformat()
        r["distanceKmToIncident"] = round(d, 2)
        r["etaMinutes"] = estimate_eta_minutes(d, r["type"])
        inc["assignedAmbulancesByStation"].setdefault(r["stationId"], []).append(r["resourceId"])
        DISPATCH_EVENTS.append(
            {
                "resourceId": r["resourceId"],
                "stationId": r["stationId"],
                "incidentId": incident_id,
                "type": r["type"],
                "units": 1,
                "dispatchedAt": r["dispatchedAt"],
                "distanceKm": r["distanceKmToIncident"],
                "etaMinutes": r["etaMinutes"],
            }
        )

    for r in picked_fire:
        d = haversine_km(inc["latitude"], inc["longitude"], r["latitude"], r["longitude"])
        r["status"] = "DISPATCHED"
        r["assignedIncidentId"] = incident_id
        r["dispatchedAt"] = datetime.now(timezone.utc).isoformat()
        r["distanceKmToIncident"] = round(d, 2)
        r["etaMinutes"] = estimate_eta_minutes(d, r["type"])
        inc["assignedFireTrucksByStation"].setdefault(r["stationId"], []).append(r["resourceId"])
        DISPATCH_EVENTS.append(
            {
                "resourceId": r["resourceId"],
                "stationId": r["stationId"],
                "incidentId": incident_id,
                "type": r["type"],
                "units": 1,
                "dispatchedAt": r["dispatchedAt"],
                "distanceKm": r["distanceKmToIncident"],
                "etaMinutes": r["etaMinutes"],
            }
        )

    inc["needAmbulances"] = max(0, inc["needAmbulances"] - len(picked_amb))
    inc["needFireTrucks"] = max(0, inc["needFireTrucks"] - len(picked_fire))

    return {
        "ok": True,
        "sentAmbulances": [r["resourceId"] for r in picked_amb],
        "sentFireTrucks": [r["resourceId"] for r in picked_fire],
        "remainingNeedAmbulances": inc["needAmbulances"],
        "remainingNeedFireTrucks": inc["needFireTrucks"],
        "availableAmbulancesWithinRadius": len(within_amb),
        "availableFireTrucksWithinRadius": len(within_fire),
        "availableAmbulancesTotal": len([r for r in RESOURCES.values() if r["type"] == "AMBULANCE" and r["status"] == "AVAILABLE"]),
        "availableFireTrucksTotal": len([r for r in RESOURCES.values() if r["type"] == "FIRE_TRUCK" and r["status"] == "AVAILABLE"]),
        "usedRadiusForAmbulances": used_radius_amb,
        "usedRadiusForFireTrucks": used_radius_fire,
        "incident": inc,
    }
