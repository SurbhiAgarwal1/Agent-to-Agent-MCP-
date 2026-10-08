"""Matching Agent for Blood Donation Matching System.

Responsible for discovering compatible blood sources (blood bank inventory and
eligible synthetic donors) for a validated blood request.

Key principles:
1. Uses medically sound RBC compatibility rules from app.services.compatibility.
2. Prioritizes exact blood-group matches first, followed by compatible alternatives.
3. Filters out exhausted blood bank stock (units_available <= 0) and unavailable donors.
4. Keeps matching algorithm decoupled from direct database access to allow pure
   in-memory evaluation and unit testing.
5. Does NOT calculate distance, route, or ETA (reserved for subsequent agents).
"""

from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.donor import Donor
from app.models.enums import MatchSourceType
from app.services.compatibility import get_compatible_donor_groups


class MatchingAgent:
    """Agent that matches a validated blood request with compatible blood sources.
    
    Searches both:
    - Blood bank inventories (pre-tested stock available at licensed facilities)
    - Synthetic voluntary donors (registered donors who are currently marked available)
    """

    def __init__(self, db: Optional[Session] = None, bus: Optional[Any] = None):
        """Initialize the Matching Agent with an optional database session and A2A message bus.
        
        Args:
            db: Optional SQLAlchemy Session for fetching records directly from the database.
            bus: Optional MessageBus instance for A2A communication.
        """
        self.db = db
        self.bus = bus

    def handle_a2a_message(self, message: Any) -> Any:
        """Handle incoming A2A message for candidate blood source discovery.
        
        Validates message envelope, discovers compatible sources, enriches coordinates,
        and forwards to LocationAgent if connected to the message bus.
        """
        from app.agents.a2a.message import A2AMessage, A2AMessageType
        from app.models.hospital import Hospital
        from app.models.blood_bank import BloodBank

        if not hasattr(message, "payload") or not isinstance(message.payload, dict):
            return message.create_error(
                sender_agent="MatchingAgent",
                error_message="Malformed message: payload must be a dictionary.",
            )

        if getattr(message, "message_type", None) != A2AMessageType.MATCHING_FIND_SOURCES_REQUEST:
            return message.create_error(
                sender_agent="MatchingAgent",
                error_message=f"Unsupported message_type '{getattr(message, 'message_type', None)}'. Expected '{A2AMessageType.MATCHING_FIND_SOURCES_REQUEST}'.",
            )

        req_data = message.payload.get("requirement", message.payload)
        if not isinstance(req_data, dict) or "blood_group" not in req_data:
            return message.create_error(
                sender_agent="MatchingAgent",
                error_message="Malformed payload: missing requirement or blood_group.",
            )

        # 1. Discover compatible sources
        matches_result = self.find_matches(
            request_data=req_data,
            inventories=message.payload.get("inventories"),
            donors=message.payload.get("donors"),
        )

        # 2. If connected to A2A bus, resolve coordinates and forward to LocationAgent
        if self.bus:
            hospital_coords = message.payload.get("hospital_coords")
            hospital_id = message.payload.get("hospital_id")

            if not hospital_coords and self.db and hospital_id:
                hosp = self.db.query(Hospital).filter(Hospital.hospital_id == hospital_id).first()
                if hosp:
                    hospital_coords = {
                        "hospital_id": hosp.hospital_id,
                        "name": hosp.name,
                        "latitude": hosp.latitude,
                        "longitude": hosp.longitude,
                        "address": hosp.address,
                    }

            enriched_candidates = []
            for m in matches_result.get("matches", []):
                item = dict(m)
                s_type = m["source_type"]
                s_id = m["source_id"]

                # If coordinates already in match dict, preserve them
                if "latitude" not in item or "longitude" not in item:
                    if self.db:
                        if s_type == MatchSourceType.BLOOD_BANK.value:
                            bank = self.db.query(BloodBank).filter(BloodBank.bank_id == s_id).first()
                            if bank:
                                item["latitude"] = bank.latitude
                                item["longitude"] = bank.longitude
                                item["name"] = bank.name
                                item["address"] = bank.address
                        else:
                            donor = self.db.query(Donor).filter(Donor.donor_id == s_id).first()
                            if donor:
                                item["latitude"] = donor.latitude
                                item["longitude"] = donor.longitude
                                item["name"] = donor.name
                                item["address"] = "Voluntary Donor (Mobile Dispatch)"

                enriched_candidates.append(item)

            loc_payload = {
                "hospital_id": hospital_id,
                "hospital_coords": hospital_coords,
                "candidates": enriched_candidates,
                "requirement": req_data,
            }
            next_msg = A2AMessage.create(
                sender_agent="MatchingAgent",
                receiver_agent="LocationAgent",
                message_type=A2AMessageType.LOCATION_CALCULATE_DISTANCES_REQUEST,
                payload=loc_payload,
                correlation_id=message.correlation_id,
            )
            return self.bus.send(next_msg)

        # Standalone response
        return message.create_response(
            sender_agent="MatchingAgent",
            message_type=A2AMessageType.MATCHING_SOURCES_FOUND_EVENT,
            payload=matches_result,
        )

    def find_matches(
        self,
        request_data: Union[Dict[str, Any], BloodRequest],
        inventories: Optional[List[Union[Dict[str, Any], BloodInventory]]] = None,
        donors: Optional[List[Union[Dict[str, Any], Donor]]] = None,
    ) -> Dict[str, Any]:
        """Find all compatible blood bank inventory and donor matches for a blood request.
        
        Args:
            request_data: Dictionary or BloodRequest instance containing:
                - request_id: int
                - blood_group: str (e.g. "O+")
            inventories: Optional list of blood inventory records (dicts or BloodInventory models).
                         If None and db is configured, fetched from database.
            donors: Optional list of donor records (dicts or Donor models).
                    If None and db is configured, fetched from database.
                    
        Returns:
            Dictionary with structure:
            {
                "request_id": 101,
                "matches": [
                    {
                        "source_type": "BLOOD_BANK",
                        "source_id": 2,
                        "blood_group": "O+",
                        "units_available": 6
                    },
                    {
                        "source_type": "DONOR",
                        "source_id": 8,
                        "blood_group": "O+",
                        "units_available": 1
                    }
                ]
            }
        """
        # 1. Extract request attributes
        request_id, recipient_group = self._extract_request_info(request_data)

        if not recipient_group:
            return {"request_id": request_id, "matches": []}

        # 2. Determine ordered compatible donor groups (exact match is always index 0)
        compatible_groups = get_compatible_donor_groups(recipient_group)
        if not compatible_groups:
            # Unknown or unsupported blood group -> no matches possible
            return {"request_id": request_id, "matches": []}

        # Lookup table for priority rank based on compatibility: exact match = 0, others = 1, 2, ...
        group_priority = {bg: rank for rank, bg in enumerate(compatible_groups)}

        # 3. Retrieve candidate inventories and donors
        candidate_inventories = self._get_inventories(inventories)
        candidate_donors = self._get_donors(donors)

        matches: List[Dict[str, Any]] = []

        # 4. Filter and process blood bank inventory candidates
        for inv in candidate_inventories:
            inv_data = self._parse_inventory(inv)
            if not inv_data:
                continue

            bg = inv_data["blood_group"]
            units = inv_data["units_available"]

            # Must be medically compatible and have units available > 0
            if bg in group_priority and units > 0:
                matches.append({
                    "source_type": MatchSourceType.BLOOD_BANK.value,
                    "source_id": inv_data["bank_id"],
                    "blood_group": bg,
                    "units_available": units,
                    "_priority_rank": group_priority[bg],
                    "_source_rank": 0,  # Prioritize institutional blood banks before individual donors
                })

        # 5. Filter and process voluntary donor candidates
        for donor in candidate_donors:
            donor_data = self._parse_donor(donor)
            if not donor_data:
                continue

            bg = donor_data["blood_group"]
            available = donor_data["available"]

            # Must be medically compatible and currently marked available
            if bg in group_priority and available:
                matches.append({
                    "source_type": MatchSourceType.DONOR.value,
                    "source_id": donor_data["donor_id"],
                    "blood_group": bg,
                    "units_available": 1,  # A single voluntary donor contributes 1 unit
                    "_priority_rank": group_priority[bg],
                    "_source_rank": 1,
                })

        # 6. Sort matches:
        # 1st: Exact blood match first (priority_rank 0), then compatible alternatives (rank 1, 2, ...)
        # 2nd: Blood bank before donor for equal compatibility rank
        # 3rd: Higher units available first for blood banks
        matches.sort(
            key=lambda m: (m["_priority_rank"], m["_source_rank"], -m["units_available"])
        )

        # 7. Strip internal ranking keys before returning
        clean_matches = [
            {
                "source_type": m["source_type"],
                "source_id": m["source_id"],
                "blood_group": m["blood_group"],
                "units_available": m["units_available"],
            }
            for m in matches
        ]

        return {
            "request_id": request_id,
            "matches": clean_matches,
        }

    # -------------------------------------------------------------------------
    # Helper & Extraction Methods
    # -------------------------------------------------------------------------

    def _extract_request_info(
        self, request_data: Union[Dict[str, Any], BloodRequest]
    ) -> tuple[Optional[int], Optional[str]]:
        """Extract request_id and normalized blood_group from dict or BloodRequest."""
        if isinstance(request_data, dict):
            req_id = request_data.get("request_id")
            raw_bg = request_data.get("blood_group")
        elif isinstance(request_data, BloodRequest):
            req_id = request_data.request_id
            raw_bg = request_data.blood_group
        else:
            return None, None

        clean_bg = raw_bg.strip().upper() if isinstance(raw_bg, str) else None
        return req_id, clean_bg

    def _get_inventories(
        self, inventories: Optional[List[Union[Dict[str, Any], BloodInventory]]]
    ) -> List[Any]:
        """Fetch inventory list from passed argument or database."""
        if inventories is not None:
            return inventories
        if self.db is not None:
            return (
                self.db.query(BloodInventory)
                .filter(BloodInventory.units_available > 0)
                .all()
            )
        return []

    def _get_donors(
        self, donors: Optional[List[Union[Dict[str, Any], Donor]]]
    ) -> List[Any]:
        """Fetch donor list from passed argument or database."""
        if donors is not None:
            return donors
        if self.db is not None:
            return self.db.query(Donor).filter(Donor.available.is_(True)).all()
        return []

    def _parse_inventory(
        self, item: Union[Dict[str, Any], BloodInventory]
    ) -> Optional[Dict[str, Any]]:
        """Normalize inventory data from dict or SQLAlchemy model."""
        if isinstance(item, dict):
            bank_id = item.get("bank_id") or item.get("source_id")
            bg = item.get("blood_group")
            units = item.get("units_available", 0)
        elif isinstance(item, BloodInventory):
            bank_id = item.bank_id
            bg = item.blood_group
            units = item.units_available
        else:
            return None

        if bank_id is None or not bg:
            return None

        return {
            "bank_id": bank_id,
            "blood_group": bg.strip().upper(),
            "units_available": int(units) if units is not None else 0,
        }

    def _parse_donor(
        self, item: Union[Dict[str, Any], Donor]
    ) -> Optional[Dict[str, Any]]:
        """Normalize donor data from dict or SQLAlchemy model."""
        if isinstance(item, dict):
            donor_id = item.get("donor_id") or item.get("source_id")
            bg = item.get("blood_group")
            available = item.get("available", True)
        elif isinstance(item, Donor):
            donor_id = item.donor_id
            bg = item.blood_group
            available = item.available
        else:
            return None

        if donor_id is None or not bg:
            return None

        return {
            "donor_id": donor_id,
            "blood_group": bg.strip().upper(),
            "available": bool(available),
        }
