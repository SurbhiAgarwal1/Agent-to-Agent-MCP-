"""Optimization Service for Multi-Source Blood Fulfillment.

Part 10: Intelligently combines multiple sources (blood banks and donors)
to satisfy the total units_required when a single source is insufficient,
minimizing travel burden and respecting medical donor limitations.
"""

from enum import Enum
from typing import Any, Dict, List, Optional


class FulfillmentStatus(str, Enum):
    """Fulfillment state of a blood allocation plan."""
    FULLY_FULFILLED = "FULLY_FULFILLED"
    PARTIALLY_FULFILLED = "PARTIALLY_FULFILLED"
    UNFULFILLED = "UNFULFILLED"


class OptimizationService:
    """Service to generate optimal multi-source fulfillment plans."""

    # Medical policy assumption: A single voluntary donor can only donate 1 unit per request
    MAX_UNITS_PER_DONOR = 1

    # Urgency distance weighting multipliers
    URGENCY_WEIGHTS = {
        "CRITICAL": 1.5,
        "HIGH": 1.2,
        "MEDIUM": 1.0,
        "LOW": 0.8,
    }

    @classmethod
    def calculate_candidate_score(
        cls,
        candidate: Dict[str, Any],
        urgency: str,
    ) -> float:
        """Calculate weighted dispatch score for a candidate source.
        
        Formula:
            score = distance_km * urgency_weight - source_preference_bonus
            
        Where:
            - distance_km: straight-line or road distance
            - urgency_weight: higher urgency penalizes distance more heavily
            - source_preference_bonus: 0.5 bonus (lower score) for blood banks
              to reduce logistical fragmentation when multiple units are needed.
              
        Lower score is prioritized first in greedy allocation.
        """
        distance_km = float(candidate.get("distance_km", 999.0))
        urgency_upper = (urgency or "MEDIUM").strip().upper()
        urgency_weight = cls.URGENCY_WEIGHTS.get(urgency_upper, 1.0)

        # Base cost influenced by distance and urgency urgency
        score = distance_km * urgency_weight

        # Prefer blood banks over donors to minimize multi-site logistics
        source_type = candidate.get("source_type", "")
        if str(source_type).upper() == "BLOOD_BANK":
            score -= 0.5

        return round(score, 4)

    def optimize(
        self,
        request_id: int,
        units_required: int,
        urgency: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a multi-source fulfillment plan.
        
        Args:
            request_id: Identifier of the blood request.
            units_required: Total units needed by the hospital.
            urgency: Urgency level ("CRITICAL", "HIGH", "MEDIUM", "LOW").
            candidates: List of candidate sources with distance and units.
            
        Returns:
            Dictionary representing the fulfillment plan:
            {
                "request_id": int,
                "fulfilled": bool,
                "plan": List[Dict[str, Any]],
                "total_units": int,
                "status": "FULLY_FULFILLED" | "PARTIALLY_FULFILLED" | "UNFULFILLED",
                "details": Dict[str, Any]
            }
        """
        if not candidates or units_required <= 0:
            return {
                "request_id": request_id,
                "fulfilled": False,
                "plan": [],
                "total_units": 0,
                "status": FulfillmentStatus.UNFULFILLED.value,
                "details": {
                    "units_required": max(0, units_required),
                    "units_shortage": max(0, units_required),
                    "algorithm": "greedy_nearest_urgency_weighted",
                },
            }

        # 1. Score and rank candidates
        scored_candidates = []
        for cand in candidates:
            c = dict(cand)
            score = self.calculate_candidate_score(c, urgency)
            c["_optimization_score"] = score
            scored_candidates.append(c)

        # Sort ascending by optimization score (lowest distance/cost first)
        scored_candidates.sort(key=lambda x: x["_optimization_score"])

        # 2. Greedy allocation
        plan: List[Dict[str, Any]] = []
        units_remaining = units_required
        total_allocated = 0

        for cand in scored_candidates:
            if units_remaining <= 0:
                break

            s_type = cand.get("source_type", "BLOOD_BANK")
            avail = int(cand.get("units_available", 1))

            # Apply donor allocation constraint (max 1 unit per voluntary donor)
            if s_type == "DONOR":
                max_allocatable = min(avail, self.MAX_UNITS_PER_DONOR)
            else:
                max_allocatable = avail

            if max_allocatable <= 0:
                continue

            units_to_take = min(max_allocatable, units_remaining)
            total_allocated += units_to_take
            units_remaining -= units_to_take

            plan_entry = {
                "source_type": s_type,
                "source_id": cand.get("source_id"),
                "units": units_to_take,
                "distance_km": cand.get("distance_km"),
            }
            if "name" in cand:
                plan_entry["name"] = cand["name"]
            if "estimated_time" in cand:
                plan_entry["estimated_time"] = cand["estimated_time"]

            plan.append(plan_entry)

        # 3. Determine status
        if total_allocated >= units_required:
            status = FulfillmentStatus.FULLY_FULFILLED.value
            fulfilled = True
        elif total_allocated > 0:
            status = FulfillmentStatus.PARTIALLY_FULFILLED.value
            fulfilled = False
        else:
            status = FulfillmentStatus.UNFULFILLED.value
            fulfilled = False

        return {
            "request_id": request_id,
            "fulfilled": fulfilled,
            "plan": plan,
            "total_units": total_allocated,
            "status": status,
            "details": {
                "units_required": units_required,
                "units_shortage": max(0, units_required - total_allocated),
                "algorithm": "greedy_nearest_urgency_weighted",
            },
        }
