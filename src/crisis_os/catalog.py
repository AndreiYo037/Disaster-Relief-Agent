"""Static Katrina catalog: IDs, lon/lat, routes.

Coordinates are the real 2005 sites (Wikipedia / OSM / IPET). The live basemap is
modern imagery, so bridge:B7 sits on the 2011 Twin Span alignment — labelled as such.
"""

ENTITIES_SPEC = [
    # Canonical demo IDs
    dict(entity_id="bridge:B7", type="bridge", name="I-10 Twin Span Bridge",
         lon=-89.82486, lat=30.18264, aliases=["Twin Span", "the north bridge", "I-10 bridge"]),
    dict(entity_id="route:R14", type="route", name="I-10 East (to Slidell)",
         lon=-89.8550, lat=30.1550, aliases=["I-10 east"]),
    dict(entity_id="route:R22", type="route", name="US-11 Lake Pontchartrain bridge (alt)",
         lon=-89.84306, lat=30.18722, aliases=["US-11", "the alternate route", "Maestri Bridge"]),
    dict(entity_id="zone:B", type="zone", name="Lower Ninth Ward",
         lon=-90.0130, lat=29.9740, aliases=["Lower 9", "Ninth Ward", "L9W"]),
    dict(entity_id="zone:C", type="zone", name="Ernest N. Morial Convention Center",
         lon=-90.0629, lat=29.9428, aliases=["Morial Convention Center"]),
    dict(entity_id="warehouse:W1", type="warehouse", name="Slidell I-10 staging",
         lon=-89.7704, lat=30.2753),
    dict(entity_id="truck:17", type="vehicle", name="Relief water convoy 17",
         lon=-89.7704, lat=30.2753),
    dict(entity_id="hospital:NDH", type="hospital", name="Memorial Medical Center (Baptist)",
         lon=-90.0986, lat=29.9267, aliases=["Memorial", "Baptist", "NDH", "Ochsner Baptist"]),

    dict(entity_id="bridge:us11", type="bridge", name="Maestri Bridge (US-11)",
         lon=-89.84306, lat=30.18722, aliases=["US-11"]),
    dict(entity_id="bridge:ccc", type="bridge", name="Crescent City Connection (US-90)",
         lon=-90.05750, lat=29.93861, aliases=["CCC", "GNO bridge"]),
    dict(entity_id="bridge:danziger", type="bridge", name="Danziger Bridge",
         lon=-90.0267, lat=30.0094, aliases=["Danziger"]),
    dict(entity_id="bridge:causeway", type="bridge", name="Lake Pontchartrain Causeway (south landing)",
         lon=-90.1539, lat=30.0266, aliases=["Causeway"]),
    dict(entity_id="road:i10", type="road", name="I-10 at Claiborne Avenue overpass",
         lon=-90.0755, lat=29.9642, aliases=["I-10"]),

    dict(entity_id="camp:cloverleaf", type="camp", name="I-10 / Causeway cloverleaf",
         lon=-90.1544, lat=30.0028, aliases=["cloverleaf"]),
    dict(entity_id="shelter:dome", type="shelter", name="Louisiana Superdome",
         lon=-90.08124, lat=29.95106, aliases=["Superdome", "the Dome", "Caesars Superdome"]),
    dict(entity_id="shelter:morial", type="shelter", name="Ernest N. Morial Convention Center",
         lon=-90.0629, lat=29.9428, aliases=["Convention Center"]),
    dict(entity_id="school:mcd", type="school", name="McDonogh 35 Senior High (Kerlerec St)",
         lon=-90.0685, lat=29.9717, aliases=["McDonogh 35"]),

    dict(entity_id="hospital:charity", type="hospital", name="Charity Hospital",
         lon=-90.0781, lat=29.9586, aliases=["Big Charity"]),
    dict(entity_id="hospital:university", type="hospital", name="University Hospital (MCLNO)",
         lon=-90.0817, lat=29.9578, aliases=["University Hospital"]),
    dict(entity_id="hospital:touro", type="hospital", name="Touro Infirmary",
         lon=-90.0930, lat=29.9256, aliases=["Touro"]),
    dict(entity_id="hospital:methodist", type="hospital", name="Pendleton Memorial Methodist Hospital",
         lon=-89.9748, lat=30.0165, aliases=["Methodist"]),
    dict(entity_id="hospital:chalmette", type="hospital", name="Chalmette Medical Center",
         lon=-89.9625, lat=29.9408, aliases=["Chalmette"]),
    dict(entity_id="clinic:9th", type="clinic", name="St. Claude Ave clinic (9th Ward)",
         lon=-90.0375, lat=29.9688, aliases=["clinic"]),

    dict(entity_id="infra:power", type="power", name="A.B. Paterson / Market St plant",
         lon=-90.0669, lat=29.9410, aliases=["power", "grid"]),
    dict(entity_id="power:michoud", type="power", name="Entergy Michoud Generating Station",
         lon=-89.9244, lat=30.0078, aliases=["Michoud"]),
    dict(entity_id="power:waterford", type="power", name="Waterford 3 Nuclear Station",
         lon=-90.4711, lat=29.9953, aliases=["Waterford"]),
    dict(entity_id="power:ninemile", type="power", name="Entergy Nine Mile Point",
         lon=-90.2056, lat=29.9475, aliases=["Nine Mile"]),
    dict(entity_id="infra:water", type="water", name="Carrollton Water Purification Plant",
         lon=-90.1342, lat=29.9606, aliases=["S&WB"]),
    dict(entity_id="infra:pump6", type="pump", name="S&WB Drainage Pump Station No. 6",
         lon=-90.1215, lat=30.0208),
    dict(entity_id="infra:pumpInd", type="pump", name="S&WB Drainage Pump Station No. 5",
         lon=-90.0325, lat=29.9822),

    dict(entity_id="breach:17th", type="breach", name="17th Street Canal breach (Bellaire Dr)",
         lon=-90.1217, lat=30.0170),
    dict(entity_id="breach:london", type="breach", name="London Avenue Canal south breach (Mirabeau)",
         lon=-90.0710, lat=30.0092),
    dict(entity_id="breach:london-n", type="breach", name="London Avenue Canal north breach (Warrington)",
         lon=-90.0695, lat=30.0206),
    dict(entity_id="breach:ihnc", type="breach", name="IHNC east-bank breach (Lower Ninth)",
         lon=-90.0205, lat=29.9758),
    dict(entity_id="breach:ihnc-west", type="breach", name="IHNC west-bank breach (France Rd)",
         lon=-90.0280, lat=29.9875),

    dict(entity_id="infra:port", type="port", name="Port of New Orleans (Julia St terminal)",
         lon=-90.0635, lat=29.9440),
    dict(entity_id="airport:msy", type="airport", name="Louis Armstrong New Orleans Intl",
         lon=-90.2581, lat=29.9934, aliases=["MSY"]),
    dict(entity_id="airport:lakefront", type="airport", name="New Orleans Lakefront Airport",
         lon=-90.0283, lat=30.0424),
    dict(entity_id="comms:eoc", type="comm", name="City command post — Hyatt Regency",
         lon=-90.0783, lat=29.9486, aliases=["EOC"]),
    dict(entity_id="personnel:ng", type="personnel", name="Jackson Barracks — Louisiana NG HQ",
         lon=-90.0089, lat=29.9511),
    dict(entity_id="food:pod", type="food", name="Alario Center POD",
         lon=-90.1556, lat=29.9075),
    dict(entity_id="medicine:cache", type="medicine", name="MSY airport DMAT field hospital",
         lon=-90.2560, lat=29.9885),
    dict(entity_id="fuel:depot", type="fuel", name="Murphy Oil refinery (Meraux)",
         lon=-89.9370, lat=29.9335),
    dict(entity_id="gauge:ihnc", type="gauge", name="IHNC Lock staff gauge",
         lon=-90.0274, lat=29.9647),
]

