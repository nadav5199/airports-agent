"""
Shared definition of the airport "demo set" used by every ingestion script.

Scope (per docs/contracts.md and CLAUDE.md):
  - ALL New England airports with scheduled commercial service (CT/ME/MA/NH/RI/VT),
    pulled dynamically from OurAirports at ingestion time (see fetch_ourairports.py).
  - The exam's named example airports: LAX, SNA, ANC, SFO.
  - A spread of ~35 other major US airports (FAA OEP-35-style set) so that
    percentile-rank comparisons in the scoring engine are meaningful outside
    New England too.

The New England list itself is NOT hardcoded here -- it's discovered live from
OurAirports by fetch_ourairports.py (filtered on iso_region + scheduled_service).
This module only hardcodes the "other major airports" we deliberately add on top,
plus the US-state -> region label mapping used for the `region` column in
airports.csv.
"""

# Named example airports from the exam prompt (CLAUDE.md "Example Queries"),
# plus a representative spread of other major US airports (FAA OEP-35-style)
# so percentile-rank comparisons are meaningful beyond New England.
MAJOR_AIRPORTS = [
    # Exam-named examples
    "LAX", "SNA", "ANC", "SFO",
    # Other major US airports (OEP-35-ish superset)
    "JFK", "EWR", "LGA", "ORD", "MDW", "ATL", "DFW", "DEN", "SEA",
    "MIA", "PHX", "IAH", "MCO", "LAS", "MSP", "DTW", "PHL", "BWI",
    "SLC", "SAN", "TPA", "PDX", "STL", "CLT", "IAD", "DCA", "HNL",
    "FLL", "BNA", "AUS", "RDU", "MSY", "SMF", "OAK",
]

NEW_ENGLAND_STATES = {"CT", "ME", "MA", "NH", "RI", "VT"}

# US state (2-letter) -> broad region label used for regional filtering queries
# (e.g. "New England", "West Coast").
STATE_TO_REGION = {
    "CT": "New England", "ME": "New England", "MA": "New England",
    "NH": "New England", "RI": "New England", "VT": "New England",
    "NY": "Mid-Atlantic", "NJ": "Mid-Atlantic", "PA": "Mid-Atlantic",
    "DE": "Mid-Atlantic", "MD": "Mid-Atlantic", "DC": "Mid-Atlantic",
    "VA": "Southeast", "NC": "Southeast", "SC": "Southeast", "GA": "Southeast",
    "FL": "Southeast", "AL": "Southeast", "MS": "Southeast", "TN": "Southeast",
    "KY": "Southeast", "WV": "Southeast", "LA": "South Central",
    "OH": "Midwest", "IN": "Midwest", "IL": "Midwest", "MI": "Midwest",
    "WI": "Midwest", "MN": "Midwest", "IA": "Midwest", "MO": "Midwest",
    "ND": "Midwest", "SD": "Midwest", "NE": "Midwest", "KS": "Midwest",
    "TX": "South Central", "OK": "South Central", "AR": "South Central",
    "MT": "Mountain", "ID": "Mountain", "WY": "Mountain", "CO": "Mountain",
    "UT": "Mountain", "NV": "Mountain", "AZ": "Mountain", "NM": "Mountain",
    "CA": "West Coast", "OR": "West Coast", "WA": "West Coast",
    "AK": "Alaska", "HI": "Hawaii",
}


def region_for_state(state: str) -> str:
    return STATE_TO_REGION.get(state, "Other")
