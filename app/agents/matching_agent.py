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

from datetime import date
from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from app.models.blood_inventory import BloodInventory
from app.models.blood_request import BloodRequest
from app.models.donor import Donor
from app.models.enums import MatchSourceType, MatchStatus
from app.models.match import Match
from app.services.compatibility import get_compatible_donor_groups
from app.services.eligibility import get_donor_min_gap_days, is_donor_eligible, is_stock_usable


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
        
        Validates the message envelope, discovers compatible sources and replies to the sender.
        """
        from app.agents.a2a.message import A2AMessageType

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

        matches_result = self.find_matches(
            request_data=req_data,
            inventories=message.payload.get("inventories"),
            donors=message.payload.get("donors"),
        )

        # Reply to whoever asked (the Coordinator); agents never forward to each other
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
        today: Optional[date] = None,
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
        today = today or date.today()
        min_gap = get_donor_min_gap_days()
        excluded = {
            "expired_inventory_batches": 0,
            "donors_in_cooldown": 0,
            "units_held_for_other_requests": 0,
            "donors_held_for_other_requests": 0,
            "sources_rejected_for_request": 0,
        }

        # 1. Extract request attributes
        request_id, recipient_group = self._extract_request_info(request_data)

        if not recipient_group:
            return {"request_id": request_id, "matches": [], "excluded": excluded}

        # 2. Determine ordered compatible donor groups (exact match is always index 0)
        compatible_groups = get_compatible_donor_groups(recipient_group)
        if not compatible_groups:
            # Unknown or unsupported blood group -> no matches possible
            return {"request_id": request_id, "matches": [], "excluded": excluded}

        # Lookup table for priority rank based on compatibility: exact match = 0, others = 1, 2, ...
        group_priority = {bg: rank for rank, bg in enumerate(compatible_groups)}

        # 3. Retrieve candidate inventories and donors
        candidate_inventories = self._get_inventories(inventories)
        candidate_donors = self._get_donors(donors)

        # Units/donors reserved by other requests (database-backed lookups only)
        bank_held, donor_held, rejected = self._load_reservations(request_id)
        use_bank_holds = inventories is None
        use_donor_holds = donors is None

        matches: List[Dict[str, Any]] = []
        bank_index: Dict[Any, Dict[str, Any]] = {}

        # 4. Filter and process blood bank inventory candidates
        for inv in candidate_inventories:
            inv_data = self._parse_inventory(inv)
            if not inv_data:
                continue

            bg = inv_data["blood_group"]
            units = inv_data["units_available"]

            # Must be medically compatible and have units available > 0
            if bg in group_priority and units > 0:
                if not is_stock_usable(inv_data["expiry_date"], today=today):
                    excluded["expired_inventory_batches"] += 1
                    continue
                if (MatchSourceType.BLOOD_BANK.value, inv_data["bank_id"]) in rejected:
                    excluded["sources_rejected_for_request"] += 1
                    continue
                if use_bank_holds:
                    key = (inv_data["bank_id"], bg)
                    reserved = min(bank_held.get(key, 0), units)
                    if reserved:
                        bank_held[key] -= reserved
                        units -= reserved
                        excluded["units_held_for_other_requests"] += reserved
                        if units <= 0:
                            continue
                # Merge several batches of the same group at one bank into a single source
                existing = bank_index.get((inv_data["bank_id"], bg))
                if existing is not None:
                    existing["units_available"] += units
                    continue
                entry = {
                    "source_type": MatchSourceType.BLOOD_BANK.value,
                    "source_id": inv_data["bank_id"],
                    "blood_group": bg,
                    "units_available": units,
                    "_priority_rank": group_priority[bg],
                    "_source_rank": 0,  # Prioritize institutional blood banks before individual donors
                }
                bank_index[(inv_data["bank_id"], bg)] = entry
                matches.append(entry)

        # 5. Filter and process voluntary donor candidates
        for donor in candidate_donors:
            donor_data = self._parse_donor(donor)
            if not donor_data:
                continue

            bg = donor_data["blood_group"]
            available = donor_data["available"]

            # Must be medically compatible and currently marked available
            if bg in group_priority and available:
                if not is_donor_eligible(donor_data["last_donation_date"], today=today, min_gap_days=min_gap):
                    excluded["donors_in_cooldown"] += 1
                    continue
                if (MatchSourceType.DONOR.value, donor_data["donor_id"]) in rejected:
                    excluded["sources_rejected_for_request"] += 1
                    continue
                if use_donor_holds and donor_data["donor_id"] in donor_held:
                    excluded["donors_held_for_other_requests"] += 1
                    continue
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
            "excluded": excluded,
        }

    # -------------------------------------------------------------------------
    # Helper & Extraction Methods
    # -------------------------------------------------------------------------

    def _load_reservations(self, request_id: Optional[int]):
        """Return (bank units held, donors held, sources rejected for this request).

        A hold is an ACCEPTED match with reserved units. Holds belonging to the request
        being matched are ignored because re-coordination replaces them.
        """
        bank_held: Dict[Any, int] = {}
        donor_held: set = set()
        rejected: set = set()
        if self.db is None:
            return bank_held, donor_held, rejected
        for m in self.db.query(Match).filter(Match.status == MatchStatus.ACCEPTED.value, Match.units.isnot(None)):
            if request_id is not None and m.request_id == request_id:
                continue
            if m.source_type == MatchSourceType.BLOOD_BANK.value:
                key = (m.source_id, (m.blood_group or "").upper())
                bank_held[key] = bank_held.get(key, 0) + (m.units or 0)
            else:
                donor_held.add(m.source_id)
        if request_id is not None:
            for m in self.db.query(Match).filter(Match.request_id == request_id,
                                                 Match.status == MatchStatus.REJECTED.value):
                rejected.add((m.source_type, m.source_id))
        return bank_held, donor_held, rejected

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
            expiry = item.get("expiry_date")
        elif isinstance(item, BloodInventory):
            bank_id = item.bank_id
            bg = item.blood_group
            units = item.units_available
            expiry = item.expiry_date
        else:
            return None

        if bank_id is None or not bg:
            return None

        return {
            "bank_id": bank_id,
            "blood_group": bg.strip().upper(),
            "units_available": int(units) if units is not None else 0,
            "expiry_date": expiry,
        }

    def _parse_donor(
        self, item: Union[Dict[str, Any], Donor]
    ) -> Optional[Dict[str, Any]]:
        """Normalize donor data from dict or SQLAlchemy model."""
        if isinstance(item, dict):
            donor_id = item.get("donor_id") or item.get("source_id")
            bg = item.get("blood_group")
            available = item.get("available", True)
            last_donation = item.get("last_donation_date")
        elif isinstance(item, Donor):
            donor_id = item.donor_id
            bg = item.blood_group
            available = item.available
            last_donation = item.last_donation_date
        else:
            return None

        if donor_id is None or not bg:
            return None

        return {
            "donor_id": donor_id,
            "blood_group": bg.strip().upper(),
            "available": bool(available),
            "last_donation_date": last_donation,
        }