RELATIONSHIPS = [
    ("route:R14", "bridge:B7", "reachable_from"),
    ("route:R14", "zone:B", "serves"),
    ("route:R22", "zone:B", "serves"),
    ("route:R22", "bridge:us11", "reachable_from"),
    ("warehouse:W1", "zone:B", "supplies"),
    ("warehouse:W1", "zone:C", "supplies"),
    ("truck:17", "warehouse:W1", "connects"),
    ("infra:pump6", "infra:power", "depends_on"),
    ("infra:pumpInd", "infra:power", "depends_on"),
    ("infra:water", "infra:power", "depends_on"),
    ("hospital:charity", "infra:power", "depends_on"),
    ("hospital:university", "infra:power", "depends_on"),
    ("hospital:NDH", "infra:power", "depends_on"),
    ("hospital:touro", "infra:power", "depends_on"),
    ("hospital:methodist", "infra:power", "depends_on"),
    ("shelter:dome", "infra:power", "depends_on"),
    ("shelter:morial", "infra:power", "depends_on"),
    ("infra:pumpInd", "zone:B", "serves"),
    ("infra:pump6", "zone:C", "serves"),
    ("breach:ihnc", "zone:B", "floods"),
    ("breach:london", "zone:C", "floods"),
    ("breach:london-n", "zone:C", "floods"),
    ("breach:17th", "zone:C", "floods"),
    ("infra:port", "warehouse:W1", "supplies"),
    ("infra:water", "zone:B", "supplies"),
    ("infra:water", "zone:C", "supplies"),
    ("infra:power", "power:michoud", "depends_on"),
    ("infra:power", "power:waterford", "depends_on"),
    ("comms:eoc", "infra:power", "depends_on"),
    ("airport:msy", "infra:power", "depends_on"),
]

# Lower Ninth: IHNC (west) to St. Bernard line (east), river to Florida Ave.
ZONE_RINGS = {
    "zone:B": [
        [-90.0275, 29.9565], [-89.9880, 29.9540], [-89.9850, 29.9860],
        [-90.0275, 29.9845], [-90.0275, 29.9565],
    ],
    # Morial Convention Center riverfront bar
    "zone:C": [
        [-90.0735, 29.9375], [-90.0560, 29.9378], [-90.0560, 29.9475],
        [-90.0735, 29.9470], [-90.0735, 29.9375],
    ],
}

P_STAGING = [-89.7704, 30.2753]
P_B7 = [-89.82486, 30.18264]
P_US11 = [-89.84306, 30.18722]
P_ZONE_B = [-90.0130, 29.9740]

# Waypoints on I-10 (R14) and US-11 (R22), not straight-line chords across the marsh.
ROUTE_PATHS = {
    "route:R14": [
        P_STAGING, [-89.805, 30.220], [-89.805, 30.205], P_B7,
        [-89.855, 30.155], [-89.920, 30.080], [-89.980, 30.045],
        [-90.000, 30.020], [-90.012, 29.990], P_ZONE_B,
    ],
    "route:R22": [
        P_STAGING, [-89.800, 30.250], P_US11, [-89.860, 30.155],
        [-89.940, 30.070], [-89.990, 30.030], [-90.000, 30.005], P_ZONE_B,
    ],
}

BASE_STATES = {
    "bridge:B7": "uncertain", "route:R14": "operational", "route:R22": "operational",
    "bridge:us11": "operational", "bridge:ccc": "operational", "bridge:danziger": "operational",
    "bridge:causeway": "operational", "road:i10": "damaged",
    "zone:B": "uncertain", "zone:C": "uncertain", "camp:cloverleaf": "critical",
    "shelter:dome": "critical", "shelter:morial": "critical", "school:mcd": "critical",
    "hospital:charity": "inaccessible", "hospital:university": "inaccessible",
    "hospital:NDH": "operational", "hospital:touro": "damaged",
    "hospital:methodist": "inaccessible", "hospital:chalmette": "inaccessible",
    "clinic:9th": "inaccessible", "infra:power": "inaccessible",
    "power:michoud": "inaccessible", "power:waterford": "damaged", "power:ninemile": "damaged",
    "infra:water": "critical",
    "infra:pump6": "damaged", "infra:pumpInd": "inaccessible",
    "breach:17th": "critical", "breach:london": "critical", "breach:london-n": "critical",
    "breach:ihnc": "critical", "breach:ihnc-west": "critical",
    "infra:port": "damaged",
    "airport:msy": "inaccessible", "airport:lakefront": "inaccessible", "comms:eoc": "critical",
    "warehouse:W1": "full", "truck:17": "operational", "personnel:ng": "critical",
    "food:pod": "inaccessible", "medicine:cache": "inaccessible", "fuel:depot": "inaccessible",
    "gauge:ihnc": "operational",
}
